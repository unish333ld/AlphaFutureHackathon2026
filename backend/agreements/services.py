import hashlib
import hmac
import json
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from agreements.demo_codes import DemoCodeAdapter, require_demo_codes
from agreements.models import Agreement, Disbursement, SignatureAttempt, SignatureConfirmation
from applications.models import Application
from applications.services import current_revision, locked_application, require_assignee, transition
from common.access import require_member, require_specialist
from common.exceptions import Conflict
from offers.models import Offer
from products.presentation import cost_breakdown


def terms_hash(terms):
    return hashlib.sha256(
        json.dumps(terms, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _offer_application(offer_id):
    offer = get_object_or_404(
        Offer.objects.select_related("decision__assessment__revision"), pk=offer_id
    )
    return offer, offer.decision.assessment.revision.application_id


@transaction.atomic
def respond_to_offer(user, offer_id, version, *, accept):
    offer, app_id = _offer_application(offer_id)
    app = locked_application(app_id, version)
    require_member(user, app.company_id, "can_submit")
    offer.refresh_from_db()
    if (
        app.status != Application.Status.OFFERED
        or offer.status != Offer.Status.AVAILABLE
        or offer.expires_at <= timezone.now()
        or offer.decision.assessment.revision_id != current_revision(app).id
    ):
        raise Conflict("Предложение истекло, заменено или недоступно.")
    if not accept:
        offer.status = Offer.Status.DECLINED
        offer.save(update_fields=["status"])
        transition(app, Application.Status.DECLINED, user, "offer_declined")
        return app
    offer.status = Offer.Status.ACCEPTED
    offer.accepted_at = timezone.now()
    offer.sign_before = offer.accepted_at + timedelta(days=3)
    offer.save(update_fields=["status", "accepted_at", "sign_before"])
    terms = {
        "schema_version": 1,
        "offer_id": str(offer.id),
        "company_id": str(app.company_id),
        "amount": str(offer.amount),
        "annual_rate": str(offer.annual_rate),
        "term_months": offer.term_months,
        "monthly_payment": str(offer.monthly_payment),
        "schedule": offer.schedule,
        "signature_mode": "simulation",
        "parties": {"company": offer.decision.assessment.revision.input_snapshot["company"]},
        "product_name": offer.decision.assessment.revision.input_snapshot["product"].get(
            "name", offer.decision.assessment.revision.input_snapshot["product"]["code"]
        ),
        "purpose": offer.decision.assessment.revision.purpose,
        "cost_breakdown": cost_breakdown(offer.amount, offer.schedule),
        "catalog_version": offer.decision.assessment.revision.input_snapshot["product"][
            "rules_version"
        ],
    }
    Agreement.objects.create(
        offer=offer,
        number=f"DEMO-{uuid.uuid4().hex.upper()}",
        terms_snapshot=terms,
        document_hash=terms_hash(terms),
    )
    transition(app, Application.Status.ACCEPTED, user, "offer_accepted")
    return app


def sign_agreement(
    user,
    agreement_id,
    version,
    document_hash,
    *,
    attempt_id=None,
    document_id=None,
    pdf_sha256=None,
    code=None,
):
    """The only signing boundary; no legacy hash-only shortcut remains."""
    require_demo_codes()
    with transaction.atomic():
        agreement, app = signature_context(user, agreement_id, version, document_hash)
        attempt = get_object_or_404(
            SignatureAttempt.objects.select_for_update(),
            pk=attempt_id,
            user=user,
            agreement=agreement,
            company_id=app.company_id,
        )
        if attempt.state != SignatureAttempt.State.PENDING:
            raise Conflict("Попытка подтверждения уже недоступна.", code="attempt_unavailable")
        error = None
        if attempt.expires_at <= timezone.now():
            attempt.state = SignatureAttempt.State.EXPIRED
            attempt.save(update_fields=["state"])
            error = Conflict(
                "Срок демо-кода истёк. Начните подтверждение заново.", code="attempt_expired"
            )
        elif (
            attempt.lock_version != version
            or attempt.document_hash != document_hash
            or str(attempt.document_id) != str(document_id)
            or attempt.pdf_sha256 != pdf_sha256
        ):
            raise Conflict("Попытка относится к другой версии документа.", code="terms_mismatch")
        else:
            from agreements.documents import assert_integrity

            document = attempt.document
            assert_integrity(document)
            if document.terms_hash != agreement.document_hash or document.snapshot["signer"][
                "id"
            ] != str(user.pk):
                raise Conflict("Документ сформирован для другой версии или подписанта.")
            if not hmac.compare_digest(
                attempt.code_digest, DemoCodeAdapter.digest(attempt.id, code)
            ):
                attempt.failures += 1
                if attempt.failures >= 5:
                    attempt.state = SignatureAttempt.State.LOCKED
                attempt.save(update_fields=["failures", "state"])
                error = ValidationError({"code": ["Неверный демонстрационный код."]})
            else:
                attempt.state = SignatureAttempt.State.USED
                attempt.save(update_fields=["state"])
                agreement.signed_by = user
                agreement.signed_at = timezone.now()
                agreement.save(update_fields=["signed_by", "signed_at"])
                confirmation = SignatureConfirmation.objects.create(
                    agreement=agreement,
                    document=document,
                    attempt=attempt,
                    user=user,
                    company_id=app.company_id,
                    confirmed_at=agreement.signed_at,
                    document_hash=agreement.document_hash,
                    pdf_sha256=document.pdf_sha256,
                )
                transition(
                    app,
                    Application.Status.SIGNED,
                    user,
                    "signed",
                    {
                        "signature_mode": "simulation",
                        "confirmation_id": str(confirmation.pk),
                        "document_id": str(document.pk),
                        "pdf_sha256": document.pdf_sha256,
                    },
                )
    # Failed checks must commit their counters/expiry before returning an error.
    if error:
        raise error
    return agreement


def signature_context(user, agreement_id, version, document_hash):
    agreement = get_object_or_404(
        Agreement.objects.select_related("offer__decision__assessment__revision"), pk=agreement_id
    )
    app = locked_application(agreement.offer.decision.assessment.revision.application_id, version)
    require_member(user, app.company_id, "can_sign")
    agreement.refresh_from_db()
    offer = agreement.offer
    if (
        app.status != Application.Status.ACCEPTED
        or offer.status != Offer.Status.ACCEPTED
        or agreement.signed_at
        or offer.decision.assessment.revision_id != current_revision(app).id
    ):
        raise Conflict("Договор недоступен для условного подписания.")
    if not offer.sign_before or offer.sign_before <= timezone.now():
        raise Conflict("Срок условного подписания истёк.")
    if (
        document_hash != agreement.document_hash
        or terms_hash(agreement.terms_snapshot) != agreement.document_hash
    ):
        raise Conflict("Версия условий не совпадает с принятой. Обновите договор.")
    return agreement, app


@transaction.atomic
def start_signature_attempt(user, agreement_id, version, document_hash, document_id, pdf_sha256):
    require_demo_codes()
    agreement, app = signature_context(user, agreement_id, version, document_hash)
    from agreements.documents import assert_integrity
    from agreements.models import AgreementDocument

    document = get_object_or_404(
        AgreementDocument, pk=document_id, agreement=agreement, kind="original"
    )
    assert_integrity(document)
    if (
        document.pdf_sha256 != pdf_sha256
        or document.terms_hash != document_hash
        or document.snapshot["signer"]["id"] != str(user.pk)
    ):
        raise Conflict(
            "Документ или подписант не совпадает с просмотренной версией.", code="terms_mismatch"
        )
    now = timezone.now()
    SignatureAttempt.objects.filter(
        agreement=agreement, state="pending", expires_at__lte=now
    ).update(state="expired")
    pending = SignatureAttempt.objects.filter(
        agreement=agreement, user=user, state="pending"
    ).first()
    if pending:
        if pending.document_id != document.pk or pending.lock_version != version:
            pending.state = "cancelled"
            pending.save(update_fields=["state"])
        else:
            return pending
    if (
        SignatureAttempt.objects.filter(
            user=user, agreement=agreement, created_at__gte=now - timedelta(hours=1)
        ).count()
        >= 10
    ):
        from rest_framework.exceptions import Throttled

        raise Throttled(wait=3600, detail="Лимит демонстрационных попыток. Повторите позже.")
    attempt = SignatureAttempt(
        agreement=agreement,
        document=document,
        user=user,
        company_id=app.company_id,
        lock_version=version,
        document_hash=document_hash,
        pdf_sha256=pdf_sha256,
        expires_at=now + timedelta(minutes=2),
    )
    attempt.code_digest = DemoCodeAdapter.digest(attempt.pk, DemoCodeAdapter.code(attempt.pk))
    attempt.save()
    return attempt


@transaction.atomic
def cancel_signature_attempt(user, agreement_id, attempt_id):
    agreement = get_object_or_404(
        Agreement.objects.select_related("offer__decision__assessment__revision"), pk=agreement_id
    )
    app = Application.objects.select_for_update().get(
        pk=agreement.offer.decision.assessment.revision.application_id
    )
    require_member(user, app.company_id, "can_sign")
    attempt = get_object_or_404(SignatureAttempt, pk=attempt_id, agreement=agreement, user=user)
    if attempt.state == "used":
        raise Conflict(
            "Подпись уже могла сохраниться. Обновите карточку.", code="already_completed"
        )
    if attempt.state == "pending":
        attempt.state = "cancelled"
        attempt.save(update_fields=["state"])
    return attempt


@transaction.atomic
def disburse(user, agreement_id, version, idempotency_key):
    require_specialist(user)
    agreement = get_object_or_404(
        Agreement.objects.select_related("offer__decision__assessment__revision"), pk=agreement_id
    )
    # One application lock serializes every mutation, including requests with different keys.
    app = Application.objects.select_for_update().get(
        pk=agreement.offer.decision.assessment.revision.application_id
    )
    existing = Disbursement.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.agreement_id != agreement.id:
            raise Conflict("Idempotency-Key уже использован с другим договором.")
        return existing
    if app.lock_version != version:
        raise Conflict("Устаревший lock_version.", code="stale_version")
    require_assignee(user, app)
    agreement.refresh_from_db()
    if app.status != Application.Status.SIGNED or not agreement.signed_at:
        raise Conflict("Выдача доступна только по условно подписанному договору.")
    if agreement.offer.decision.assessment.revision_id != current_revision(app).id:
        raise Conflict("Договор относится к другой ревизии.", code="assessment_outdated")
    if agreement.document_hash != terms_hash(agreement.terms_snapshot):
        raise Conflict("Целостность условий договора нарушена.")
    if str(agreement.offer.amount) != agreement.terms_snapshot.get("amount"):
        raise ValidationError("Сумма договора не совпадает с предложением.")
    try:
        with transaction.atomic():
            result = Disbursement.objects.create(
                agreement=agreement, amount=agreement.offer.amount, idempotency_key=idempotency_key
            )
    except IntegrityError as exc:
        raise Conflict(
            "Для договора уже существует выдача или ключ использован другим запросом."
        ) from exc
    transition(
        app,
        Application.Status.ISSUED,
        user,
        "issued",
        {"disbursement_id": str(result.id), "is_simulated": True},
    )
    return result

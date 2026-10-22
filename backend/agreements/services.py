import hashlib
import json
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from agreements.models import Agreement, Disbursement
from applications.models import Application
from applications.services import current_revision, locked_application, transition
from common.access import require_member, require_specialist
from common.exceptions import Conflict
from offers.models import Offer


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
    }
    Agreement.objects.create(
        offer=offer,
        number=f"DEMO-{uuid.uuid4().hex.upper()}",
        terms_snapshot=terms,
        document_hash=terms_hash(terms),
    )
    transition(app, Application.Status.ACCEPTED, user, "offer_accepted")
    return app


@transaction.atomic
def sign_agreement(user, agreement_id, version, document_hash):
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
    ):
        raise Conflict("Договор недоступен для условного подписания.")
    if not offer.sign_before or offer.sign_before <= timezone.now():
        raise Conflict("Срок условного подписания истёк.")
    if (
        document_hash != agreement.document_hash
        or terms_hash(agreement.terms_snapshot) != agreement.document_hash
    ):
        raise Conflict("Версия условий не совпадает с принятой. Обновите договор.")
    agreement.signed_by = user
    agreement.signed_at = timezone.now()
    agreement.save(update_fields=["signed_by", "signed_at"])
    transition(app, Application.Status.SIGNED, user, "signed", {"signature_mode": "simulation"})
    return agreement


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
        raise Conflict("Устаревший lock_version.")
    agreement.refresh_from_db()
    if app.status != Application.Status.SIGNED or not agreement.signed_at:
        raise Conflict("Выдача доступна только по условно подписанному договору.")
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

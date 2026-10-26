"""Prepare under a short lock, render without a transaction, compare-and-save."""

import copy
import hashlib
import json
import subprocess
import sys
import uuid

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from agreements.models import Agreement, AgreementDocument
from agreements.services import terms_hash
from applications.models import Application
from applications.services import current_revision
from common.access import require_member
from common.exceptions import Conflict, DependencyUnavailable
from products.presentation import CALCULATION_VERSION, cost_breakdown

TEMPLATE_VERSION = "demo-credit-contract-1"
MAX_PDF_BYTES = 4 * 1024 * 1024


def assert_integrity(document):
    if hashlib.sha256(bytes(document.pdf_data)).hexdigest() != document.pdf_sha256:
        raise Conflict("Целостность PDF нарушена. Документ недоступен.", code="document_integrity")
    if terms_hash(document.snapshot["terms"]) != document.terms_hash:
        raise Conflict("Снимок PDF не совпадает с условиями.", code="document_integrity")


def render_pdf(snapshot):
    encoded = json.dumps(snapshot, ensure_ascii=False).encode()
    if len(encoded) > 256 * 1024:
        raise ValidationError({"document": ["Данные документа превышают допустимый размер."]})
    try:
        result = subprocess.run(
            [sys.executable, "-m", "agreements.pdf_worker"],
            input=encoded,
            capture_output=True,
            timeout=settings.PDF_RENDER_TIMEOUT_SECONDS,
            cwd=str(settings.BASE_DIR),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise DependencyUnavailable(
            "PDF временно не сформирован. Подпись не выполнялась повторно."
        ) from exc
    if (
        result.returncode
        or not result.stdout.startswith(b"%PDF-")
        or len(result.stdout) > MAX_PDF_BYTES
    ):
        # Never expose stderr: it can contain document contents or local paths.
        raise DependencyUnavailable(
            "Не удалось сформировать PDF. Условия сохранены; повторите формирование документа."
        )
    return result.stdout


def _agreement(agreement_id):
    return get_object_or_404(
        Agreement.objects.select_related("offer__decision__assessment__revision", "signed_by"),
        pk=agreement_id,
    )


def _validate_source(agreement, app):
    offer = agreement.offer
    if terms_hash(agreement.terms_snapshot) != agreement.document_hash:
        raise Conflict("Целостность условий договора нарушена.")
    terms = agreement.terms_snapshot
    if any(
        terms.get(field) != value
        for field, value in {
            "offer_id": str(offer.pk),
            "company_id": str(app.company_id),
            "amount": str(offer.amount),
            "annual_rate": str(offer.annual_rate),
            "term_months": offer.term_months,
            "monthly_payment": str(offer.monthly_payment),
            "schedule": offer.schedule,
        }.items()
    ):
        raise Conflict("Снимок договора расходится с принятым предложением.", code="terms_mismatch")
    if offer.decision.assessment.revision_id != current_revision(app).id:
        raise Conflict("Договор относится к другой ревизии.")
    if app.status not in {"accepted", "signed", "issued"}:
        raise Conflict("Договор недоступен в текущем состоянии.")
    if not agreement.signed_at and (not offer.sign_before or offer.sign_before <= timezone.now()):
        raise Conflict("Срок подписания истёк.", code="offer_expired")


def _snapshot(agreement, user, membership):
    revision = agreement.offer.decision.assessment.revision
    terms = copy.deepcopy(agreement.terms_snapshot)
    sides = terms.get("parties")
    company = copy.deepcopy(
        sides["company"] if sides else revision.input_snapshot.get("company", {})
    )
    product = terms.get("product_name")
    if not product:
        # Historical submissions did not freeze a product name. Use a stable code,
        # not today's catalogue name, and explicitly identify that limitation.
        product = revision.input_snapshot.get("product", {}).get("code")
    purpose = terms.get("purpose", revision.purpose)
    signer = agreement.signed_by or user
    if (
        not company.get("name")
        or not company.get("inn")
        or not product
        or not purpose
        or not signer.username
    ):
        raise ValidationError(
            {
                "document": [
                    "Недостаточно сведений: нужны название и ИНН компании, продукт, цель и уполномоченная учётная запись."
                ]
            }
        )
    for value, limit in [
        (company["name"], 255),
        (company["inn"], 12),
        (product, 255),
        (purpose, 1000),
        (signer.username, 150),
        (signer.get_full_name(), 301),
    ]:
        if len(value) > limit:
            raise ValidationError({"document": ["Превышена допустимая длина реквизитов."]})
    cost = cost_breakdown(terms["amount"], terms["schedule"])
    if terms.get("cost_breakdown") is not None and terms["cost_breakdown"] != cost:
        raise Conflict("Паспорт стоимости расходится с графиком договора.", code="terms_mismatch")
    if not cost["is_complete"]:
        raise ValidationError(
            {
                "document": [
                    "Полная стоимость неизвестна. Уточните комиссии и услуги до формирования договора."
                ]
            }
        )
    return {
        "schema_version": 1,
        "id": str(uuid.uuid4()),
        "version": 1,
        "number": agreement.number,
        "agreement_id": str(agreement.pk),
        "offer_id": str(agreement.offer_id),
        "revision_id": str(revision.pk),
        "agreement_created_at": agreement.created_at.isoformat(),
        "generated_at": timezone.now().isoformat(),
        "template_version": TEMPLATE_VERSION,
        "calculator_version": CALCULATION_VERSION,
        "document_hash": agreement.document_hash,
        "terms": terms,
        "company": company,
        "signer": {
            "id": str(signer.pk),
            "username": signer.username,
            "full_name": signer.get_full_name() or None,
            "role": membership.role,
        },
        "product_name": product,
        "purpose": purpose,
        "cost": cost,
        "currency": "RUB",
        "rate_type": "Фиксированная учебная ставка, процентов годовых",
        "security": None,
        "confirmation": None,
    }


def generate_document(user, agreement_id, *, kind="original", version=None, document_hash=None):
    with transaction.atomic():
        agreement = _agreement(agreement_id)
        app = Application.objects.select_for_update().get(
            pk=agreement.offer.decision.assessment.revision.application_id
        )
        membership = require_member(user, app.company_id, "can_sign")
        if version is not None and version != app.lock_version:
            raise Conflict("Устаревший lock_version.", code="stale_version")
        if document_hash is not None and document_hash != agreement.document_hash:
            raise Conflict("Версия условий не совпадает.", code="terms_mismatch")
        _validate_source(agreement, app)
        existing = agreement.documents.filter(kind=kind, version=1).first()
        if existing:
            assert_integrity(existing)
            return existing
        source = None
        if kind == AgreementDocument.Kind.SIGNED_COPY:
            confirmation = getattr(agreement, "confirmation", None)
            if not agreement.signed_at or confirmation is None:
                raise Conflict("Нет подтверждения кодом для формирования копии.")
            source = confirmation.document
            assert_integrity(source)
            snapshot = copy.deepcopy(source.snapshot)
            snapshot.update(id=str(uuid.uuid4()), generated_at=timezone.now().isoformat())
            snapshot["confirmation"] = {
                "id": str(confirmation.pk),
                "attempt_id": str(confirmation.attempt_id),
                "user_id": str(confirmation.user_id),
                "confirmed_at": confirmation.confirmed_at.isoformat(),
                "source_document_id": str(source.pk),
                "source_pdf_sha256": source.pdf_sha256,
            }
        else:
            snapshot = _snapshot(agreement, user, membership)
        source_version = app.lock_version
        original_terms_hash = agreement.document_hash
    # No row lock, transaction or remote resource access during rendering.
    pdf = render_pdf(snapshot)
    with transaction.atomic():
        app = Application.objects.select_for_update().get(pk=app.pk)
        agreement = _agreement(agreement_id)
        _validate_source(agreement, app)
        require_member(user, app.company_id, "can_sign")
        existing = agreement.documents.filter(kind=kind, version=1).first()
        if existing:
            assert_integrity(existing)
            return existing
        if agreement.document_hash != original_terms_hash or (
            kind == "original" and app.lock_version != source_version
        ):
            raise Conflict(
                "Условия изменились во время формирования. Обновите договор.", code="stale_version"
            )
        return AgreementDocument.objects.create(
            id=uuid.UUID(snapshot["id"]),
            agreement=agreement,
            kind=kind,
            version=1,
            template_version=snapshot["template_version"],
            calculator_version=snapshot["calculator_version"],
            snapshot=snapshot,
            terms_hash=original_terms_hash,
            pdf_sha256=hashlib.sha256(pdf).hexdigest(),
            pdf_data=pdf,
            source_document=source,
        )

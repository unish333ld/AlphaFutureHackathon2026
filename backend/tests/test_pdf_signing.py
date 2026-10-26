"""Independent arithmetic, real PDF renders, private delivery and adversarial signing."""

import hashlib
import io
import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.exceptions import ValidationError

from agreements import documents, services
from agreements.models import (
    Agreement,
    AgreementDocument,
    Disbursement,
    SignatureAttempt,
    SignatureConfirmation,
)
from applications import services as applications
from applications.models import Application
from common.exceptions import Conflict, DependencyUnavailable
from companies.models import CompanyMember
from offers.models import Offer
from products.calculations import payment_schedule
from products.models import CreditProduct
from tests.signing import signing_payload
from tests.test_api_edges import request
from tests.test_frontend_contract import assert_response


def independent_schedule(amount, rate, months):
    """Separate recurrence and high precision; never call the product calculator."""
    with localcontext() as context:
        context.prec = 50
        cent = Decimal(".01")
        principal = Decimal(amount)
        monthly = Decimal(rate) / Decimal(1200)
        discount_sum = sum((1 + monthly) ** -period for period in range(1, months + 1))
        installment = (principal / discount_sum).quantize(cent, rounding=ROUND_HALF_UP)
        balance = principal
        rows = []
        for period in range(1, months + 1):
            interest = (balance * monthly).quantize(cent, rounding=ROUND_HALF_UP)
            repayment = min(installment - interest, balance) if period != months else balance
            balance -= repayment
            rows.append(
                {
                    "month": period,
                    "payment": repayment + interest,
                    "principal": repayment,
                    "interest": interest,
                    "balance": balance,
                }
            )
        return installment, rows


@pytest.mark.parametrize("amount", ["300000.00", "1100000.00", "30000000.00", "1100000.37"])
@pytest.mark.parametrize("rate", ["0", "27", "100"])
@pytest.mark.parametrize("months", [12, 24, 60])
def test_independent_arithmetic_matches_every_period(amount, rate, months):
    payment, expected = independent_schedule(amount, rate, months)
    actual_payment, actual = payment_schedule(Decimal(amount), Decimal(rate), months)
    assert actual_payment == payment
    assert actual["rows"] == [
        {key: value if key == "month" else f"{value:.2f}" for key, value in row.items()}
        for row in expected
    ]
    assert sum(row["principal"] for row in expected) == Decimal(amount)
    assert expected[-1]["balance"] == 0
    if (amount, rate, months) == ("1100000.00", "27", 24):
        assert payment == Decimal("59818.25")
        assert expected[-1]["payment"] == Decimal("59818.30")
        assert sum(row["interest"] for row in expected) == Decimal("335638.05")
        assert sum(row["payment"] for row in expected) == Decimal("1435638.05")


def test_real_pdf_private_stable_and_copy_never_rewrites_original(demo, agreement, api):
    app = agreement.offer.decision.assessment.revision.application
    data = signing_payload(demo["client"], agreement, app.lock_version)
    document = AgreementDocument.objects.get(pk=data["document_id"])
    first = bytes(document.pdf_data)
    reader = PdfReader(io.BytesIO(first))
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert agreement.number in text and "Учебный график" in text and "Месяц" in text
    assert "Демо · Рост" in " ".join(text.split()) and "0000000001" in text
    for page in reader.pages:
        assert abs(float(page.mediabox.width) - 595.28) < 0.1
        assert abs(float(page.mediabox.height) - 841.89) < 0.1
        fonts = page["/Resources"]["/Font"].get_object().values()
        assert any(
            "/FontFile2" in desc["/FontDescriptor"].get_object()
            for font in fonts
            for desc in font.get_object().get("/DescendantFonts", [])
        )
    path = f"agreements/{agreement.id}/pdf/"
    for user, expected in [
        (demo["client"], 200),
        (demo["accountant"], 200),
        (demo["specialist"], 200),
        (demo["outsider"], 404),
    ]:
        result = request(api, user, "get", path, expected=expected)
        if expected == 200:
            assert result.content == first
            assert result["Content-Type"] == "application/pdf"
            assert "private" in result["Cache-Control"] and "no-store" in result["Cache-Control"]
    assert request(api, demo["client"], "get", path + "?download=true")[
        "Content-Disposition"
    ].startswith("attachment;")
    assert (
        documents.generate_document(demo["client"], agreement.pk).pdf_sha256
        == hashlib.sha256(first).hexdigest()
    )
    assert agreement.document_hash != document.pdf_sha256
    signed = request(api, demo["client"], "post", f"agreements/{agreement.id}/sign/", data).json()
    assert signed["signed_at"] and Disbursement.objects.count() == 0
    app.refresh_from_db()
    assert app.status == "signed"
    audit = SignatureConfirmation.objects.get(agreement=agreement)
    assert audit.pdf_sha256 == document.pdf_sha256
    event = app.events.get(event_type="signed")
    assert event.details["confirmation_id"] == str(audit.id) and "code" not in event.details
    with patch("agreements.documents.render_pdf", side_effect=DependencyUnavailable()):
        request(
            api,
            demo["client"],
            "post",
            f"agreements/{agreement.id}/signed-document/",
            {"lock_version": app.lock_version, "document_hash": agreement.document_hash},
            expected=503,
        )
    agreement.refresh_from_db()
    assert agreement.signed_at
    copy = documents.generate_document(demo["client"], agreement.pk, kind="signed_copy")
    assert copy.source_document_id == document.pk and copy.pdf_sha256 != document.pdf_sha256
    assert "Отметка демонстрационного" in " ".join(
        page.extract_text() for page in PdfReader(io.BytesIO(bytes(copy.pdf_data))).pages
    )
    assert request(api, demo["client"], "get", path).content == first
    request(api, demo["outsider"], "get", path + "?kind=signed_copy", expected=404)
    request(api, demo["client"], "post", f"agreements/{agreement.id}/sign/", data, expected=409)
    assert SignatureConfirmation.objects.count() == 1


def test_cancel_and_signed_copy_http_contracts_preserve_one_signature(demo, agreement, api):
    app = agreement.offer.decision.assessment.revision.application
    data = signing_payload(demo["client"], agreement, app.lock_version)
    base = f"agreements/{agreement.pk}/"
    request(
        api,
        demo["outsider"],
        "post",
        base + "cancel-signature/",
        {"attempt_id": data["attempt_id"]},
        expected=404,
    )
    request(
        api,
        demo["client"],
        "post",
        base + "cancel-signature/",
        {"attempt_id": data["attempt_id"]},
        expected=204,
    )
    assert SignatureAttempt.objects.get(pk=data["attempt_id"]).state == "cancelled"
    request(api, demo["client"], "post", base + "sign/", data, expected=409)
    reopened = signing_payload(demo["client"], agreement, app.lock_version)
    assert reopened["attempt_id"] != data["attempt_id"]
    request(api, demo["client"], "post", base + "sign/", reopened)
    request(
        api,
        demo["client"],
        "post",
        base + "cancel-signature/",
        {"attempt_id": reopened["attempt_id"]},
        expected=409,
    )
    app.refresh_from_db()
    response = request(
        api,
        demo["client"],
        "post",
        base + "signed-document/",
        {
            "lock_version": app.lock_version,
            "document_hash": agreement.document_hash,
        },
    )
    schema = api.get("/api/schema/?format=json").json()
    metadata = response.json()
    assert_response(schema, metadata, "/api/v1/agreements/{id}/signed-document/", "post")
    assert (
        metadata["kind"] == "signed_copy"
        and "pdf_data" not in metadata
        and "snapshot" not in metadata
    )
    copy = request(api, demo["client"], "get", base + "pdf/?kind=signed_copy")
    assert hashlib.sha256(copy.content).hexdigest() == metadata["pdf_sha256"]
    request(api, demo["client"], "get", base + "pdf/?kind=other", expected=400)
    request(api, demo["client"], "get", base + "pdf/?download=invalid", expected=400)
    assert SignatureConfirmation.objects.filter(agreement=agreement).count() == 1
    assert not Disbursement.objects.exists()


@pytest.mark.parametrize(
    "case",
    [
        "version",
        "request_hash",
        "terms_hash",
        "offer_mismatch",
        "state",
        "deadline",
        "purpose_length",
        "product_missing",
        "cost_mismatch",
        "old_revision",
    ],
)
def test_document_source_guards_reject_before_starting_renderer(demo, agreement, case):
    app = agreement.offer.decision.assessment.revision.application
    kwargs = {"version": app.lock_version, "document_hash": agreement.document_hash}
    terms = deepcopy(agreement.terms_snapshot)
    expected = Conflict
    if case == "version":
        kwargs["version"] += 1
    elif case == "request_hash":
        kwargs["document_hash"] = "0" * 64
    elif case == "terms_hash":
        terms["amount"] = "123.00"
        Agreement.objects.filter(pk=agreement.pk).update(terms_snapshot=terms)
    elif case == "state":
        Application.objects.filter(pk=app.pk).update(status="offered")
    elif case == "deadline":
        Offer.objects.filter(pk=agreement.offer_id).update(
            sign_before=timezone.now() - timedelta(seconds=1)
        )
    elif case == "product_missing":
        terms.pop("product_name")
        revision = agreement.offer.decision.assessment.revision
        snapshot = deepcopy(revision.input_snapshot)
        snapshot["product"].pop("code")
        type(revision).objects.filter(pk=revision.pk).update(input_snapshot=snapshot)
        expected = ValidationError
    elif case == "purpose_length":
        terms["purpose"] = "я" * 1001
        expected = ValidationError
    elif case == "cost_mismatch":
        terms["cost_breakdown"]["total_repayment"] = "1.00"
    elif case == "old_revision":
        revision = agreement.offer.decision.assessment.revision
        # A separate newer revision is enough to invalidate the agreement source.
        values = {
            field.attname: getattr(revision, field.attname)
            for field in revision._meta.concrete_fields
        }
        values.update(id=uuid.uuid4(), revision_no=revision.revision_no + 1)
        type(revision).objects.create(**values)
    else:
        terms["amount"] = "123.00"
    if case in {"offer_mismatch", "purpose_length", "product_missing", "cost_mismatch"}:
        kwargs["document_hash"] = services.terms_hash(terms)
        Agreement.objects.filter(pk=agreement.pk).update(
            terms_snapshot=terms, document_hash=kwargs["document_hash"]
        )
    with patch("agreements.documents.render_pdf") as render, pytest.raises(expected):
        documents.generate_document(demo["client"], agreement.pk, **kwargs)
    render.assert_not_called()
    assert not AgreementDocument.objects.exists() and not SignatureConfirmation.objects.exists()


def test_oversized_document_input_never_starts_subprocess():
    with patch("agreements.documents.subprocess.run") as run, pytest.raises(ValidationError):
        documents.render_pdf({"purpose": "я" * (256 * 1024)})
    run.assert_not_called()


@pytest.mark.parametrize(
    "case",
    [
        "missing_attempt",
        "wrong_code",
        "expired",
        "cancelled",
        "wrong_document",
        "wrong_pdf",
        "wrong_hash",
        "stale_version",
        "other_user",
        "no_capability",
        "disabled_demo",
    ],
)
def test_signature_adversarial_attempts(demo, agreement, api, settings, case):
    app = agreement.offer.decision.assessment.revision.application
    data = signing_payload(demo["client"], agreement, app.lock_version)
    attempt = SignatureAttempt.objects.get(pk=data["attempt_id"])
    user = demo["client"]
    expected = 409
    if case == "missing_attempt":
        data.pop("attempt_id")
        expected = 400
    elif case == "wrong_code":
        data["code"] = "000000" if data["code"] != "000000" else "111111"
        expected = 400
    elif case == "expired":
        SignatureAttempt.objects.filter(pk=attempt.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
    elif case == "cancelled":
        services.cancel_signature_attempt(user, agreement.pk, attempt.pk)
    elif case == "wrong_document":
        data["document_id"] = str(uuid.uuid4())
    elif case == "wrong_pdf":
        data["pdf_sha256"] = "0" * 64
    elif case == "wrong_hash":
        data["document_hash"] = "0" * 64
    elif case == "stale_version":
        data["lock_version"] -= 1
    elif case == "other_user":
        user = demo["accountant"]
        CompanyMember.objects.filter(user=user, company_id=app.company_id).update(can_sign=True)
        expected = 404
    elif case == "no_capability":
        user = demo["accountant"]
        expected = 403
    elif case == "disabled_demo":
        settings.DEMO_SIGNATURE_ENABLED = False
        expected = 403
    request(api, user, "post", f"agreements/{agreement.id}/sign/", data, expected=expected)
    agreement.refresh_from_db()
    app.refresh_from_db()
    attempt.refresh_from_db()
    assert agreement.signed_at is None and app.status == "accepted"
    assert not SignatureConfirmation.objects.exists() and not Disbursement.objects.exists()
    if case == "wrong_code":
        assert attempt.failures == 1
    if case == "expired":
        assert attempt.state == "expired"


def test_wrong_code_budget_persists_and_start_is_idempotent(demo, agreement, api):
    app = agreement.offer.decision.assessment.revision.application
    data = signing_payload(demo["client"], agreement, app.lock_version)
    start = {
        key: data[key] for key in ("lock_version", "document_hash", "document_id", "pdf_sha256")
    }
    start.update(acknowledged=True, confirm_simulation=True)
    response = request(
        api, demo["client"], "post", f"agreements/{agreement.id}/signature-attempt/", start
    ).json()
    assert response["id"] == data["attempt_id"] and response["demo_code"] == data["code"]
    wrong = {**data, "code": "000000" if data["code"] != "000000" else "111111"}
    for _ in range(5):
        request(
            api, demo["client"], "post", f"agreements/{agreement.id}/sign/", wrong, expected=400
        )
    request(api, demo["client"], "post", f"agreements/{agreement.id}/sign/", data, expected=409)
    attempt = SignatureAttempt.objects.get(pk=data["attempt_id"])
    assert attempt.failures == 5 and attempt.state == "locked"
    schema = api.get("/api/schema/?format=json").json()
    assert_response(schema, response, "/api/v1/agreements/{id}/signature-attempt/", "post")


@pytest.mark.django_db(transaction=True)
def test_concurrent_document_generation_is_outside_lock_and_returns_one_artifact(demo, agreement):
    gate = Barrier(2)
    real = documents.render_pdf

    def render(snapshot):
        assert not connection.in_atomic_block
        gate.wait(timeout=10)
        return real(snapshot)

    def generate(_):
        close_old_connections()
        try:
            return documents.generate_document(demo["client"], agreement.pk).id
        finally:
            close_old_connections()

    with (
        patch("agreements.documents.render_pdf", side_effect=render),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        ids = list(pool.map(generate, range(2)))
    assert ids[0] == ids[1] and AgreementDocument.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_document_cas_rejects_concurrent_version_change(demo, agreement):
    real = documents.render_pdf
    app = agreement.offer.decision.assessment.revision.application

    def render(snapshot):
        assert not connection.in_atomic_block
        Application.objects.filter(pk=app.pk).update(lock_version=app.lock_version + 1)
        return real(snapshot)

    with patch("agreements.documents.render_pdf", side_effect=render), pytest.raises(Conflict):
        documents.generate_document(demo["client"], agreement.pk)
    assert not AgreementDocument.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_tabs_cannot_sign_twice(demo, agreement):
    app = agreement.offer.decision.assessment.revision.application
    data = signing_payload(demo["client"], agreement, app.lock_version)
    gate = Barrier(2)

    def sign(_):
        close_old_connections()
        try:
            gate.wait(timeout=10)
            services.sign_agreement(
                demo["client"],
                agreement.pk,
                data["lock_version"],
                data["document_hash"],
                **{key: data[key] for key in ("attempt_id", "document_id", "pdf_sha256", "code")},
            )
            return "signed"
        except Conflict:
            return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(sign, range(2))) == ["conflict", "signed"]
    assert SignatureConfirmation.objects.count() == 1
    assert app.events.filter(event_type="signed").count() == 1
    assert not Disbursement.objects.exists()


def test_attempt_limit_and_expired_cancel_reopening(demo, agreement):
    from rest_framework.exceptions import Throttled

    app = agreement.offer.decision.assessment.revision.application
    data = signing_payload(demo["client"], agreement, app.lock_version)
    previous = data["attempt_id"]
    for _ in range(9):
        services.cancel_signature_attempt(demo["client"], agreement.pk, previous)
        data = signing_payload(demo["client"], agreement, app.lock_version)
        assert data["attempt_id"] != previous
        previous = data["attempt_id"]
    services.cancel_signature_attempt(demo["client"], agreement.pk, previous)
    with pytest.raises(Throttled):
        signing_payload(demo["client"], agreement, app.lock_version)
    assert SignatureAttempt.objects.count() == 10
    assert not SignatureAttempt.objects.filter(state="pending").exists()


def test_document_tampering_missing_fields_and_timeout_are_safe(demo, agreement, api):
    app = agreement.offer.decision.assessment.revision.application
    with patch(
        "agreements.documents.subprocess.run", side_effect=subprocess.TimeoutExpired("render", 20)
    ):
        with pytest.raises(DependencyUnavailable):
            documents.generate_document(demo["client"], agreement.pk)
    assert not AgreementDocument.objects.exists() and not agreement.signed_at
    data = signing_payload(demo["client"], agreement, app.lock_version)
    AgreementDocument.objects.filter(pk=data["document_id"]).update(pdf_data=b"%PDF-tampered")
    request(api, demo["client"], "get", f"agreements/{agreement.pk}/pdf/", expected=409)
    request(api, demo["client"], "post", f"agreements/{agreement.pk}/sign/", data, expected=409)
    assert not SignatureConfirmation.objects.exists()


@pytest.mark.parametrize("missing", ["company", "fees"])
def test_missing_parties_or_unknown_cost_never_generate_fiction(demo, agreement, missing):
    from rest_framework.exceptions import ValidationError

    from agreements.services import terms_hash

    terms = dict(agreement.terms_snapshot)
    if missing == "company":
        terms["parties"] = {"company": {**terms["parties"]["company"], "name": ""}}
    else:
        # Simulate an unsupported historical price structure in the isolated DB.
        terms["schedule"] = {**terms["schedule"], "fees": None}
        terms.pop("cost_breakdown")
        Offer.objects.filter(pk=agreement.offer_id).update(schedule=terms["schedule"])
    Agreement.objects.filter(pk=agreement.pk).update(
        terms_snapshot=terms, document_hash=terms_hash(terms)
    )
    with pytest.raises(ValidationError):
        documents.generate_document(demo["client"], agreement.pk)
    assert not AgreementDocument.objects.exists()


def test_attempt_cannot_be_used_for_another_agreement(demo, agreement, api):
    first_app = agreement.offer.decision.assessment.revision.application
    first = signing_payload(demo["client"], agreement, first_app.lock_version)
    second_app = demo["applications"]["counteroffer"]
    applications.submit_application(demo["client"], second_app.pk, second_app.lock_version)
    second_app.refresh_from_db()
    applications.claim_application(demo["specialist"], second_app.pk, second_app.lock_version)
    second_app.refresh_from_db()
    applications.make_decision(demo["specialist"], second_app.pk, second_app.lock_version)
    second_app.refresh_from_db()
    offer = Offer.objects.get(decision__assessment__revision__application=second_app)
    services.respond_to_offer(demo["client"], offer.pk, second_app.lock_version, accept=True)
    second_app.refresh_from_db()
    other = Agreement.objects.get(offer=offer)
    second = signing_payload(demo["client"], other, second_app.lock_version)
    request(
        api,
        demo["client"],
        "post",
        f"agreements/{other.pk}/sign/",
        {**second, "attempt_id": first["attempt_id"], "code": first["code"]},
        expected=404,
    )
    assert SignatureConfirmation.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_acceptance_racing_expiration_never_creates_expired_agreement(demo, offer):
    app = offer.decision.assessment.revision.application
    app.refresh_from_db()
    Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() - timedelta(milliseconds=1))
    gate = Barrier(2)

    def act(accept):
        close_old_connections()
        try:
            gate.wait(timeout=10)
            if accept:
                try:
                    services.respond_to_offer(
                        demo["client"], offer.pk, app.lock_version, accept=True
                    )
                except Conflict:
                    return "conflict"
                return "accepted"
            applications.expire_application_if_due(app.pk)
            return "expired"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(act, [True, False])) == ["conflict", "expired"]
    assert not Agreement.objects.exists()
    app.refresh_from_db()
    assert app.status == "expired"


def test_readiness_distinguishes_provided_from_checked_and_old_assessment(demo, api):
    app = demo["applications"]["approval"]
    before = request(api, demo["client"], "get", f"applications/{app.pk}/").json()["readiness"]
    assert before["financial_data_complete"] and before["verification_state"] == "not_checked"
    applications.submit_application(demo["client"], app.pk, app.lock_version)
    after = request(api, demo["client"], "get", f"applications/{app.pk}/").json()["readiness"]
    assert after["verification_state"] == "checked" and after["checked_at"]
    from decisions.models import Assessment

    Assessment.objects.filter(revision__application=app).update(checks_attempt=99)
    outdated = request(api, demo["client"], "get", f"applications/{app.pk}/").json()["readiness"]
    assert outdated["verification_state"] == "outdated"


@pytest.mark.parametrize(
    "amount,months,malicious",
    [
        ("1100000.00", 24, False),
        ("300000.37", 12, False),
        ("30000000.00", 60, False),
        ("1100000.00", 24, True),
    ],
)
def test_dynamic_pdf_samples_use_offer_not_live_catalogue(demo, api, amount, months, malicious):
    company = demo["applications"]["approval"].company
    company.name = "Демо · Производственно-коммерческое объединение научно-технического развития и перспективного машиностроения «Северный горизонт»"
    company.save(update_fields=["name"])
    app = applications.create_application(
        demo["client"],
        {
            "company": company.pk,
            "product": CreditProduct.objects.get(code="working-capital").pk,
            "amount": Decimal(amount),
            "term_months": months,
            "purpose": "Приобретение производственных материалов <script>alert(1)</script><img src='http://127.0.0.1/private'>"
            if malicious
            else "Приобретение производственных материалов и развитие производства",
            "monthly_revenue": Decimal("100000000"),
            "monthly_expenses": Decimal("1000000"),
            "monthly_debt_payments": Decimal("0"),
        },
    )
    applications.submit_application(demo["client"], app.pk, app.lock_version)
    app.refresh_from_db()
    applications.claim_application(demo["specialist"], app.pk, app.lock_version)
    app.refresh_from_db()
    applications.make_decision(demo["specialist"], app.pk, app.lock_version)
    app.refresh_from_db()
    offer = Offer.objects.get(decision__assessment__revision__application=app)
    services.respond_to_offer(demo["client"], offer.pk, app.lock_version, accept=True)
    app.refresh_from_db()
    agreement = Agreement.objects.get(offer=offer)
    CreditProduct.objects.filter(pk=app.product_id).update(
        annual_rate=99, name="Изменённый живой каталог"
    )
    data = signing_payload(demo["client"], agreement, app.lock_version)
    doc = AgreementDocument.objects.get(pk=data["document_id"])
    assert (
        doc.snapshot["terms"]["amount"] == amount
        and Decimal(doc.snapshot["terms"]["annual_rate"]) == 27
    )
    expected_payment, rows = independent_schedule(amount, "27", months)
    assert Decimal(doc.snapshot["cost"]["total_repayment"]) == sum(row["payment"] for row in rows)
    assert Decimal(doc.snapshot["terms"]["monthly_payment"]) == expected_payment
    text = " ".join(
        page.extract_text() for page in PdfReader(io.BytesIO(bytes(doc.pdf_data))).pages
    )
    assert "Изменённый живой каталог" not in text
    assert ("alert(1)" in text) == malicious
    assert "/OpenAction" not in PdfReader(io.BytesIO(bytes(doc.pdf_data))).trailer["/Root"]
    assert text.count("Итого") == 1
    output = os.environ.get("PDF_SAMPLE_DIR")
    if output and not malicious:
        target = Path(output)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"demo-{amount}-{months}-original.pdf").write_bytes(bytes(doc.pdf_data))
        if months == 24:
            request(api, demo["client"], "post", f"agreements/{agreement.pk}/sign/", data)
            signed = documents.generate_document(demo["client"], agreement.pk, kind="signed_copy")
            (target / f"demo-{amount}-{months}-signed-copy.pdf").write_bytes(bytes(signed.pdf_data))

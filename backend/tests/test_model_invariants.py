import uuid
from decimal import Decimal

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone

from accounts.models import User
from agreements.models import Agreement, Disbursement
from agreements.services import disburse
from applications.models import Application, ApplicationEvent, ApplicationRevision
from checks.models import CheckResult
from companies.models import CompanyMember
from decisions.models import Assessment, CreditDecision
from offers.models import Offer
from products.models import CreditProduct


@pytest.mark.parametrize(
    "fields",
    [
        {"min_amount": 0},
        {"max_amount": Decimal("99999.99")},
        {"min_term_months": 0},
        {"max_term_months": 5},
        {"max_term_months": 121},
        {"annual_rate": Decimal("-0.0001")},
        {"annual_rate": Decimal("100.0001")},
    ],
)
def test_product_bounds_are_database_constraints(demo, fields):
    with pytest.raises(IntegrityError), transaction.atomic():
        CreditProduct.objects.filter(code="working-capital").update(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"revision_no": 0},
        {"amount": 0},
        {"term_months": 0},
        {"term_months": 121},
        {"monthly_revenue": Decimal("-0.01")},
        {"monthly_expenses": Decimal("-0.01")},
        {"monthly_debt_payments": Decimal("-0.01")},
    ],
)
def test_revision_bounds_are_database_constraints(demo, fields):
    app = demo["applications"]["approval"]
    with pytest.raises(IntegrityError), transaction.atomic():
        app.revisions.update(**fields)


def test_revision_number_and_membership_are_unique(demo):
    app = demo["applications"]["approval"]
    with pytest.raises(IntegrityError), transaction.atomic():
        ApplicationRevision.objects.create(
            application=app, revision_no=1, amount=100000, term_months=12, purpose="Дубликат"
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyMember.objects.create(
            user=demo["client"], company=app.company, role=CompanyMember.Role.OWNER
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=demo["client"].pk).update(system_role="administrator")


def test_check_attempt_and_assessment_constraints(demo, reviewed_app):
    revision = reviewed_app.revisions.get()
    check = revision.checks.first()
    with pytest.raises(IntegrityError), transaction.atomic():
        CheckResult.objects.create(
            revision=revision, kind=check.kind, status=check.status, attempt=check.attempt
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        CheckResult.objects.filter(pk=check.pk).update(attempt=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        Assessment.objects.filter(revision=revision).update(score=101)
    with pytest.raises(IntegrityError), transaction.atomic():
        Assessment.objects.create(
            revision=revision, score=90, risk_level="low", rules_version="test"
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"amount": 0},
        {"monthly_payment": 0},
        {"term_months": 0},
        {"term_months": 121},
        {"annual_rate": Decimal("-0.0001")},
        {"annual_rate": Decimal("100.0001")},
    ],
)
def test_offer_bounds_are_database_constraints(offer, fields):
    with pytest.raises(IntegrityError), transaction.atomic():
        Offer.objects.filter(pk=offer.pk).update(**fields)


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", Decimal("1.00")),
        ("annual_rate", Decimal("1.0000")),
        ("term_months", 1),
        ("monthly_payment", Decimal("1.00")),
        ("schedule", {"rows": []}),
    ],
)
def test_offer_terms_cannot_be_edited_through_model_save(offer, field, value):
    original = getattr(offer, field)
    setattr(offer, field, value)
    with pytest.raises(ValidationError):
        offer.save()
    offer.refresh_from_db()
    assert getattr(offer, field) == original


@pytest.mark.parametrize("field", ["terms_snapshot", "document_hash", "number", "signature_mode"])
def test_agreement_terms_cannot_be_edited_through_model_save(agreement, field):
    setattr(agreement, field, {} if field == "terms_snapshot" else "changed")
    with pytest.raises(ValidationError):
        agreement.save()


@pytest.mark.parametrize("fields", [{"signed_at": timezone.now()}, {"signature_mode": "real"}])
def test_agreement_requires_paired_signature_and_simulation_mode(agreement, fields):
    with pytest.raises(IntegrityError), transaction.atomic():
        Agreement.objects.filter(pk=agreement.pk).update(**fields)


def test_signed_agreement_cannot_be_rewritten(signed_deal):
    with pytest.raises(ValidationError):
        signed_deal.save()
    with pytest.raises(IntegrityError), transaction.atomic():
        Agreement.objects.filter(pk=signed_deal.pk).update(signed_by=None)


@pytest.mark.parametrize("fields", [{"amount": 0}, {"is_simulated": False}, {"status": "pending"}])
def test_disbursement_is_positive_completed_and_simulated(demo, signed_deal, fields):
    app = signed_deal.offer.decision.assessment.revision.application
    record = disburse(demo["specialist"], signed_deal.id, app.lock_version, uuid.uuid4())
    with pytest.raises(IntegrityError), transaction.atomic():
        Disbursement.objects.filter(pk=record.pk).update(**fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        Disbursement.objects.create(
            agreement=signed_deal, amount=record.amount, idempotency_key=uuid.uuid4()
        )


@pytest.mark.parametrize(
    "model", [CheckResult, Assessment, CreditDecision, ApplicationEvent, Disbursement]
)
def test_historical_models_reject_save_and_delete(demo, signed_deal, model):
    app = signed_deal.offer.decision.assessment.revision.application
    disburse(demo["specialist"], signed_deal.id, app.lock_version, uuid.uuid4())
    record = model.objects.first()
    with pytest.raises(ValidationError):
        record.save()
    with pytest.raises(ValidationError):
        record.delete()
    assert model.objects.filter(pk=record.pk).exists()


@pytest.mark.parametrize(
    "model",
    [
        Application,
        ApplicationRevision,
        CheckResult,
        Assessment,
        CreditDecision,
        Offer,
        Agreement,
        Disbursement,
    ],
)
def test_admin_cannot_mutate_financial_records(demo, model):
    request = RequestFactory().get("/admin/")
    request.user = demo["specialist"]
    model_admin = admin.site._registry[model]
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
    assert set(model_admin.get_readonly_fields(request)) == {
        field.name for field in model._meta.fields
    }

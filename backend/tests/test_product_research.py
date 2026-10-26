import copy
import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection

from agreements import services as agreements
from agreements.documents import generate_document
from agreements.models import Agreement
from applications import services
from offers.models import Offer
from products.calculations import payment_schedule
from products.models import CreditProduct
from products.presentation import cost_breakdown
from tests.test_api_edges import request
from tests.test_frontend_contract import assert_response


@pytest.mark.parametrize("amount", ["300000.00", "1500000.00", "30000000.00"])
@pytest.mark.parametrize("rate", ["0.0000", "27.0000", "100.0000"])
@pytest.mark.parametrize("months", [12, 24, 60])
def test_cost_reconciles_to_actual_rounded_schedule(amount, rate, months):
    _, schedule = payment_schedule(Decimal(amount), Decimal(rate), months)
    value = cost_breakdown(amount, schedule)
    assert value["is_complete"]
    assert Decimal(value["total_repayment"]) == sum(Decimal(r["payment"]) for r in schedule["rows"])
    assert Decimal(value["total_repayment"]) == Decimal(amount) + Decimal(value["interest_total"])
    assert Decimal(value["total_cost"]) == Decimal(value["interest_total"])
    assert value["net_disbursement"] == amount
    assert value["fees_total"] == value["services_total"] == "0.00"
    assert value["last_payment"] == schedule["rows"][-1]["payment"]
    assert Decimal(schedule["rows"][-1]["balance"]) == 0


@pytest.mark.parametrize("fee", [None, "unknown", "5000.00"])
def test_unknown_or_unsupported_fees_never_become_zero_or_complete(fee):
    _, schedule = payment_schedule(Decimal("1000000"), Decimal("27"), 24)
    schedule["fees"] = fee
    value = cost_breakdown("1000000", schedule)
    assert value["is_complete"] is False
    assert value["total_repayment"] is None
    assert value["fees_total"] is value["services_total"] is value["net_disbursement"] is None
    assert Decimal(value["known_payments_total"]) > 1000000


def test_catalog_quote_uses_server_rate_and_exposes_evidence(demo, api):
    app = demo["applications"]["approval"]
    product = CreditProduct.objects.get(pk=app.product_id)
    catalog = request(api, demo["client"], "get", f"products/{product.pk}/").json()
    assert catalog["annual_rate"] == "27.0000"
    assert catalog["min_amount"] == "300000.00" and catalog["max_amount"] == "30000000.00"
    assert catalog["catalog_reference"]["advertised_rate_from"] == "23.5000"
    assert catalog["catalog_reference"]["effective_from"] is None
    data = {"product": str(product.pk), "amount": "1500000.00", "term_months": 24}
    quoted = request(api, demo["client"], "post", "calculator/payment/", data).json()
    assert quoted["monthly_payment"] == "81570.34"
    assert quoted["annual_rate"] == "27.0000"
    assert quoted["rate_source"] == "demo_assumption"
    assert quoted["catalog_version"] == product.rules_version
    assert quoted["cost_breakdown"]["is_complete"]
    schema = api.get("/api/schema/?format=json").json()
    assert_response(schema, catalog, "/api/v1/products/{id}/")
    assert_response(schema, quoted, "/api/v1/calculator/payment/", "post")
    request(
        api,
        demo["client"],
        "post",
        "calculator/payment/",
        {**data, "annual_rate": "1"},
        expected=400,
    )
    request(
        api,
        demo["client"],
        "post",
        "calculator/payment/",
        {**data, "amount": "299999.99"},
        expected=400,
    )
    request(
        api,
        demo["client"],
        "post",
        "calculator/payment/",
        {"amount": "1000000", "term_months": 24},
        expected=400,
    )


def test_readiness_distinguishes_zero_missing_and_permissions(demo, api):
    app = demo["applications"]["needs_info"]
    client = request(api, demo["client"], "get", f"applications/{app.pk}/").json()
    assert client["readiness"]["can_submit"]
    assert not client["readiness"]["financial_data_complete"]
    assert {x["state"] for x in client["readiness"]["items"]} == {"missing"}
    data = {"lock_version": 0, "monthly_debt_payments": "0.00"}
    updated = request(api, demo["client"], "patch", f"applications/{app.pk}/", data).json()
    assert {x["field"]: x["state"] for x in updated["readiness"]["items"]} == {
        "monthly_revenue": "missing",
        "monthly_expenses": "missing",
        "monthly_debt_payments": "ready",
    }
    staff = request(api, demo["specialist"], "get", f"staff/applications/{app.pk}/").json()
    assert not staff["readiness"]["can_submit"]
    request(api, demo["outsider"], "get", f"applications/{app.pk}/", expected=404)
    request(
        api,
        demo["client"],
        "patch",
        f"applications/{app.pk}/",
        {"lock_version": 1, "readiness": {"financial_data_complete": True}},
        expected=400,
    )


def _decide(demo, app):
    services.submit_application(demo["client"], app.id, app.lock_version)
    app.refresh_from_db()
    services.claim_application(demo["specialist"], app.id, app.lock_version)
    app.refresh_from_db()
    services.make_decision(demo["specialist"], app.id, app.lock_version)
    app.refresh_from_db()
    return Offer.objects.get(decision__assessment__revision__application=app)


def test_counteroffer_comparison_uses_reviewed_revision_and_freezes_price(demo, api):
    app = demo["applications"]["counteroffer"]
    services.update_draft(
        demo["client"],
        app.id,
        {
            "lock_version": 0,
            "amount": Decimal("1500000"),
            "monthly_revenue": Decimal("500000"),
            "monthly_expenses": Decimal("320000"),
            "monthly_debt_payments": Decimal("30000"),
        },
    )
    app.refresh_from_db()
    offer = _decide(demo, app)
    before = request(api, demo["client"], "get", f"offers/{offer.pk}/").json()
    comparison = before["comparison"]
    assert comparison["source_revision_id"] == str(offer.decision.assessment.revision_id)
    assert comparison["requested"]["monthly_payment"] == "81570.34"
    assert Decimal(comparison["proposed"]["monthly_payment"]) <= Decimal("60000")
    assert Decimal(comparison["proposed"]["amount"]) < Decimal(comparison["requested"]["amount"])
    assert set(comparison["changed_fields"]) == {"amount", "monthly_payment"}
    assert comparison["requested"]["term_months"] == comparison["proposed"]["term_months"] == 24
    CreditProduct.objects.filter(pk=app.product_id).update(
        annual_rate=Decimal("35"), rules_version="future-catalog"
    )
    assert request(api, demo["client"], "get", f"offers/{offer.pk}/").json() == before
    agreements.respond_to_offer(demo["client"], offer.pk, app.lock_version, accept=True)
    agreement = Agreement.objects.get(offer=offer)
    assert agreement.terms_snapshot["cost_breakdown"] == before["cost_breakdown"]
    assert agreement.terms_snapshot["catalog_version"] == "research-2026-10-25"
    assert agreements.terms_hash(agreement.terms_snapshot) == agreement.document_hash


def test_catalog_migration_preserves_existing_agreement_and_custom_products(demo, api):
    app = demo["applications"]["approval"]
    CreditProduct.objects.filter(pk=app.product_id).update(
        min_amount=100000,
        max_amount=5000000,
        min_term_months=6,
        max_term_months=36,
        annual_rate=18,
        rules_version="demo-1",
        catalog_reference=None,
    )
    equipment = CreditProduct.objects.get(code="equipment")
    CreditProduct.objects.filter(pk=equipment.pk).update(
        annual_rate=17, rules_version="demo-1", catalog_reference=None
    )
    offer = _decide(demo, app)
    agreements.respond_to_offer(demo["client"], offer.pk, app.lock_version, accept=True)
    agreement = Agreement.objects.get(offer=offer)
    snapshot = copy.deepcopy(agreement.terms_snapshot)
    digest = agreement.document_hash
    original = generate_document(demo["client"], agreement.pk)
    original_bytes = bytes(original.pdf_data)
    pdf_digest = original.pdf_sha256
    migration = importlib.import_module("products.migrations.0003_research_catalog")
    migration.upgrade_catalog(apps, SimpleNamespace(connection=connection))
    migration.upgrade_catalog(apps, SimpleNamespace(connection=connection))
    product = CreditProduct.objects.get(pk=app.product_id)
    assert product.annual_rate == Decimal("27")
    assert product.catalog_reference["value_type"] == "public_product"
    equipment.refresh_from_db()
    assert equipment.annual_rate == Decimal("17") and equipment.catalog_reference is None
    agreement.refresh_from_db()
    offer.refresh_from_db()
    assert offer.annual_rate == Decimal("18")
    assert agreement.terms_snapshot == snapshot and agreement.document_hash == digest
    original.refresh_from_db()
    assert bytes(original.pdf_data) == original_bytes and original.pdf_sha256 == pdf_digest
    assert generate_document(demo["client"], agreement.pk).pk == original.pk
    data = request(api, demo["client"], "get", f"offers/{offer.pk}/").json()
    assert data["comparison"]["catalog_version"] == "demo-1"
    assert data["comparison"]["requested"]["annual_rate"] == "18.0000"

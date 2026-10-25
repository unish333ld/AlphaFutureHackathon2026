import uuid
from decimal import Decimal

import pytest

from agreements.models import Agreement, Disbursement
from applications.models import Application
from companies.models import Company
from offers.models import Offer
from products.models import CreditProduct


def request(api, user, method, path, data=None, expected=200, **headers):
    api.force_authenticate(user=user)
    url = f"/api/v1/{path}"
    if method == "get":
        response = api.get(url, data, **headers)
    else:
        response = getattr(api, method)(url, data, format="json", **headers)
    assert response.status_code == expected, getattr(response, "data", response.content)
    return response


def application_data(app, **overrides):
    return {
        "company": str(app.company_id),
        "product": str(app.product_id),
        "amount": "1000000.00",
        "term_months": 24,
        "purpose": "Проверка API",
        "monthly_revenue": "1500000.00",
        "monthly_expenses": "900000.00",
        "monthly_debt_payments": "50000.00",
        **overrides,
    }


def test_create_and_update_draft_persist_with_versioned_event(demo, api):
    source = demo["applications"]["approval"]
    data = application_data(source)
    response = request(api, demo["client"], "post", "applications/", data, expected=201)
    created = Application.objects.get(pk=response.data["id"])
    assert response.data["status"] == "draft"
    assert response.data["lock_version"] == 0
    assert created.revisions.get().input_snapshot == {}
    assert created.events.get().event_type == "created"

    update = request(
        api,
        demo["client"],
        "patch",
        f"applications/{created.id}/",
        {"lock_version": 0, "amount": "1250000.00", "purpose": "Новая цель"},
    )
    revision = created.revisions.get()
    assert update.data["lock_version"] == 1
    assert revision.amount == Decimal("1250000.00")
    assert revision.purpose == "Новая цель"
    assert created.events.order_by("created_at").last().event_type == "draft_updated"

    request(
        api,
        demo["client"],
        "patch",
        f"applications/{created.id}/",
        {"lock_version": 0, "amount": "1300000.00"},
        expected=409,
    )
    request(
        api,
        demo["client"],
        "patch",
        f"applications/{created.id}/",
        {"lock_version": 1, "amount": "9999999.00"},
        expected=400,
    )
    revision.refresh_from_db()
    assert revision.amount == Decimal("1250000.00")


def test_create_rejects_foreign_company_and_ineligible_product(demo, api):
    source = demo["applications"]["approval"]
    data = application_data(source)
    request(
        api,
        demo["outsider"],
        "post",
        "applications/",
        {**data, "company": str(source.company_id)},
        expected=404,
    )

    Company.objects.filter(pk=source.company_id).update(is_existing_client=False)
    request(api, demo["client"], "post", "applications/", data, expected=400)

    Company.objects.filter(pk=source.company_id).update(is_existing_client=True)
    CreditProduct.objects.filter(pk=source.product_id).update(active=False)
    request(api, demo["client"], "post", "applications/", data, expected=400)
    assert Application.objects.count() == 5


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "99999.99"},
        {"amount": "5000000.01"},
        {"term_months": 5},
        {"term_months": 37},
        {"monthly_revenue": "-0.01"},
        {"term_months": 24, "admin": True},
    ],
)
def test_create_rejects_invalid_amount_term_finances_and_unknown_fields(demo, api, changes):
    source = demo["applications"]["approval"]
    request(
        api,
        demo["client"],
        "post",
        "applications/",
        application_data(source, **changes),
        expected=400,
    )
    assert Application.objects.count() == 5


def test_company_product_and_staff_lists_are_role_scoped(demo, api):
    client_companies = request(api, demo["client"], "get", "companies/").data["count"]
    assert client_companies == 5
    assert request(api, demo["specialist"], "get", "companies/").data["count"] == 6
    assert request(api, demo["outsider"], "get", "companies/").data["count"] == 1

    specialist_queue = request(api, demo["specialist"], "get", "staff/applications/")
    assert specialist_queue.data["count"] == 5
    request(api, demo["client"], "get", "staff/applications/", expected=403)
    request(api, demo["specialist"], "get", "applications/?status=unknown", expected=400)
    filtered = request(api, demo["client"], "get", "applications/?status=draft")
    assert filtered.data["count"] == 5

    CreditProduct.objects.filter(code="equipment").update(active=False)
    assert request(api, demo["client"], "get", "products/").data["count"] == 1


def test_only_specialist_can_make_a_credit_decision(demo, api):
    app = demo["applications"]["approval"]
    request(api, demo["client"], "post", f"applications/{app.id}/submit/", {"lock_version": 0})
    app.refresh_from_db()
    for user in (demo["client"], demo["accountant"]):
        request(
            api,
            user,
            "post",
            f"staff/applications/{app.id}/decide/",
            {"lock_version": app.lock_version},
            expected=403,
        )
    decided = request(
        api,
        demo["specialist"],
        "post",
        f"staff/applications/{app.id}/claim/",
        {"lock_version": app.lock_version},
    )
    app.refresh_from_db()
    decided = request(
        api,
        demo["specialist"],
        "post",
        f"staff/applications/{app.id}/decide/",
        {"lock_version": app.lock_version},
    )
    assert decided.data["status"] == "offered"


@pytest.mark.parametrize(
    "data",
    [
        {"amount": "0.99", "annual_rate": "18", "term_months": 12},
        {"amount": "1000", "annual_rate": "100.0001", "term_months": 12},
        {"amount": "1000", "annual_rate": "18", "term_months": 121},
        {"amount": "1000", "annual_rate": "18", "term_months": 12, "status": "issued"},
    ],
)
def test_calculator_validates_bounds_and_rejects_injection(demo, api, data):
    request(api, demo["client"], "post", "calculator/payment/", data, expected=400)


def test_calculator_returns_complete_zero_rate_schedule(demo, api):
    response = request(
        api,
        demo["client"],
        "post",
        "calculator/payment/",
        {"amount": "1200.00", "annual_rate": "0.0000", "term_months": 12},
    )
    assert response.data["monthly_payment"] == "100.00"
    assert len(response.data["schedule"]["rows"]) == 12
    assert response.data["schedule"]["rows"][-1]["balance"] == "0.00"


def test_session_login_rejects_bad_credentials_and_extra_fields(demo, api):
    request(
        api,
        demo["client"],
        "post",
        "session/login/",
        {"username": "client", "password": "wrong-password"},
        expected=403,
    )
    request(
        api,
        demo["client"],
        "post",
        "session/login/",
        {"username": "client", "password": "TestsOnly2026!password", "system_role": "specialist"},
        expected=400,
    )


def test_sign_rejects_database_tampering_of_frozen_terms(demo, api):
    app = demo["applications"]["approval"]
    app.refresh_from_db()
    request(api, demo["client"], "post", f"applications/{app.id}/submit/", {"lock_version": 0})
    app.refresh_from_db()
    request(
        api,
        demo["specialist"],
        "post",
        f"staff/applications/{app.id}/claim/",
        {"lock_version": app.lock_version},
    )
    app.refresh_from_db()
    result = request(
        api,
        demo["specialist"],
        "post",
        f"staff/applications/{app.id}/decide/",
        {"lock_version": app.lock_version},
    )
    offer = result.data["revisions"][0]["assessment"]["decision"]["offer"]
    app.refresh_from_db()
    result = request(
        api,
        demo["client"],
        "post",
        f"offers/{offer['id']}/accept/",
        {"lock_version": app.lock_version},
    )
    agreement_data = result.data["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
    agreement = Agreement.objects.get(pk=agreement_data["id"])
    changed_terms = {**agreement.terms_snapshot, "amount": "1.00"}
    Agreement.objects.filter(pk=agreement.pk).update(terms_snapshot=changed_terms)

    request(
        api,
        demo["client"],
        "post",
        f"agreements/{agreement.id}/sign/",
        {
            "lock_version": result.data["lock_version"],
            "document_hash": agreement.document_hash,
            "confirm_simulation": True,
        },
        expected=409,
    )
    agreement.refresh_from_db()
    assert agreement.signed_at is None
    assert not Disbursement.objects.exists()


def test_disbursement_requires_valid_idempotency_uuid_and_matches_frozen_amount(demo, api):
    app = demo["applications"]["approval"]
    request(api, demo["client"], "post", f"applications/{app.id}/submit/", {"lock_version": 0})
    app.refresh_from_db()
    request(
        api,
        demo["specialist"],
        "post",
        f"staff/applications/{app.id}/claim/",
        {"lock_version": app.lock_version},
    )
    app.refresh_from_db()
    result = request(
        api,
        demo["specialist"],
        "post",
        f"staff/applications/{app.id}/decide/",
        {"lock_version": app.lock_version},
    )
    offer = result.data["revisions"][0]["assessment"]["decision"]["offer"]
    app.refresh_from_db()
    result = request(
        api,
        demo["client"],
        "post",
        f"offers/{offer['id']}/accept/",
        {"lock_version": app.lock_version},
    )
    agreement_data = result.data["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
    request(
        api,
        demo["client"],
        "post",
        f"agreements/{agreement_data['id']}/sign/",
        {
            "lock_version": result.data["lock_version"],
            "document_hash": agreement_data["document_hash"],
            "confirm_simulation": True,
        },
    )
    app.refresh_from_db()
    request(
        api,
        demo["specialist"],
        "post",
        f"agreements/{agreement_data['id']}/disburse/",
        {"lock_version": app.lock_version},
        expected=400,
    )

    agreement = Agreement.objects.get(pk=agreement_data["id"])
    Offer.objects.filter(pk=agreement.offer_id).update(amount=Decimal("1000001.00"))
    request(
        api,
        demo["specialist"],
        "post",
        f"agreements/{agreement.id}/disburse/",
        {"lock_version": app.lock_version},
        expected=400,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    app.refresh_from_db()
    assert app.status == "signed"
    assert not Disbursement.objects.exists()

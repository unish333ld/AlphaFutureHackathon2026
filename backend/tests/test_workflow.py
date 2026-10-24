import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from agreements.models import Agreement, Disbursement
from agreements.services import disburse
from applications.models import Application, ApplicationRevision
from common.exceptions import Conflict
from offers.models import Offer
from products.calculations import annuity_payment, payment_schedule


def post(api, user, path, data, expected=200, **headers):
    api.force_authenticate(user=user)
    response = api.post(f"/api/v1/{path}", data, format="json", **headers)
    assert response.status_code == expected, response.data
    return response.data


def app_action(api, user, app, action, *, staff=False, **payload):
    app.refresh_from_db()
    prefix = "staff/" if staff else ""
    return post(
        api,
        user,
        f"{prefix}applications/{app.id}/{action}/",
        {"lock_version": app.lock_version, **payload},
    )


def offer_for(api, demo, app):
    app_action(api, demo["client"], app, "submit")
    app_action(api, demo["specialist"], app, "claim", staff=True)
    result = app_action(api, demo["specialist"], app, "decide", staff=True)
    return result["revisions"][0]["assessment"]["decision"]["offer"]


def signed_agreement(api, demo, app):
    offer = offer_for(api, demo, app)
    app.refresh_from_db()
    result = post(
        api, demo["client"], f"offers/{offer['id']}/accept/", {"lock_version": app.lock_version}
    )
    agreement = result["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
    post(
        api,
        demo["client"],
        f"agreements/{agreement['id']}/sign/",
        {
            "lock_version": result["lock_version"],
            "document_hash": agreement["document_hash"],
            "confirm_simulation": True,
        },
    )
    app.refresh_from_db()
    return agreement


def financial_data():
    return {
        "amount": "1000000.00",
        "term_months": 24,
        "purpose": "Оборотные средства",
        "monthly_revenue": "1500000.00",
        "monthly_expenses": "900000.00",
        "monthly_debt_payments": "50000.00",
    }


def test_complete_flow_idempotency_and_persistence(demo, api):
    app = demo["applications"]["approval"]
    agreement = signed_agreement(api, demo, app)
    key = str(uuid.uuid4())
    path = f"agreements/{agreement['id']}/disburse/"
    result = post(
        api, demo["specialist"], path, {"lock_version": app.lock_version}, HTTP_IDEMPOTENCY_KEY=key
    )
    repeated = post(
        api, demo["specialist"], path, {"lock_version": app.lock_version}, HTTP_IDEMPOTENCY_KEY=key
    )
    assert result == repeated
    assert result["amount"] == "1000000.00" and result["is_simulated"] is True
    app.refresh_from_db()
    assert app.status == "issued" and Disbursement.objects.count() == 1
    post(
        api,
        demo["specialist"],
        path,
        {"lock_version": app.lock_version},
        expected=409,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    api.force_authenticate(user=demo["client"])
    reloaded = api.get(f"/api/v1/applications/{app.id}/").data
    assert reloaded["status"] == "issued"
    assert (
        reloaded["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]["disbursement"][
            "id"
        ]
        == result["id"]
    )
    assert list(
        app.events.exclude(event_type__startswith="assignment_").values_list("to_status", flat=True)
    ) == [
        "draft",
        "submitted",
        "checking",
        "review",
        "offered",
        "accepted",
        "signed",
        "issued",
    ]


def test_missing_information_creates_new_revision(demo, api):
    app = demo["applications"]["needs_info"]
    result = app_action(api, demo["client"], app, "submit")
    assert result["status"] == "needs_info"
    old = app.revisions.first()
    old_snapshot = old.input_snapshot.copy()
    result = app_action(api, demo["client"], app, "provide-information", **financial_data())
    assert result["status"] == "review" and result["revisions"][0]["revision_no"] == 2
    old.refresh_from_db()
    assert old.input_snapshot == old_snapshot and old.monthly_revenue is None
    assert old.information_requests.get().response_revision.revision_no == 2


def test_counteroffer_respects_affordability(demo, api):
    app = demo["applications"]["counteroffer"]
    offer = offer_for(api, demo, app)
    assert Decimal("100000") <= Decimal(offer["amount"]) < Decimal("1000000")
    assert Decimal(offer["monthly_payment"]) <= Decimal("30000.00")
    assert Offer.objects.get(pk=offer["id"]).decision.outcome == "counteroffer"


def test_negative_check_is_explained_rejection(demo, api):
    app = demo["applications"]["rejected"]
    app_action(api, demo["client"], app, "submit")
    app_action(api, demo["specialist"], app, "claim", staff=True)
    result = app_action(api, demo["specialist"], app, "decide", staff=True)
    decision = result["revisions"][0]["assessment"]["decision"]
    assert result["status"] == "rejected" and decision["reason_code"] == "negative_check"
    assert decision["offer"] is None


def test_technical_error_can_retry_without_credit_rejection(demo, api):
    app = demo["applications"]["check_error"]
    result = app_action(api, demo["client"], app, "submit")
    assert result["status"] == "checking"
    assert result["revisions"][0]["assessment"] is None
    assert any(check["status"] == "error" for check in result["revisions"][0]["checks"])
    result = app_action(api, demo["client"], app, "retry-checks")
    assert result["status"] == "review" and len(result["revisions"][0]["checks"]) == 6


def test_staff_information_request_after_assessment(demo, api):
    app = demo["applications"]["approval"]
    app_action(api, demo["client"], app, "submit")
    app_action(api, demo["specialist"], app, "claim", staff=True)
    result = app_action(
        api,
        demo["specialist"],
        app,
        "request-information",
        staff=True,
        question="Уточните месячные расходы",
    )
    assert result["status"] == "needs_info"
    result = app_action(api, demo["client"], app, "provide-information", **financial_data())
    assert result["revisions"][0]["revision_no"] == 2
    assert app.revisions.get(revision_no=1).assessment is not None


def test_old_offer_cannot_be_accepted_after_revision(demo, api):
    app = demo["applications"]["approval"]
    offer = offer_for(api, demo, app)
    app_action(api, demo["client"], app, "revise", **financial_data())
    app.refresh_from_db()
    post(
        api,
        demo["client"],
        f"offers/{offer['id']}/accept/",
        {"lock_version": app.lock_version},
        expected=409,
    )
    assert Offer.objects.get(pk=offer["id"]).status == "superseded"


def test_expired_offer_is_recorded_and_rejected(demo, api):
    app = demo["applications"]["approval"]
    offer = offer_for(api, demo, app)
    Offer.objects.filter(pk=offer["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
    api.force_authenticate(user=demo["client"])
    assert api.get(f"/api/v1/offers/{offer['id']}/").data["status"] == "expired"
    app.refresh_from_db()
    post(
        api,
        demo["client"],
        f"offers/{offer['id']}/accept/",
        {"lock_version": app.lock_version},
        expected=409,
    )
    assert app.status == "expired"


def test_decline_offer(demo, api):
    app = demo["applications"]["approval"]
    offer = offer_for(api, demo, app)
    app.refresh_from_db()
    result = post(
        api, demo["client"], f"offers/{offer['id']}/decline/", {"lock_version": app.lock_version}
    )
    assert result["status"] == "declined" and not Agreement.objects.exists()


def test_sign_requires_permission_and_exact_hash(demo, api):
    app = demo["applications"]["approval"]
    offer = offer_for(api, demo, app)
    app.refresh_from_db()
    result = post(
        api, demo["client"], f"offers/{offer['id']}/accept/", {"lock_version": app.lock_version}
    )
    agreement = result["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
    payload = {
        "lock_version": result["lock_version"],
        "document_hash": agreement["document_hash"],
        "confirm_simulation": True,
    }
    path = f"agreements/{agreement['id']}/sign/"
    post(api, demo["accountant"], path, payload, expected=403)
    post(api, demo["client"], path, {**payload, "document_hash": "0" * 64}, expected=409)
    post(api, demo["client"], path, {**payload, "confirm_simulation": False}, expected=400)
    assert Agreement.objects.get(pk=agreement["id"]).signed_at is None
    post(
        api,
        demo["client"],
        f"agreements/{agreement['id']}/disburse/",
        {"lock_version": result["lock_version"]},
        expected=403,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )


def test_unsigned_agreement_cannot_be_disbursed(demo, api):
    app = demo["applications"]["approval"]
    offer = offer_for(api, demo, app)
    app.refresh_from_db()
    result = post(
        api, demo["client"], f"offers/{offer['id']}/accept/", {"lock_version": app.lock_version}
    )
    agreement = result["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
    post(
        api,
        demo["specialist"],
        f"agreements/{agreement['id']}/disburse/",
        {"lock_version": result["lock_version"]},
        expected=409,
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert not Disbursement.objects.exists()


def test_cross_company_access_list_detail_actions_and_history(demo, api):
    app = demo["applications"]["approval"]
    agreement = signed_agreement(api, demo, app)
    issuance = post(
        api,
        demo["specialist"],
        f"agreements/{agreement['id']}/disburse/",
        {"lock_version": app.lock_version},
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    api.force_authenticate(user=demo["outsider"])
    for resource in ["applications", "offers", "agreements", "disbursements"]:
        assert api.get(f"/api/v1/{resource}/").data["count"] == 0
    assert api.get(f"/api/v1/applications/{app.id}/").status_code == 404
    assert api.get(f"/api/v1/applications/{app.id}/events/").status_code == 404
    assert api.get(f"/api/v1/agreements/{agreement['id']}/").status_code == 404
    assert api.get(f"/api/v1/offers/{agreement['offer']}/").status_code == 404
    assert api.get(f"/api/v1/disbursements/{issuance['id']}/").status_code == 404
    assert api.get("/api/v1/staff/applications/").status_code == 403
    post(api, demo["outsider"], f"applications/{app.id}/submit/", {"lock_version": 0}, expected=404)


def test_field_injection_and_stale_version(demo, api):
    app = demo["applications"]["approval"]
    api.force_authenticate(user=demo["client"])
    response = api.patch(
        f"/api/v1/applications/{app.id}/",
        {
            "lock_version": 0,
            "status": "issued",
            "annual_rate": "0",
            "created_by": str(demo["specialist"].id),
        },
        format="json",
    )
    assert response.status_code == 400 and "status" in response.data
    result = app_action(api, demo["client"], app, "submit")
    post(
        api,
        demo["specialist"],
        f"staff/applications/{app.id}/decide/",
        {"lock_version": 0},
        expected=409,
    )
    app.refresh_from_db()
    assert app.status == "review" and app.lock_version == result["lock_version"]


def test_csrf_login_rotation_authenticated_write_and_logout(demo):
    client = APIClient(enforce_csrf_checks=True)
    path = "/api/v1/session/login/"
    credentials = {"username": "client", "password": "TestsOnly2026!password"}
    assert client.post(path, credentials, format="json").status_code == 403
    token = client.get("/api/v1/session/csrf/").data["csrf_token"]
    response = client.post(path, credentials, format="json", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200
    assert response.cookies["sessionid"]["httponly"]
    rotated = response.data["csrf_token"]
    assert rotated != token
    data = {
        "company": str(uuid.UUID(int=1)),
        "product": str(uuid.UUID(int=101)),
        **financial_data(),
    }
    assert client.post("/api/v1/applications/", data, format="json").status_code == 403
    assert (
        client.post(
            "/api/v1/applications/", data, format="json", HTTP_X_CSRFTOKEN=rotated
        ).status_code
        == 201
    )
    assert client.post("/api/v1/session/logout/", HTTP_X_CSRFTOKEN=rotated).status_code == 204
    assert client.get("/api/v1/me/").status_code == 403


def test_submitted_revision_and_financial_history_are_immutable(demo, api):
    app = demo["applications"]["approval"]
    app_action(api, demo["client"], app, "submit")
    revision = app.revisions.first()
    revision.amount += Decimal(1)
    with pytest.raises(ValidationError):
        revision.save()
    event = app.events.first()
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ProtectedError):
        demo["client"].delete()
    with transaction.atomic(), pytest.raises(IntegrityError):
        ApplicationRevision.objects.create(
            application=app, revision_no=2, amount=-1, term_months=24, purpose="invalid"
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_disbursement_is_serialized_by_postgres(demo, api, same_key):
    assert connection.vendor == "postgresql"
    app = demo["applications"]["approval"]
    agreement = signed_agreement(api, demo, app)
    keys = [uuid.uuid4(), uuid.uuid4()]
    if same_key:
        keys[1] = keys[0]
    barrier = Barrier(2)

    def issue(key):
        close_old_connections()
        try:
            specialist = User.objects.get(pk=demo["specialist"].id)
            barrier.wait(timeout=10)
            try:
                return str(disburse(specialist, agreement["id"], app.lock_version, key).id)
            except Conflict:
                return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue, keys))
    assert Disbursement.objects.count() == 1
    assert len(set(results)) == 1 if same_key else results.count("conflict") == 1


def test_seed_is_idempotent(demo):
    before = (User.objects.count(), Application.objects.count())
    call_command("seed_demo", verbosity=0)
    assert (User.objects.count(), Application.objects.count()) == before


def test_decision_uses_product_snapshot(demo, api):
    app = demo["applications"]["approval"]
    app_action(api, demo["client"], app, "submit")
    app_action(api, demo["specialist"], app, "claim", staff=True)
    original_rate = app.product.annual_rate
    app.product.annual_rate += Decimal(1)
    app.product.save()
    result = app_action(api, demo["specialist"], app, "decide", staff=True)
    assert (
        Decimal(result["revisions"][0]["assessment"]["decision"]["offer"]["annual_rate"])
        == original_rate
    )


def test_same_key_cannot_issue_another_agreement(demo, api):
    first_app = demo["applications"]["approval"]
    second_app = demo["applications"]["counteroffer"]
    first = signed_agreement(api, demo, first_app)
    second = signed_agreement(api, demo, second_app)
    key = str(uuid.uuid4())
    post(
        api,
        demo["specialist"],
        f"agreements/{first['id']}/disburse/",
        {"lock_version": first_app.lock_version},
        HTTP_IDEMPOTENCY_KEY=key,
    )
    post(
        api,
        demo["specialist"],
        f"agreements/{second['id']}/disburse/",
        {"lock_version": second_app.lock_version},
        expected=409,
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert Disbursement.objects.count() == 1
    second_app.refresh_from_db()
    assert second_app.status == "signed"


def test_signing_deadline_expires_without_signature(demo, api):
    app = demo["applications"]["approval"]
    offer = offer_for(api, demo, app)
    app.refresh_from_db()
    result = post(
        api, demo["client"], f"offers/{offer['id']}/accept/", {"lock_version": app.lock_version}
    )
    agreement = result["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
    Offer.objects.filter(pk=offer["id"]).update(sign_before=timezone.now() - timedelta(seconds=1))
    post(
        api,
        demo["client"],
        f"agreements/{agreement['id']}/sign/",
        {
            "lock_version": result["lock_version"],
            "document_hash": agreement["document_hash"],
            "confirm_simulation": True,
        },
        expected=409,
    )
    app.refresh_from_db()
    assert app.status == "expired" and Agreement.objects.get(pk=agreement["id"]).signed_at is None


def test_company_member_without_submit_capability(demo, api):
    app = demo["applications"]["approval"]
    demo["client"].memberships.filter(company=app.company).update(can_submit=False)
    post(api, demo["client"], f"applications/{app.id}/submit/", {"lock_version": 0}, expected=403)
    app.refresh_from_db()
    assert app.status == "draft"


def test_swagger_schema_and_browser_login_are_accessible(api):
    assert api.get("/api/docs/").status_code == 200
    assert api.get("/api/session/login/").status_code == 200
    schema = api.get("/api/schema/?format=json").json()
    assert "/api/v1/agreements/{id}/disburse/" in schema["paths"]
    for model in (
        "Application",
        "Revision",
        "Check",
        "Assessment",
        "CreditDecision",
        "Offer",
        "Agreement",
        "Disbursement",
    ):
        assert model in schema["components"]["schemas"]


@pytest.mark.parametrize(
    "amount,rate,term",
    [("1000000.00", "18.0000", 24), ("120000.00", "0.0000", 12), ("200000.01", "16.0000", 60)],
)
def test_payment_schedule_conserves_principal(amount, rate, term):
    payment, schedule = payment_schedule(Decimal(amount), Decimal(rate), term)
    assert payment == annuity_payment(Decimal(amount), Decimal(rate), term)
    assert sum(Decimal(row["principal"]) for row in schedule["rows"]) == Decimal(amount)
    assert schedule["rows"][-1]["balance"] == "0.00"

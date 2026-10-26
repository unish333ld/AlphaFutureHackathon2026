import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import IntegrityError, OperationalError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import User
from agreements import services as deals
from agreements.models import Disbursement
from applications import services
from applications.models import Application, ApplicationRevision
from checks.adapters import run_synthetic_checks
from checks.models import CheckResult
from common.exceptions import Conflict
from companies.models import CompanyMember
from decisions.models import Assessment, CreditDecision
from offers.models import Offer
from tests.signing import sign_with_code


@pytest.fixture
def second_specialist(demo):
    return User.objects.create_user(username="specialist-2", system_role="specialist")


def post(api, user, app, action, *, expected=200, payload=None):
    app.refresh_from_db()
    api.force_authenticate(user=user)
    response = api.post(
        f"/api/v1/staff/applications/{app.pk}/{action}/",
        {"lock_version": app.lock_version} if payload is None else payload,
        format="json",
    )
    assert response.status_code == expected, response.data
    return response.json()


def hints(api, user, app):
    api.force_authenticate(user=user)
    response = api.get(f"/api/v1/applications/{app.pk}/")
    assert response.status_code == 200
    return {item["action"]: item for item in response.json()["available_actions"]}


def claim(user, app):
    app.refresh_from_db()
    services.claim_application(user, app.pk, app.lock_version)
    app.refresh_from_db()


def revise_data(app):
    app.refresh_from_db()
    revision = app.revisions.first()
    return {
        "lock_version": app.lock_version,
        **{field: getattr(revision, field) for field in services.REVISION_FIELDS},
    }


def test_assignment_is_independent_versioned_and_own_only(
    demo, api, reviewed_app, second_specialist
):
    app = reviewed_app
    before = app.status_changed_at
    first = post(api, demo["specialist"], app, "claim")
    assert first["status"] == "review"
    assert first["assigned_to"]["id"] == str(demo["specialist"].pk)
    assert first["assigned_at"] and first["lock_version"] == app.lock_version + 1
    app.refresh_from_db()
    assert app.status_changed_at == before
    repeated = post(api, demo["specialist"], app, "claim")
    assert repeated["lock_version"] == first["lock_version"]
    assert app.events.filter(event_type="assignment_claimed").count() == 1
    for action in ("claim", "release", "decide", "request-information"):
        data = {"lock_version": app.lock_version}
        if action == "request-information":
            data["question"] = "Нельзя менять чужое назначение"
        result = post(api, second_specialist, app, action, expected=409, payload=data)
        assert result["code"] == "assigned_to_other"
    released = post(api, demo["specialist"], app, "release")
    assert released["assigned_to"] is None and released["assigned_at"] is None
    assert released["status"] == "review" and released["lock_version"] == first["lock_version"] + 1
    post(api, demo["specialist"], app, "release", expected=409)
    claim(second_specialist, app)
    assert app.assigned_to_id == second_specialist.pk
    assert app.status_changed_at == before


@pytest.mark.parametrize(
    "status", ["draft", "submitted", "issued", "rejected", "declined", "expired"]
)
def test_assignment_rejects_ineligible_states(demo, api, status):
    app = demo["applications"]["approval"]
    Application.objects.filter(pk=app.pk).update(status=status)
    result = post(api, demo["specialist"], app, "claim", expected=409)
    assert result["code"] == "invalid_state"
    assert not app.events.filter(event_type="assignment_claimed").exists()


@pytest.mark.parametrize("status", sorted(services.ASSIGNABLE_STATUSES))
def test_assignment_allows_documented_states(demo, api, status):
    scenario = {"checking": "check_error", "needs_info": "needs_info"}.get(status, "approval")
    app = demo["applications"][scenario]
    services.submit_application(demo["client"], app.pk, 0)
    app.refresh_from_db()
    if status in {"offered", "accepted", "signed"}:
        claim(demo["specialist"], app)
        services.make_decision(demo["specialist"], app.pk, app.lock_version)
        app.refresh_from_db()
        offer = Offer.objects.get(decision__assessment__revision=app.revisions.first())
        if status in {"accepted", "signed"}:
            deals.respond_to_offer(demo["client"], offer.pk, app.lock_version, accept=True)
            app.refresh_from_db()
            if status == "signed":
                agreement = offer.agreement
                sign_with_code(
                    demo["client"], agreement.pk, app.lock_version, agreement.document_hash
                )
                app.refresh_from_db()
        services.release_application(demo["specialist"], app.pk, app.lock_version)
    post(api, demo["specialist"], app, "claim")
    post(api, demo["specialist"], app, "release")
    app.refresh_from_db()
    assert app.status == status and app.assigned_to_id is None


@pytest.mark.django_db(transaction=True)
def test_two_specialists_cannot_claim_one_application(demo, reviewed_app, second_specialist):
    assert connection.vendor == "postgresql"
    app = reviewed_app
    initial_version = app.lock_version
    barrier = Barrier(2)

    def acquire(user_id):
        try:
            user = User.objects.get(pk=user_id)
            barrier.wait(timeout=10)
            try:
                services.claim_application(user, app.pk, app.lock_version)
                return str(user_id)
            except Conflict as error:
                return str(error.get_codes())
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(acquire, [demo["specialist"].pk, second_specialist.pk]))
    app.refresh_from_db()
    assert results.count("stale_version") == 1
    assert str(app.assigned_to_id) in results
    assert app.events.filter(event_type="assignment_claimed").count() == 1
    assert app.lock_version == initial_version + 1


@pytest.mark.parametrize("action", ["decide", "request-information"])
def test_bank_actions_need_assignment(demo, api, reviewed_app, action):
    data = {"lock_version": reviewed_app.lock_version}
    if action == "request-information":
        data["question"] = "Нужны дополнительные сведения"
    result = post(api, demo["specialist"], reviewed_app, action, expected=409, payload=data)
    assert result["code"] == "assignment_required"
    assert not CreditDecision.objects.exists()


@pytest.mark.parametrize("action", ["claim", "release", "decide", "request-information"])
def test_client_and_admin_flag_do_not_grant_specialist_actions(demo, api, reviewed_app, action):
    user = demo["client"]
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    post(api, user, reviewed_app, action, expected=403)


def test_disbursement_requires_current_assignee_and_replay_remains_idempotent(
    demo, api, signed_deal, second_specialist
):
    app = signed_deal.offer.decision.assessment.revision.application
    app.refresh_from_db()
    services.release_application(demo["specialist"], app.pk, app.lock_version)
    app.refresh_from_db()
    key = uuid.uuid4()
    with pytest.raises(Conflict) as unassigned:
        deals.disburse(demo["specialist"], signed_deal.pk, app.lock_version, key)
    assert unassigned.value.get_codes() == "assignment_required"
    claim(second_specialist, app)
    with pytest.raises(Conflict) as other:
        deals.disburse(demo["specialist"], signed_deal.pk, app.lock_version, key)
    assert other.value.get_codes() == "assigned_to_other"
    issued = deals.disburse(second_specialist, signed_deal.pk, app.lock_version, key)
    app.refresh_from_db()
    assert app.assigned_to_id is None and app.status == "issued"
    assert (
        app.events.filter(
            event_type="assignment_released", details__reason="terminal_state"
        ).count()
        == 1
    )
    assert deals.disburse(second_specialist, signed_deal.pk, 0, key).pk == issued.pk
    assert Disbursement.objects.count() == 1
    api.force_authenticate(user=second_specialist)
    changed = api.post(
        f"/api/v1/agreements/{signed_deal.pk}/disburse/",
        {"lock_version": app.lock_version, "amount": "1.00"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(key),
    )
    assert changed.status_code == 400 and "amount" in changed.data
    assert Disbursement.objects.count() == 1


def test_assignment_survives_information_and_client_accept_sign(
    demo, api, reviewed_app, second_specialist
):
    app = reviewed_app
    claim(second_specialist, app)
    post(
        api,
        second_specialist,
        app,
        "request-information",
        payload={"lock_version": app.lock_version, "question": "Уточните расходы"},
    )
    app.refresh_from_db()
    previous = app.revisions.first()
    assert app.status == "needs_info" and app.assigned_to_id == second_specialist.pk
    assert hints(api, demo["client"], app)["provide_information"]["allowed"]
    services.revise_application(demo["client"], app.pk, revise_data(app), answering=True)
    app.refresh_from_db()
    assert app.revisions.first().revision_no == 2
    assert app.assigned_to_id == second_specialist.pk
    previous.information_requests.get().refresh_from_db()
    assert previous.information_requests.get().response_revision_id == app.revisions.first().pk
    post(api, second_specialist, app, "decide")
    offer = Offer.objects.get(decision__assessment__revision=app.revisions.first())
    assert hints(api, demo["client"], app)["accept_offer"]["allowed"]
    app.refresh_from_db()
    deals.respond_to_offer(demo["client"], offer.pk, app.lock_version, accept=True)
    agreement = offer.agreement
    assert hints(api, demo["client"], app)["sign_agreement"]["allowed"]
    assert (
        hints(api, demo["accountant"], app)["sign_agreement"]["reason_code"]
        == "capability_required"
    )
    app.refresh_from_db()
    sign_with_code(demo["client"], agreement.pk, app.lock_version, agreement.document_hash)
    app.refresh_from_db()
    assert app.assigned_to_id == second_specialist.pk and app.status == "signed"


@pytest.mark.parametrize("terminal", ["rejected", "declined", "expired"])
def test_terminal_outcomes_release_assignment(demo, api, terminal):
    app = demo["applications"]["rejected" if terminal == "rejected" else "approval"]
    services.submit_application(demo["client"], app.pk, 0)
    claim(demo["specialist"], app)
    post(api, demo["specialist"], app, "decide")
    app.refresh_from_db()
    if terminal != "rejected":
        offer = Offer.objects.get(decision__assessment__revision=app.revisions.first())
        if terminal == "declined":
            deals.respond_to_offer(demo["client"], offer.pk, app.lock_version, accept=False)
        else:
            Offer.objects.filter(pk=offer.pk).update(
                expires_at=timezone.now() - timedelta(seconds=1)
            )
            services.expire_application_if_due(app.pk)
    app.refresh_from_db()
    assert app.status == terminal and app.assigned_to_id is None and app.assigned_at is None
    assert (
        app.events.filter(
            event_type="assignment_released", details__reason="terminal_state"
        ).count()
        == 1
    )


def test_action_hints_follow_role_owner_checks_and_stale_version(
    demo, api, reviewed_app, second_specialist
):
    app = reviewed_app
    assert hints(api, demo["specialist"], app)["decide"]["reason_code"] == "assignment_required"
    assert hints(api, demo["specialist"], app)["claim"]["allowed"]
    old_version = app.lock_version
    claim(demo["specialist"], app)
    mine = hints(api, demo["specialist"], app)
    assert mine["decide"]["allowed"] and mine["release"]["allowed"]
    assert mine["claim"]["reason_code"] == "already_assigned"
    assert hints(api, second_specialist, app)["decide"]["reason_code"] == "assigned_to_other"
    assert hints(api, demo["client"], app)["decide"]["reason_code"] == "role_required"
    result = post(
        api, demo["specialist"], app, "decide", expected=409, payload={"lock_version": old_version}
    )
    assert result["code"] == "stale_version"
    assert app.status == "review" and not CreditDecision.objects.exists()


def test_technical_error_and_missing_information_have_distinct_hints(demo, api):
    for scenario, reason in [
        ("check_error", "technical_error"),
        ("needs_info", "needs_information"),
    ]:
        app = demo["applications"][scenario]
        services.submit_application(demo["client"], app.pk, 0)
        claim(demo["specialist"], app)
        staff = hints(api, demo["specialist"], app)
        assert staff["decide"]["reason_code"] == reason
        client = hints(api, demo["client"], app)
        assert client["retry_checks"]["allowed"] is (scenario == "check_error")
        assert client["provide_information"]["allowed"] is (scenario == "needs_info")
        assert getattr(app.revisions.first(), "assessment", None) is None


@pytest.mark.parametrize(
    "corruption,reason",
    [
        ("new_attempt", "assessment_outdated"),
        ("missing_kind", "checks_incomplete"),
        ("no_assessment", "assessment_unavailable"),
        ("new_revision", "checks_incomplete"),
    ],
)
def test_decision_rejects_inapplicable_assessment(demo, api, reviewed_app, corruption, reason):
    app = reviewed_app
    claim(demo["specialist"], app)
    revision = app.revisions.first()
    if corruption == "new_attempt":
        for check in list(revision.checks.all()):
            CheckResult.objects.create(
                revision=revision,
                attempt=2,
                kind=check.kind,
                status=check.status,
                result=check.result,
            )
    elif corruption == "missing_kind":
        revision.checks.filter(kind="registry")._raw_delete("default")
    elif corruption == "no_assessment":
        Assessment.objects.filter(revision=revision)._raw_delete("default")
    else:
        ApplicationRevision.objects.create(
            application=app,
            revision_no=2,
            amount=revision.amount,
            term_months=24,
            purpose="Новая ревизия без оценки",
            submitted_at=timezone.now(),
        )
    assert hints(api, demo["specialist"], app)["decide"]["reason_code"] == reason
    response = post(api, demo["specialist"], app, "decide", expected=409)
    assert response["code"] == reason
    assert not CreditDecision.objects.exists() and not Offer.objects.exists()


def test_repeat_decision_conflicts_without_duplicate_offer(demo, api, reviewed_app):
    claim(demo["specialist"], reviewed_app)
    post(api, demo["specialist"], reviewed_app, "decide")
    assert (
        hints(api, demo["specialist"], reviewed_app)["decide"]["reason_code"]
        == "waiting_for_client"
    )
    post(api, demo["specialist"], reviewed_app, "decide", expected=409)
    assert CreditDecision.objects.count() == Offer.objects.count() == 1


def test_assignment_pair_is_enforced_by_postgres(demo, reviewed_app):
    with transaction.atomic(), pytest.raises(IntegrityError):
        Application.objects.filter(pk=reviewed_app.pk).update(assigned_to=demo["specialist"])


def test_specialist_membership_does_not_allow_client_actions(demo, api):
    app = demo["applications"]["approval"]
    CompanyMember.objects.create(
        user=demo["specialist"], company=app.company, role="owner", can_submit=True, can_sign=True
    )
    api.force_authenticate(user=demo["specialist"])
    result = api.post(f"/api/v1/applications/{app.pk}/submit/", {"lock_version": 0}, format="json")
    assert result.status_code == 403
    app.refresh_from_db()
    assert app.status == "draft" and app.revisions.first().checks.count() == 0


def test_injected_assignments_roles_risk_or_terms_are_rejected(demo, api, reviewed_app):
    for field, value in {
        "assigned_to": str(demo["specialist"].pk),
        "risk_level": "low",
        "annual_rate": "0",
        "outcome": "approved",
        "status": "issued",
        "system_role": "specialist",
    }.items():
        response = post(
            api,
            demo["specialist"],
            reviewed_app,
            "claim",
            expected=400,
            payload={"lock_version": reviewed_app.lock_version, field: value},
        )
        assert field in response
    reviewed_app.refresh_from_db()
    assert reviewed_app.assigned_to_id is None


def test_dependency_error_is_safe_json_503(demo, api, reviewed_app):
    api.force_authenticate(user=demo["specialist"])
    with patch(
        "api.views.staff_queue_queryset", side_effect=OperationalError("secret credentials")
    ):
        response = api.get("/api/v1/staff/applications/")
    assert response.status_code == 503
    assert response.data["code"] == "dependency_unavailable"
    assert b"secret credentials" not in response.content


def test_queue_uses_only_latest_revision_and_keeps_client_list_unchanged(demo, api, reviewed_app):
    app = reviewed_app
    claim(demo["specialist"], app)
    services.request_information(demo["specialist"], app.pk, app.lock_version, "Новые финансы")
    data = {
        **revise_data(app),
        "amount": Decimal("1200000.00"),
        "term_months": 12,
        "monthly_expenses": Decimal("1490000.00"),
    }
    services.revise_application(demo["client"], app.pk, data, answering=True)
    api.force_authenticate(user=demo["specialist"])
    response = api.get("/api/v1/staff/applications/", {"search": app.number})
    assert response.status_code == 200
    item = response.json()["results"][0]
    revision = app.revisions.first()
    assert item["current_revision_id"] == str(revision.pk)
    assert (item["amount"], item["term_months"], item["risk_level"]) == ("1200000.00", 12, "medium")
    assert item["company_inn"] == app.company.inn and item["assigned_to"]["id"] == str(
        demo["specialist"].pk
    )
    assert "revisions" not in item
    assert app.revisions.get(revision_no=1).assessment.risk_level == "low"
    assert api.get("/api/v1/staff/applications/?risk_level=medium").json()["count"] == 1
    api.force_authenticate(user=demo["client"])
    client_item = api.get("/api/v1/applications/").json()["results"][0]
    assert "assigned_to" not in client_item and "amount" not in client_item


def test_queue_does_not_reuse_old_risk_when_current_checks_fail_technically(
    demo, api, reviewed_app, monkeypatch
):
    app = reviewed_app
    claim(demo["specialist"], app)
    services.request_information(demo["specialist"], app.pk, app.lock_version, "Уточнение")

    def error(revision, attempt):
        checks = run_synthetic_checks(revision, attempt)
        kind, _, result = checks[0]
        checks[0] = (kind, "error", {**result, "retryable": True})
        return checks

    monkeypatch.setattr(services, "run_synthetic_checks", error)
    services.revise_application(demo["client"], app.pk, revise_data(app), answering=True)
    api.force_authenticate(user=demo["specialist"])
    row = api.get(
        "/api/v1/staff/applications/", {"search": app.number, "risk_level": "unassessed"}
    ).json()["results"][0]
    assert row["risk_level"] is None and row["status"] == "checking"
    assert row["current_revision_id"] == str(app.revisions.first().pk)
    assert app.revisions.get(revision_no=1).assessment.risk_level == "low"


def test_expired_offer_has_no_accept_or_sign_actions(demo, api, offer):
    app = offer.decision.assessment.revision.application
    Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    action = hints(api, demo["client"], app)["accept_offer"]
    assert not action["allowed"] and action["reason_code"] == "offer_expired"
    app.refresh_from_db()
    assert app.status == "expired" and app.assigned_to_id is None


def test_queue_filters_search_and_ordering(demo, api, second_specialist):
    for name in ("approval", "counteroffer", "rejected", "needs_info"):
        app = demo["applications"][name]
        services.submit_application(demo["client"], app.pk, 0)
    mine = demo["applications"]["approval"]
    other = demo["applications"]["counteroffer"]
    claim(demo["specialist"], mine)
    claim(second_specialist, other)
    api.force_authenticate(user=demo["specialist"])

    def rows(**params):
        response = api.get("/api/v1/staff/applications/", params)
        assert response.status_code == 200, response.data
        return response.json()["results"]

    assert {row["id"] for row in rows(assignment="mine")} == {str(mine.pk)}
    assert len(rows(assignment="free")) == 3
    assert len(rows(status="review")) == 3
    assert {row["id"] for row in rows(risk_level="low")} == {str(mine.pk), str(other.pk)}
    assert rows(risk_level="medium") == []
    assert {row["id"] for row in rows(risk_level="high")} == {
        str(demo["applications"]["rejected"].pk)
    }
    absent = rows(risk_level="unassessed")
    assert len(absent) == 2 and all(row["risk_level"] is None for row in absent)
    assert len(rows(assignment="mine", status="review", risk_level="low")) == 1
    for search in (mine.number.lower()[3:11], mine.company.name, mine.company.inn):
        assert {row["id"] for row in rows(search=search)} == {str(mine.pk)}
    numbers = [row["number"] for row in rows(ordering="number")]
    assert numbers == sorted(numbers)
    assert [row["number"] for row in rows(ordering="-number")] == list(reversed(numbers))
    assert rows(search="несуществующая компания") == []


@pytest.mark.parametrize(
    "params",
    [
        {"status": "work"},
        {"assignment": "someone"},
        {"risk_level": "A"},
        {"ordering": "company__password"},
        {"page": "-1"},
        {"search": "x" * 101},
        {"assigned_to": str(uuid.uuid4())},
    ],
)
def test_queue_rejects_invalid_filters(demo, api, params):
    api.force_authenticate(user=demo["specialist"])
    assert api.get("/api/v1/staff/applications/", params).status_code == 400


def test_queue_query_count_does_not_grow_and_pagination_is_stable(demo, api, reviewed_app):
    claim(demo["specialist"], reviewed_app)
    api.force_authenticate(user=demo["specialist"])
    with CaptureQueriesContext(connection) as initial:
        response = api.get("/api/v1/staff/applications/")
    assert response.status_code == 200
    source = demo["applications"]["approval"]
    for index in range(26):
        services.create_application(
            demo["client"],
            {
                "company": source.company_id,
                "product": source.product_id,
                "amount": Decimal("1000000.00"),
                "term_months": 24,
                "purpose": f"Очередь {index}",
            },
        )
    with CaptureQueriesContext(connection) as expanded:
        page = api.get("/api/v1/staff/applications/").json()
    assert len(initial) == len(expanded) == 2
    assert page["count"] == 31 and len(page["results"]) == 25 and page["next"]
    second = api.get("/api/v1/staff/applications/?page=2").json()
    assert len(second["results"]) == 6
    assert not (
        {item["id"] for item in page["results"]} & {item["id"] for item in second["results"]}
    )

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from agreements import services as deals
from agreements.models import Agreement, Disbursement
from applications import services
from checks.adapters import run_synthetic_checks
from checks.models import CheckResult
from common.access import company_scope, require_specialist
from common.exceptions import Conflict, exception_handler
from companies.models import Company
from offers.models import Offer
from tests.signing import sign_with_code


def revision_data(app):
    revision = app.revisions.order_by("-revision_no").first()
    return {
        "lock_version": app.lock_version,
        **{name: getattr(revision, name) for name in services.REVISION_FIELDS},
    }


def test_disallowed_transition_changes_neither_state_nor_history(demo):
    app = demo["applications"]["approval"]
    with pytest.raises(Conflict):
        services.transition(app, "issued", demo["client"], "invalid")
    app.refresh_from_db()
    assert (app.status, app.lock_version, app.events.count()) == ("draft", 0, 1)


@pytest.mark.parametrize("action", ["retry", "request-information", "revise", "answer", "decide"])
def test_service_actions_reject_draft_state(demo, action):
    app = demo["applications"]["approval"]
    calls = {
        "retry": lambda: services.retry_checks(demo["client"], app.id, 0),
        "request-information": lambda: services.request_information(
            demo["specialist"], app.id, 0, "Вопрос"
        ),
        "revise": lambda: services.revise_application(demo["client"], app.id, revision_data(app)),
        "answer": lambda: services.revise_application(
            demo["client"], app.id, revision_data(app), answering=True
        ),
        "decide": lambda: services.make_decision(demo["specialist"], app.id, 0),
    }
    with pytest.raises(Conflict):
        calls[action]()
    app.refresh_from_db()
    assert app.status == "draft" and app.lock_version == 0


def test_reviewed_application_cannot_be_submitted_or_edited_as_draft(demo, reviewed_app):
    with pytest.raises(Conflict):
        services.submit_application(demo["client"], reviewed_app.id, reviewed_app.lock_version)
    with pytest.raises(Conflict):
        services.update_draft(
            demo["client"],
            reviewed_app.id,
            {"lock_version": reviewed_app.lock_version, "purpose": "Подмена"},
        )


def test_failed_revision_rolls_back_supersession_and_new_rows(demo, offer):
    app = offer.decision.assessment.revision.application
    before = (app.lock_version, app.revisions.count(), app.events.count())
    data = {**revision_data(app), "amount": 1}
    with pytest.raises(ValidationError):
        services.revise_application(demo["client"], app.id, data)
    offer.refresh_from_db()
    app.refresh_from_db()
    assert offer.status == "available" and app.status == "offered"
    assert (app.lock_version, app.revisions.count(), app.events.count()) == before


def test_check_attempt_limit_preserves_history_and_allows_specialist_retry(demo, monkeypatch):
    app = demo["applications"]["approval"]

    def always_error(revision, attempt):
        checks = run_synthetic_checks(revision, attempt)
        kind, _, result = checks[0]
        checks[0] = (kind, CheckResult.Status.ERROR, {**result, "retryable": True})
        return checks

    monkeypatch.setattr(services, "run_synthetic_checks", always_error)
    services.submit_application(demo["client"], app.id, 0)
    for attempt in range(2, 6):
        app.refresh_from_db()
        if attempt == 2:
            services.claim_application(demo["specialist"], app.id, app.lock_version)
            app.refresh_from_db()
        user = demo["specialist"] if attempt == 2 else demo["client"]
        services.retry_checks(user, app.id, app.lock_version)
    app.refresh_from_db()
    version, event_count = app.lock_version, app.events.count()
    with pytest.raises(Conflict, match="лимит"):
        services.retry_checks(demo["client"], app.id, version)
    app.refresh_from_db()
    assert app.status == "checking" and app.lock_version == version
    assert app.events.count() == event_count
    assert app.revisions.get().checks.count() == 15
    assert not hasattr(app.revisions.get(), "assessment")


def test_unexpected_adapter_error_rolls_back_submission(demo, monkeypatch):
    app = demo["applications"]["approval"]

    def broken_adapter(*args):
        raise RuntimeError("test adapter failure")

    monkeypatch.setattr(services, "run_synthetic_checks", broken_adapter)
    with pytest.raises(RuntimeError, match="test adapter failure"):
        services.submit_application(demo["client"], app.id, 0)
    app.refresh_from_db()
    revision = app.revisions.get()
    assert app.status == "draft" and app.lock_version == 0
    assert revision.submitted_at is None and revision.input_snapshot == {}
    assert app.events.count() == 1 and revision.checks.count() == 0


def test_inactive_registry_is_negative_check_not_technical_error(demo):
    app = demo["applications"]["approval"]
    Company.objects.filter(pk=app.company_id).update(status="inactive")
    services.submit_application(demo["client"], app.id, 0)
    app.refresh_from_db()
    assert app.status == "review"
    assert app.revisions.get().checks.get(kind="registry").status == "failed"
    services.claim_application(demo["specialist"], app.id, app.lock_version)
    app.refresh_from_db()
    services.make_decision(demo["specialist"], app.id, app.lock_version)
    app.refresh_from_db()
    assert app.status == "rejected"


def test_expiration_command_is_idempotent_and_does_not_expire_signed_deals(
    demo, signed_deal_factory
):
    signed = signed_deal_factory("approval")
    pending = demo["applications"]["counteroffer"]
    services.submit_application(demo["client"], pending.id, 0)
    pending.refresh_from_db()
    services.claim_application(demo["specialist"], pending.id, pending.lock_version)
    pending.refresh_from_db()
    services.make_decision(demo["specialist"], pending.id, pending.lock_version)
    offer = Offer.objects.get(decision__assessment__revision__application=pending)
    Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    Offer.objects.filter(pk=signed.offer_id).update(
        sign_before=timezone.now() - timedelta(seconds=1)
    )
    call_command("expire_offers", stdout=StringIO())
    call_command("expire_offers", stdout=StringIO())
    pending.refresh_from_db()
    assert pending.status == "expired" and pending.events.filter(event_type="expired").count() == 1
    assert signed.offer.decision.assessment.revision.application.status == "signed"


def test_signing_replay_and_direct_deadline_enforcement(demo, agreement):
    app = agreement.offer.decision.assessment.revision.application
    Offer.objects.filter(pk=agreement.offer_id).update(
        sign_before=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(Conflict, match="истёк"):
        deals.sign_agreement(
            demo["client"], agreement.id, app.lock_version, agreement.document_hash
        )
    Offer.objects.filter(pk=agreement.offer_id).update(
        sign_before=timezone.now() + timedelta(days=1)
    )
    sign_with_code(demo["client"], agreement.id, app.lock_version, agreement.document_hash)
    app.refresh_from_db()
    with pytest.raises(Conflict):
        deals.sign_agreement(
            demo["client"], agreement.id, app.lock_version, agreement.document_hash
        )


def test_disbursement_rejects_stale_version_and_corrupted_signed_terms(demo, signed_deal):
    app = signed_deal.offer.decision.assessment.revision.application
    with pytest.raises(Conflict, match="lock_version"):
        deals.disburse(demo["specialist"], signed_deal.id, app.lock_version - 1, uuid.uuid4())
    Agreement.objects.filter(pk=signed_deal.pk).update(terms_snapshot={"amount": "1.00"})
    with pytest.raises(Conflict, match="Целостность"):
        deals.disburse(demo["specialist"], signed_deal.id, app.lock_version, uuid.uuid4())
    assert not Disbursement.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_same_idempotency_key_racing_across_two_agreements_rolls_back_loser(
    demo, signed_deal_factory, monkeypatch
):
    assert connection.vendor == "postgresql"
    agreements = [signed_deal_factory("approval"), signed_deal_factory("counteroffer")]
    key = uuid.uuid4()
    barrier = Barrier(2)
    real_create = Disbursement.objects.create

    def synchronized_create(**kwargs):
        barrier.wait(timeout=10)
        return real_create(**kwargs)

    monkeypatch.setattr(Disbursement.objects, "create", synchronized_create)

    def issue(agreement):
        try:
            specialist = User.objects.get(pk=demo["specialist"].pk)
            app = agreement.offer.decision.assessment.revision.application
            try:
                return deals.disburse(specialist, agreement.id, app.lock_version, key).id
            except Conflict:
                return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue, agreements))
    assert results.count("conflict") == 1
    assert Disbursement.objects.count() == 1
    apps = [agreement.offer.decision.assessment.revision.application for agreement in agreements]
    for app in apps:
        app.refresh_from_db()
    assert sorted(app.status for app in apps) == ["issued", "signed"]
    assert sum(app.events.filter(event_type="issued").count() for app in apps) == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("action", ["submit", "accept"])
def test_concurrent_submission_and_acceptance_create_records_once(demo, action):
    app = demo["applications"]["approval"]
    offer = None
    if action == "accept":
        services.submit_application(demo["client"], app.id, 0)
        app.refresh_from_db()
        services.claim_application(demo["specialist"], app.id, app.lock_version)
        app.refresh_from_db()
        services.make_decision(demo["specialist"], app.id, app.lock_version)
        offer = Offer.objects.get(decision__assessment__revision__application=app)
    app.refresh_from_db()
    version = app.lock_version
    barrier = Barrier(2)

    def perform(_):
        try:
            user = User.objects.get(pk=demo["client"].pk)
            barrier.wait(timeout=10)
            try:
                if action == "submit":
                    services.submit_application(user, app.id, version)
                else:
                    deals.respond_to_offer(user, offer.id, version, accept=True)
                return "success"
            except Conflict:
                return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(perform, range(2)))
    assert sorted(outcomes) == ["conflict", "success"]
    app.refresh_from_db()
    if action == "submit":
        assert app.status == "review"
        assert app.revisions.get().checks.count() == 3
        assert app.events.filter(event_type="submitted").count() == 1
    else:
        assert app.status == "accepted"
        assert Agreement.objects.filter(offer=offer).count() == 1
        assert app.events.filter(event_type="offer_accepted").count() == 1


def test_seed_refuses_non_demo_or_short_password(demo, settings, monkeypatch):
    settings.DEMO_MODE = False
    with pytest.raises(CommandError):
        call_command("seed_demo", stdout=StringIO())
    settings.DEMO_MODE = True
    monkeypatch.setenv("DEMO_PASSWORD", "short")
    with pytest.raises(CommandError):
        call_command("seed_demo", stdout=StringIO())


def test_reset_passwords_preserves_non_demo_users(demo, monkeypatch):
    other = User.objects.create_user(username="other-test-user", password="OriginalTestPassword1!")
    original = other.password
    monkeypatch.setenv("DEMO_PASSWORD", "RotatedTestPassword2026!")
    call_command("seed_demo", reset_passwords=True, stdout=StringIO())
    for name in ("client", "accountant", "specialist", "outsider"):
        assert User.objects.get(username=name).check_password("RotatedTestPassword2026!")
    other.refresh_from_db()
    assert other.password == original


def test_common_permissions_and_validation_error_translation(demo):
    with pytest.raises(PermissionDenied):
        require_specialist(AnonymousUser())
    with pytest.raises(PermissionDenied):
        require_specialist(demo["client"])
    assert not company_scope(Company.objects.all(), AnonymousUser(), "company").exists()
    for error in (DjangoValidationError("invalid"), DjangoValidationError({"amount": "invalid"})):
        response = exception_handler(error, {})
        assert response.status_code == 400
    assert exception_handler(RuntimeError("unexpected"), {}) is None

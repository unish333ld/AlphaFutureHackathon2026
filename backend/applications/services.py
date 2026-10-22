"""The only application mutation boundary: authorization, row lock, version, event."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from applications.models import (
    Application,
    ApplicationEvent,
    ApplicationRevision,
    InformationRequest,
)
from checks.adapters import run_synthetic_checks
from checks.models import CheckResult
from common.access import require_member, require_specialist
from common.exceptions import Conflict
from companies.models import Company
from decisions.models import Assessment, CreditDecision
from decisions.policy import POLICY_VERSION, assess, decide
from offers.models import Offer
from products.calculations import payment_schedule
from products.models import CreditProduct

ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"checking"},
    "checking": {"review", "needs_info"},
    "review": {"needs_info", "offered", "rejected", "submitted"},
    "needs_info": {"submitted"},
    "offered": {"accepted", "declined", "expired", "submitted"},
    "accepted": {"signed", "expired"},
    "signed": {"issued"},
}
REVISION_FIELDS = (
    "amount",
    "term_months",
    "purpose",
    "monthly_revenue",
    "monthly_expenses",
    "monthly_debt_payments",
)


def locked_application(application_id, version):
    app = get_object_or_404(Application.objects.select_for_update(), pk=application_id)
    if app.lock_version != version:
        raise Conflict("Устаревший lock_version. Загрузите заявку заново.")
    return app


def transition(app, status, actor, event_type, details=None):
    previous = app.status
    if status != previous and status not in ALLOWED_TRANSITIONS.get(previous, set()):
        raise Conflict(f"Переход {previous} → {status} недоступен.")
    app.status = status
    app.lock_version += 1
    app.save(update_fields=["status", "lock_version", "updated_at"])
    ApplicationEvent.objects.create(
        application=app,
        actor=actor,
        event_type=event_type,
        from_status=previous,
        to_status=status,
        details={"schema_version": 1, **(details or {})},
    )


def current_revision(app):
    return app.revisions.order_by("-revision_no").first()


def validate_terms(data, product):
    if not product.active:
        raise ValidationError({"product": "Продукт больше не принимает заявки."})
    if not product.min_amount <= data["amount"] <= product.max_amount:
        raise ValidationError({"amount": "Сумма вне границ выбранного продукта."})
    if not product.min_term_months <= data["term_months"] <= product.max_term_months:
        raise ValidationError({"term_months": "Срок вне границ выбранного продукта."})


def snapshot(revision, app):
    company, product = app.company, app.product
    return {
        "schema_version": 1,
        "company": {
            "id": str(company.id),
            "inn": company.inn,
            "name": company.name,
            "status": company.status,
            "registered_at": company.registered_at.isoformat(),
            "demo_scenario": company.demo_scenario,
            "is_existing_client": company.is_existing_client,
        },
        "product": {
            "id": str(product.id),
            "code": product.code,
            "rules_version": product.rules_version,
            "annual_rate": str(product.annual_rate),
            "min_amount": str(product.min_amount),
            "max_amount": str(product.max_amount),
            "min_term_months": product.min_term_months,
            "max_term_months": product.max_term_months,
        },
        "financial": {
            name: str(getattr(revision, name)) if getattr(revision, name) is not None else None
            for name in REVISION_FIELDS
            if name.startswith("monthly_")
        },
    }


@transaction.atomic
def create_application(user, data):
    company = get_object_or_404(Company, pk=data["company"])
    require_member(user, company.id)
    if not company.is_existing_client:
        raise ValidationError({"company": "MVP работает с действующими клиентами банка."})
    product = get_object_or_404(CreditProduct, pk=data["product"])
    validate_terms(data, product)
    app = Application.objects.create(company=company, product=product, created_by=user)
    revision = ApplicationRevision(
        application=app,
        revision_no=1,
        **{name: data[name] for name in REVISION_FIELDS if name in data},
    )
    revision.full_clean()
    revision.save()
    ApplicationEvent.objects.create(
        application=app,
        actor=user,
        event_type="created",
        from_status="",
        to_status=app.status,
        details={"schema_version": 1},
    )
    return app


@transaction.atomic
def update_draft(user, application_id, data):
    app = locked_application(application_id, data["lock_version"])
    require_member(user, app.company_id)
    if app.status != Application.Status.DRAFT:
        raise Conflict("Редактирование доступно только для черновика.")
    revision = current_revision(app)
    for name in REVISION_FIELDS:
        if name in data:
            setattr(revision, name, data[name])
    validate_terms({name: getattr(revision, name) for name in REVISION_FIELDS}, app.product)
    revision.full_clean()
    revision.save()
    transition(app, app.status, user, "draft_updated")
    return app


def _run_checks(app, revision, actor):
    if app.status != Application.Status.CHECKING:
        transition(app, Application.Status.CHECKING, actor, "checks_started")
    attempt = (revision.checks.aggregate(value=Max("attempt"))["value"] or 0) + 1
    if attempt > 5:
        raise Conflict("Достигнут лимит пяти попыток локальной проверки.")
    checks = [
        CheckResult.objects.create(
            revision=revision, attempt=attempt, kind=kind, status=status, result=result
        )
        for kind, status, result in run_synthetic_checks(revision, attempt)
    ]
    if any(check.status == CheckResult.Status.ERROR for check in checks):
        transition(app, app.status, actor, "checks_error", {"attempt": attempt, "retryable": True})
        return
    if any(check.status == CheckResult.Status.MISSING for check in checks):
        InformationRequest.objects.create(
            revision=revision,
            question="Укажите месячные выручку, расходы и платежи по обязательствам.",
        )
        transition(app, Application.Status.NEEDS_INFO, actor, "information_requested")
        return
    Assessment.objects.create(revision=revision, **assess(revision, checks))
    transition(app, Application.Status.REVIEW, actor, "checks_completed", {"attempt": attempt})


def _submit(app, revision, user):
    validate_terms({name: getattr(revision, name) for name in REVISION_FIELDS}, app.product)
    revision.input_snapshot = snapshot(revision, app)
    revision.submitted_at = timezone.now()
    revision.full_clean()
    revision.save()
    transition(
        app, Application.Status.SUBMITTED, user, "submitted", {"revision_no": revision.revision_no}
    )
    # Adapters are local pure functions. Real network calls must execute outside this transaction.
    _run_checks(app, revision, user)


@transaction.atomic
def submit_application(user, application_id, version):
    app = locked_application(application_id, version)
    require_member(user, app.company_id, "can_submit")
    if app.status != Application.Status.DRAFT:
        raise Conflict("Отправить можно только черновик.")
    _submit(app, current_revision(app), user)
    return app


@transaction.atomic
def retry_checks(user, application_id, version):
    app = locked_application(application_id, version)
    if user.is_credit_specialist:
        require_specialist(user)
    else:
        require_member(user, app.company_id, "can_submit")
    if app.status != Application.Status.CHECKING:
        raise Conflict("Повтор доступен только после технической ошибки проверки.")
    _run_checks(app, current_revision(app), user)
    return app


@transaction.atomic
def request_information(user, application_id, version, question):
    require_specialist(user)
    app = locked_application(application_id, version)
    if app.status not in {Application.Status.REVIEW, Application.Status.CHECKING}:
        raise Conflict("Запрос уточнения доступен во время проверки и рассмотрения.")
    InformationRequest.objects.create(
        revision=current_revision(app), requested_by=user, question=question
    )
    transition(app, Application.Status.NEEDS_INFO, user, "information_requested")
    return app


@transaction.atomic
def revise_application(user, application_id, data, *, answering=False):
    app = locked_application(application_id, data["lock_version"])
    require_member(user, app.company_id, "can_submit")
    allowed = (
        {Application.Status.NEEDS_INFO}
        if answering
        else {Application.Status.REVIEW, Application.Status.OFFERED}
    )
    if app.status not in allowed:
        raise Conflict("Новая ревизия в текущем состоянии недоступна.")
    previous = current_revision(app)
    # Existing terms and decisions stay immutable; new input always has a new revision id.
    Offer.objects.filter(
        decision__assessment__revision__application=app, status=Offer.Status.AVAILABLE
    ).update(status=Offer.Status.SUPERSEDED)
    revision = ApplicationRevision(
        application=app,
        revision_no=previous.revision_no + 1,
        **{name: data[name] for name in REVISION_FIELDS},
    )
    revision.full_clean()
    revision.save()
    if answering:
        previous.information_requests.filter(response_revision__isnull=True).update(
            response_revision=revision, responded_at=timezone.now()
        )
    _submit(app, revision, user)
    return app


@transaction.atomic
def make_decision(user, application_id, version):
    require_specialist(user)
    app = locked_application(application_id, version)
    if app.status != Application.Status.REVIEW:
        raise Conflict("Решение доступно только после успешного завершения проверок.")
    revision = current_revision(app)
    assessment = revision.assessment
    outcome, reason, explanation, amount = decide(assessment)
    decision = CreditDecision.objects.create(
        assessment=assessment,
        outcome=outcome,
        reason_code=reason,
        explanation=explanation,
        decided_by=user,
        policy_version=POLICY_VERSION,
    )
    if amount is None:
        transition(app, Application.Status.REJECTED, user, "rejected", {"reason_code": reason})
    else:
        rate = Decimal(revision.input_snapshot["product"]["annual_rate"])
        monthly_payment, schedule = payment_schedule(amount, rate, revision.term_months)
        Offer.objects.create(
            decision=decision,
            product=app.product,
            amount=amount,
            annual_rate=rate,
            term_months=revision.term_months,
            monthly_payment=monthly_payment,
            schedule=schedule,
            expires_at=timezone.now() + timedelta(days=7),
        )
        transition(app, Application.Status.OFFERED, user, "offered", {"outcome": outcome})
    return app


@transaction.atomic
def expire_application_if_due(application_id):
    app = Application.objects.select_for_update().get(pk=application_id)
    if app.status not in {Application.Status.OFFERED, Application.Status.ACCEPTED}:
        return
    offer = Offer.objects.get(decision__assessment__revision=current_revision(app))
    deadline = offer.sign_before if app.status == Application.Status.ACCEPTED else offer.expires_at
    if deadline and deadline <= timezone.now():
        offer.status = Offer.Status.EXPIRED
        offer.save(update_fields=["status"])
        transition(app, Application.Status.EXPIRED, None, "expired")

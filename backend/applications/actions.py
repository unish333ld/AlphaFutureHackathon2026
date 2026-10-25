"""Read-only UI hints. Mutation services always authorize and check again under a lock."""

from django.utils import timezone

from agreements.services import terms_hash
from applications.services import ASSIGNABLE_STATUSES, TERMINAL_STATUSES, decision_blocker
from companies.models import CompanyMember

ACTION_NAMES = (
    "update_draft",
    "submit",
    "retry_checks",
    "provide_information",
    "revise",
    "claim",
    "release",
    "request_information",
    "decide",
    "accept_offer",
    "decline_offer",
    "sign_agreement",
    "disburse",
)
REASON_CODES = (
    "role_required",
    "capability_required",
    "assignment_required",
    "assigned_to_other",
    "already_assigned",
    "not_assigned",
    "invalid_state",
    "needs_information",
    "technical_error",
    "retry_limit",
    "waiting_for_client",
    "offer_expired",
    "assessment_unavailable",
    "assessment_outdated",
    "checks_incomplete",
    "already_completed",
    "no_current_revision",
    "terms_mismatch",
    "product_unavailable",
    "invalid_terms",
)


def latest_revision(app):
    # Detail selectors always prefetch in this exact order, including old revisions.
    return next(iter(app.revisions.all()), None)


def available_actions(app, user):
    revision = latest_revision(app)
    assessment = getattr(revision, "assessment", None)
    decision = getattr(assessment, "decision", None)
    offer = getattr(decision, "offer", None)
    agreement = getattr(offer, "agreement", None)
    issued = getattr(agreement, "disbursement", None)
    checks = list(revision.checks.all()) if revision else []
    attempt = max((check.attempt for check in checks), default=0)
    latest_checks = [check for check in checks if check.attempt == attempt]
    now = timezone.now()
    specialist = user.is_credit_specialist
    member = (
        None
        if specialist
        else CompanyMember.objects.filter(user=user, company_id=app.company_id, active=True).first()
    )

    def client(capability=None):
        if specialist or member is None:
            return "role_required"
        if capability and not getattr(member, capability):
            return "capability_required"
        return None

    def bank(assigned=False):
        if not specialist:
            return "role_required"
        if assigned:
            if app.assigned_to_id is None:
                return "assignment_required"
            if app.assigned_to_id != user.pk:
                return "assigned_to_other"
        return None

    def state(*allowed):
        if app.status in allowed:
            return None
        if app.status == "expired":
            return "offer_expired"
        if app.status in TERMINAL_STATUSES:
            return "already_completed"
        if app.status == "needs_info":
            return "needs_information"
        if app.status == "checking":
            return (
                "technical_error"
                if any(c.status == "error" for c in latest_checks)
                else "checks_incomplete"
            )
        if app.status in {"offered", "accepted"}:
            return "waiting_for_client"
        return "invalid_state"

    def offer_blocker():
        if offer is None:
            return "invalid_state"
        if offer.status != "available" or offer.expires_at <= now:
            return "offer_expired"
        return None

    result = []

    def add(name, reason, target=None):
        result.append(
            {"action": name, "allowed": reason is None, "reason_code": reason, "target_id": target}
        )

    add("update_draft", client() or state("draft"), app.pk)
    terms_reason = None
    if not app.product.active:
        terms_reason = "product_unavailable"
    elif revision and not (
        app.product.min_amount <= revision.amount <= app.product.max_amount
        and app.product.min_term_months <= revision.term_months <= app.product.max_term_months
    ):
        terms_reason = "invalid_terms"
    add(
        "submit",
        client("can_submit")
        or state("draft")
        or ("no_current_revision" if not revision else terms_reason),
        app.pk,
    )
    retry_reason = state("checking")
    if not retry_reason:
        retry_reason = (
            "retry_limit"
            if attempt >= 5
            else (None if any(c.status == "error" for c in latest_checks) else "checks_incomplete")
        )
    add(
        "retry_checks", (bank(True) if specialist else client("can_submit")) or retry_reason, app.pk
    )
    add("provide_information", client("can_submit") or state("needs_info"), app.pk)
    add("revise", client("can_submit") or state("review", "offered"), app.pk)
    claim_reason = bank() or state(*ASSIGNABLE_STATUSES)
    if not claim_reason and app.assigned_to_id:
        claim_reason = "already_assigned" if app.assigned_to_id == user.pk else "assigned_to_other"
    add("claim", claim_reason, app.pk)
    add("release", bank() or ("not_assigned" if app.assigned_to_id is None else bank(True)), app.pk)
    add("request_information", bank() or state("checking", "review") or bank(True), app.pk)
    add("decide", bank() or state("review") or bank(True) or decision_blocker(revision), app.pk)
    for action in ("accept_offer", "decline_offer"):
        add(
            action,
            client("can_submit") or state("offered") or offer_blocker(),
            offer.pk if offer else None,
        )
    sign_reason = state("accepted")
    if not sign_reason:
        if (
            not offer
            or offer.status != "accepted"
            or not offer.sign_before
            or offer.sign_before <= now
        ):
            sign_reason = "offer_expired"
        elif not agreement or agreement.signed_at:
            sign_reason = "already_completed" if agreement else "invalid_state"
        elif terms_hash(agreement.terms_snapshot) != agreement.document_hash:
            sign_reason = "terms_mismatch"
    add("sign_agreement", client("can_sign") or sign_reason, agreement.pk if agreement else None)
    issue_reason = state("signed")
    if not issue_reason:
        if not agreement or not agreement.signed_at or issued:
            issue_reason = "already_completed" if issued else "invalid_state"
        elif terms_hash(
            agreement.terms_snapshot
        ) != agreement.document_hash or agreement.terms_snapshot.get("amount") != str(offer.amount):
            issue_reason = "terms_mismatch"
    add("disburse", bank() or issue_reason or bank(True), agreement.pk if agreement else None)
    return result

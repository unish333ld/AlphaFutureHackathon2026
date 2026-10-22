"""Pure deterministic adapters. No external bank, registry or credit bureau requests."""

from checks.models import CheckResult


def run_synthetic_checks(revision, attempt):
    snapshot = revision.input_snapshot
    company = snapshot["company"]
    registry_status = CheckResult.Status.PASSED
    if company["demo_scenario"] == "check_error" and attempt == 1:
        registry_status = CheckResult.Status.ERROR
    elif company["status"] != "active":
        registry_status = CheckResult.Status.FAILED
    history_status = (
        CheckResult.Status.FAILED
        if company["demo_scenario"] == "bad_history"
        else CheckResult.Status.PASSED
    )
    missing = [
        name
        for name in ("monthly_revenue", "monthly_expenses", "monthly_debt_payments")
        if snapshot["financial"][name] is None
    ]
    return [
        (
            CheckResult.Kind.REGISTRY,
            registry_status,
            {
                "schema_version": 1,
                "registration_status": company["status"],
                "retryable": registry_status == "error",
            },
        ),
        (
            CheckResult.Kind.CREDIT_HISTORY,
            history_status,
            {"schema_version": 1, "overdue": history_status == "failed"},
        ),
        (
            CheckResult.Kind.FINANCIAL,
            CheckResult.Status.MISSING if missing else CheckResult.Status.PASSED,
            {"schema_version": 1, "missing_fields": missing},
        ),
    ]

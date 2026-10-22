"""Explainable synthetic policy; thresholds are project assumptions, not bank policy."""

from decimal import ROUND_DOWN, Decimal, localcontext

from decisions.models import Assessment, CreditDecision
from products.calculations import KOPECK, annuity_factor, annuity_payment, money

SCORING_VERSION = "demo-score-1"
POLICY_VERSION = "demo-policy-1"


def assess(revision, checks):
    failed = [check.kind for check in checks if check.status == "failed"]
    financial = revision.input_snapshot["financial"]
    cashflow = Decimal(financial["monthly_revenue"]) - Decimal(financial["monthly_expenses"])
    debt = Decimal(financial["monthly_debt_payments"])
    capacity = max(Decimal(0), cashflow * Decimal("0.50") - debt)
    score = 10 if failed else (60 if cashflow <= 0 or debt > cashflow * Decimal("0.30") else 90)
    risk = (
        Assessment.Risk.HIGH
        if score < 40
        else (Assessment.Risk.MEDIUM if score < 80 else Assessment.Risk.LOW)
    )
    return {
        "score": score,
        "risk_level": risk,
        "rules_version": SCORING_VERSION,
        "factors": {
            "schema_version": 1,
            "failed_checks": failed,
            "monthly_cashflow": str(money(cashflow)),
            "payment_capacity": str(money(capacity)),
            "capacity_fraction": "0.50",
        },
    }


def decide(assessment):
    revision = assessment.revision
    terms = revision.input_snapshot["product"]
    if assessment.factors["failed_checks"]:
        return (
            CreditDecision.Outcome.REJECTED,
            "negative_check",
            "Локальная проверка выявила негативный фактор.",
            None,
        )
    capacity = Decimal(assessment.factors["payment_capacity"])
    rate = Decimal(terms["annual_rate"])
    requested_payment = annuity_payment(revision.amount, rate, revision.term_months)
    if requested_payment <= capacity:
        return (
            CreditDecision.Outcome.APPROVED,
            "affordable",
            "Запрошенный платёж укладывается в демонстрационный лимит.",
            revision.amount,
        )
    # Invert the unrounded coefficient; a cent-by-cent correction loop is unnecessary.
    with localcontext() as context:
        context.prec = 40
        amount = (capacity / annuity_factor(rate, revision.term_months)).quantize(
            KOPECK, rounding=ROUND_DOWN
        )
    amount = min(amount, revision.amount, Decimal(terms["max_amount"]))
    if amount < Decimal(terms["min_amount"]):
        return (
            CreditDecision.Outcome.REJECTED,
            "insufficient_capacity",
            "Платёжеспособность ниже минимальных условий демо-продукта.",
            None,
        )
    return (
        CreditDecision.Outcome.COUNTEROFFER,
        "reduced_amount",
        "Предложена меньшая сумма с учётом месячного денежного потока.",
        amount,
    )

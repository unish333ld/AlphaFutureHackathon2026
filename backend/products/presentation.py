"""Read-only disclosures calculated from frozen schedules, never live tariffs."""

from decimal import Decimal

from products.calculations import money, payment_schedule

CALCULATION_VERSION = "demo-annuity-monthly-v1"


def cost_breakdown(amount, schedule):
    rows = schedule.get("rows", [])
    payments = [Decimal(row["payment"]) for row in rows]
    interest = sum((Decimal(row["interest"]) for row in rows), Decimal(0))
    principal = sum((Decimal(row["principal"]) for row in rows), Decimal(0))
    known = sum(payments, Decimal(0))
    # v1 explicitly excludes fees/services. Missing/unknown pricing is NOT zero.
    complete = bool(
        rows
        and schedule.get("method") == "demo_annuity_monthly"
        and schedule.get("fees") == "0.00"
        and principal == Decimal(amount)
        and money(known) == money(principal + interest)
        and Decimal(rows[-1]["balance"]) == 0
    )
    return {
        "schema_version": 1,
        "calculation_version": CALCULATION_VERSION,
        "value_type": "derived",
        "pricing_basis": "demo_assumption",
        "currency": "RUB",
        "is_complete": complete,
        "principal": str(money(amount)),
        "net_disbursement": str(money(amount)) if complete else None,
        "interest_total": str(money(interest)),
        "fees_total": "0.00" if complete else None,
        "services_total": "0.00" if complete else None,
        "known_payments_total": str(money(known)),
        "total_repayment": str(money(known)) if complete else None,
        "total_cost": str(money(known - Decimal(amount))) if complete else None,
        "first_payment": str(money(payments[0])) if payments else None,
        "last_payment": str(money(payments[-1])) if payments else None,
        "max_payment": str(money(max(payments))) if payments else None,
        "disclosure": "Учебный аннуитет по месяцам. Комиссии и платные услуги исключены правилами демо; это не расчёт юридической ПСК и не цена реального банковского продукта.",
    }


def offer_comparison(offer):
    decision = offer.decision
    revision = decision.assessment.revision
    terms = revision.input_snapshot["product"]
    rate = Decimal(terms["annual_rate"])
    payment, schedule = payment_schedule(revision.amount, rate, revision.term_months)
    requested = {
        "amount": str(revision.amount),
        "annual_rate": str(rate),
        "term_months": revision.term_months,
        "monthly_payment": str(payment),
        "cost_breakdown": cost_breakdown(revision.amount, schedule),
    }
    proposed = {
        "amount": str(offer.amount),
        "annual_rate": str(offer.annual_rate),
        "term_months": offer.term_months,
        "monthly_payment": str(offer.monthly_payment),
        "cost_breakdown": cost_breakdown(offer.amount, offer.schedule),
    }
    return {
        "schema_version": 1,
        "source_revision_id": str(revision.pk),
        "catalog_version": terms["rules_version"],
        "policy_version": decision.policy_version,
        "reason_code": decision.reason_code,
        "explanation": decision.explanation,
        "requested": requested,
        "proposed": proposed,
        "changed_fields": [
            field
            for field in ("amount", "annual_rate", "term_months", "monthly_payment")
            if Decimal(str(requested[field])) != Decimal(str(proposed[field]))
        ],
    }

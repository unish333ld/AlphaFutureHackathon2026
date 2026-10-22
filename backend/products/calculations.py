"""Demo annuity: monthly periods, no fees, Decimal, ROUND_HALF_UP to kopecks."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

KOPECK = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(KOPECK, rounding=ROUND_HALF_UP)


def annuity_factor(annual_rate, term_months):
    with localcontext() as context:
        context.prec = 40
        rate = Decimal(annual_rate) / Decimal(1200)
        if not rate:
            return Decimal(1) / term_months
        factor = (1 + rate) ** term_months
        return rate * factor / (factor - 1)


def annuity_payment(amount, annual_rate, term_months):
    with localcontext() as context:
        context.prec = 40
        return money(Decimal(amount) * annuity_factor(annual_rate, term_months))


def payment_schedule(amount, annual_rate, term_months):
    payment = annuity_payment(amount, annual_rate, term_months)
    rate = Decimal(annual_rate) / Decimal(1200)
    balance = money(amount)
    rows = []
    for month in range(1, term_months + 1):
        interest = money(balance * rate)
        total = (
            money(balance + interest) if month == term_months else min(payment, balance + interest)
        )
        principal = money(total - interest)
        balance = money(balance - principal)
        rows.append(
            {
                "month": month,
                "payment": str(total),
                "principal": str(principal),
                "interest": str(interest),
                "balance": str(balance),
            }
        )
    return payment, {
        "schema_version": 1,
        "method": "demo_annuity_monthly",
        "fees": "0.00",
        "rows": rows,
    }

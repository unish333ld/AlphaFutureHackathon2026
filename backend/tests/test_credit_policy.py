from decimal import Decimal
from itertools import product
from types import SimpleNamespace

import pytest

from decisions.policy import assess, decide
from products.calculations import annuity_payment, money, payment_schedule


def revision(
    *,
    revenue="1000.00",
    expenses="400.00",
    debt="0.00",
    amount="1000000.00",
    rate="18.0000",
    minimum="100000.00",
):
    return SimpleNamespace(
        amount=Decimal(amount),
        term_months=24,
        input_snapshot={
            "financial": {
                "monthly_revenue": revenue,
                "monthly_expenses": expenses,
                "monthly_debt_payments": debt,
            },
            "product": {"annual_rate": rate, "min_amount": minimum, "max_amount": "5000000.00"},
        },
    )


@pytest.mark.parametrize(
    "revenue,expenses,debt,failed,score,risk,capacity",
    [
        ("1000", "400", "180", False, 90, "low", "120.00"),
        ("1000", "400", "180.01", False, 60, "medium", "119.99"),
        ("1000", "1000", "0", False, 60, "medium", "0.00"),
        ("1000", "2000", "0", False, 60, "medium", "0.00"),
        ("1000", "400", "0", True, 10, "high", "300.00"),
    ],
)
def test_assessment_boundaries_use_finances_and_failed_checks(
    revenue, expenses, debt, failed, score, risk, capacity
):
    data = revision(revenue=revenue, expenses=expenses, debt=debt)
    checks = [SimpleNamespace(kind="registry", status="failed" if failed else "passed")]
    result = assess(data, checks)
    assert (result["score"], result["risk_level"]) == (score, risk)
    assert result["factors"]["payment_capacity"] == capacity
    assert result["factors"]["failed_checks"] == (["registry"] if failed else [])


def test_exact_payment_capacity_approves_requested_amount():
    data = revision()
    payment = annuity_payment(data.amount, Decimal("18"), data.term_months)
    assessment = SimpleNamespace(
        revision=data, factors={"failed_checks": [], "payment_capacity": str(payment)}
    )
    outcome, reason, _, amount = decide(assessment)
    assert (outcome, reason, amount) == ("approved", "affordable", data.amount)


@pytest.mark.parametrize("rate", ["0.0000", "18.0000", "100.0000"])
def test_counteroffer_is_affordable_and_does_not_exceed_requested_amount(rate):
    data = revision(rate=rate)
    assessment = SimpleNamespace(
        revision=data, factors={"failed_checks": [], "payment_capacity": "30000.00"}
    )
    outcome, reason, _, amount = decide(assessment)
    assert (outcome, reason) == ("counteroffer", "reduced_amount")
    assert Decimal("100000") <= amount < data.amount
    assert annuity_payment(amount, Decimal(rate), data.term_months) <= Decimal("30000.00")


@pytest.mark.parametrize("capacity", ["0.00", "0.01", "100.00"])
def test_capacity_below_minimum_product_terms_is_rejected(capacity):
    assessment = SimpleNamespace(
        revision=revision(), factors={"failed_checks": [], "payment_capacity": capacity}
    )
    outcome, reason, _, amount = decide(assessment)
    assert (outcome, reason, amount) == ("rejected", "insufficient_capacity", None)


@pytest.mark.parametrize(
    "amount,rate,term",
    list(
        product(
            ["1.00", "100000.01", "9999999999999999.99"],
            ["0.0000", "0.0001", "18.0000", "100.0000"],
            [1, 12, 120],
        )
    ),
)
def test_schedule_preserves_money_and_balances_for_boundary_grid(amount, rate, term):
    _, schedule = payment_schedule(Decimal(amount), Decimal(rate), term)
    rows = schedule["rows"]
    assert len(rows) == term
    balance = Decimal(amount)
    for month, row in enumerate(rows, 1):
        payment, principal, interest, remaining = (
            Decimal(row[key]) for key in ("payment", "principal", "interest", "balance")
        )
        assert row["month"] == month
        assert interest == money(balance * Decimal(rate) / 1200)
        assert payment == principal + interest
        assert remaining == balance - principal
        assert 0 <= remaining <= balance
        assert principal >= 0 and interest >= 0
        balance = remaining
    assert balance == 0
    assert sum(Decimal(row["principal"]) for row in rows) == Decimal(amount)


@pytest.mark.parametrize(
    "value,expected", [("1.004", "1.00"), ("1.005", "1.01"), ("1.015", "1.02")]
)
def test_money_rounds_half_up_to_kopecks(value, expected):
    assert money(value) == Decimal(expected)

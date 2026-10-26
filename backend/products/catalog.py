"""Reviewed public reference and explicitly synthetic executable product terms."""

from decimal import Decimal

CATALOG_VERSION = "research-2026-10-25"
PUBLIC_REFERENCE = {
    "schema_version": 1,
    "value_type": "public_product",
    "source_url": "https://alfabank.ru/sme/profits/businesscredit/",
    "source_title": "Альфа-Банк: кредит одной суммой без залога",
    "observed_at": "2026-10-25",
    "effective_from": None,
    "access_mode": "search_index",
    "currency": "RUB",
    "min_amount": "300000.00",
    "max_amount": "30000000.00",
    "min_term_months": 12,
    "max_term_months": 60,
    "advertised_rate_from": "23.5000",
    "minimum_business_age_months": 9,
    "rate_note": "Публичный минимум, не персональная ставка. Скидки требуют платных услуг; их цена здесь не рассчитывается.",
    "demo_rate_type": "demo_assumption",
    "demo_cost_policy": "no_fees_no_services",
    "limitations": "Демо не проверяет поручительство, территорию обслуживания и полный набор банковских требований. Условия не являются офертой банка.",
}


def product_defaults(code):
    return {
        "name": "Оборотные средства · демо"
        if code == "working-capital"
        else "Покупка оборудования · демо",
        "description": "Разовый бизнес-кредит без моделирования залога. Диапазоны основаны на публичном ориентире; ставка 27% — учебное допущение.",
        "min_amount": Decimal("300000.00"),
        "max_amount": Decimal("30000000.00"),
        "min_term_months": 12,
        "max_term_months": 60,
        "annual_rate": Decimal("27.0000"),
        "rules_version": CATALOG_VERSION,
        "catalog_reference": dict(PUBLIC_REFERENCE),
    }

"""Upgrade only untouched built-in demo products; never rewrite credit history."""

from decimal import Decimal

from django.db import migrations


def upgrade_catalog(apps, schema_editor):
    Product = apps.get_model("products", "CreditProduct")
    # Freeze evidence in this migration; future catalogue edits cannot change it.
    reference = {
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
    for code, identifier, minimum, maximum, months, rate in [
        ("working-capital", 101, "100000", "5000000", 6, "18"),
        ("equipment", 102, "200000", "10000000", 12, "16"),
    ]:
        import uuid

        Product.objects.using(schema_editor.connection.alias).filter(
            pk=uuid.UUID(int=identifier),
            code=code,
            rules_version="demo-1",
            min_amount=Decimal(minimum),
            max_amount=Decimal(maximum),
            min_term_months=months,
            max_term_months=36 if code == "working-capital" else 60,
            annual_rate=Decimal(rate),
            catalog_reference__isnull=True,
            active=True,
        ).update(
            min_amount=Decimal("300000.00"),
            max_amount=Decimal("30000000.00"),
            min_term_months=12,
            max_term_months=60,
            annual_rate=Decimal("27.0000"),
            rules_version="research-2026-10-25",
            catalog_reference=reference,
        )


class Migration(migrations.Migration):
    dependencies = [("products", "0002_add_catalog_reference")]
    # Rolling back must not replace rates used by newly-created applications.
    operations = [migrations.RunPython(upgrade_catalog, migrations.RunPython.noop)]

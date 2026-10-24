"""Typed documentation for server-generated, versioned JSON; no arbitrary JSON inputs."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


def obj(properties, *, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


STRING = {"type": "string"}
UUID = {"type": "string", "format": "uuid"}
VERSION = {"type": "integer", "enum": [1]}
MONEY = {"type": "string", "pattern": r"^-?\d+\.\d{2}$", "example": "1000000.00"}
RATE = {"type": "string", "pattern": r"^\d+(\.\d+)?$", "example": "18.0000"}
MONTHS = {"type": "integer", "minimum": 1, "maximum": 120}
CHECK_KIND = {"type": "string", "enum": ["registry", "credit_history", "financial"]}
FINANCIAL_NAMES = ["monthly_revenue", "monthly_expenses", "monthly_debt_payments"]
FINANCES = obj({name: {**MONEY, "nullable": True} for name in FINANCIAL_NAMES})
SCHEDULE = obj(
    {
        "schema_version": VERSION,
        "method": {"type": "string", "enum": ["demo_annuity_monthly"]},
        "fees": {"type": "string", "enum": ["0.00"]},
        "rows": {
            "type": "array",
            "minItems": 1,
            "maxItems": 120,
            "items": obj(
                {
                    "month": MONTHS,
                    **{name: MONEY for name in ("payment", "principal", "interest", "balance")},
                }
            ),
        },
    }
)
FACTORS = obj(
    {
        "schema_version": VERSION,
        "failed_checks": {"type": "array", "items": CHECK_KIND},
        "monthly_cashflow": MONEY,
        "payment_capacity": MONEY,
        "capacity_fraction": {"type": "string", "enum": ["0.50"]},
    }
)
CHECK_RESULT = {
    "oneOf": [
        obj(
            {
                "schema_version": VERSION,
                "registration_status": {"type": "string", "enum": ["active", "inactive"]},
                "retryable": {"type": "boolean"},
            }
        ),
        obj({"schema_version": VERSION, "overdue": {"type": "boolean"}}),
        obj(
            {
                "schema_version": VERSION,
                "missing_fields": {
                    "type": "array",
                    "items": {"type": "string", "enum": FINANCIAL_NAMES},
                },
            }
        ),
    ],
    "description": "Форма соответствует kind: registry, credit_history или financial. Локальные синтетические адаптеры v1; ошибка не является кредитным отказом.",
}
SUBMITTED_SNAPSHOT = obj(
    {
        "schema_version": VERSION,
        "company": obj(
            {
                "id": UUID,
                "inn": STRING,
                "name": STRING,
                "status": {"type": "string", "enum": ["active", "inactive"]},
                "registered_at": {"type": "string", "format": "date"},
                "demo_scenario": {
                    "type": "string",
                    "enum": ["standard", "bad_history", "check_error"],
                },
                "is_existing_client": {"type": "boolean"},
            }
        ),
        "product": obj(
            {
                "id": UUID,
                "code": STRING,
                "rules_version": STRING,
                "annual_rate": RATE,
                "min_amount": MONEY,
                "max_amount": MONEY,
                "min_term_months": MONTHS,
                "max_term_months": MONTHS,
            }
        ),
        "financial": FINANCES,
    }
)
INPUT_SNAPSHOT = {
    "oneOf": [
        {"type": "object", "maxProperties": 0, "additionalProperties": False},
        SUBMITTED_SNAPSHOT,
    ],
    "description": "В черновике строго {}; после отправки неизменяемый снимок v1. Сумма, срок и цель находятся в полях ревизии.",
}
TERMS_SNAPSHOT = obj(
    {
        "schema_version": VERSION,
        "offer_id": UUID,
        "company_id": UUID,
        "amount": MONEY,
        "annual_rate": RATE,
        "term_months": MONTHS,
        "monthly_payment": MONEY,
        "schedule": SCHEDULE,
        "signature_mode": {"type": "string", "enum": ["simulation"]},
    }
)
EVENT_DETAILS = obj(
    {
        "schema_version": VERSION,
        "attempt": {"type": "integer", "minimum": 1, "maximum": 5},
        "retryable": {"type": "boolean"},
        "revision_no": {"type": "integer", "minimum": 1},
        "reason_code": STRING,
        "outcome": {"type": "string", "enum": ["approved", "counteroffer", "rejected"]},
        "disbursement_id": UUID,
        "is_simulated": {"type": "boolean", "enum": [True]},
        "signature_mode": {"type": "string", "enum": ["simulation"]},
        "assigned_to": UUID,
        "reason": {"type": "string", "enum": ["manual", "terminal_state"]},
    },
    required=["schema_version"],
)
EVENT_DETAILS["description"] = (
    "Безопасные метаданные v1; набор ключей зависит от event_type. Нет документов, секретов или произвольного пользовательского JSON. assignment_*: assigned_to; освобождение также reason."
)


@extend_schema_field(SCHEDULE)
class ScheduleField(serializers.JSONField):
    pass


@extend_schema_field(FACTORS)
class FactorsField(serializers.JSONField):
    pass


@extend_schema_field(CHECK_RESULT)
class CheckResultField(serializers.JSONField):
    pass


@extend_schema_field(INPUT_SNAPSHOT)
class InputSnapshotField(serializers.JSONField):
    pass


@extend_schema_field(TERMS_SNAPSHOT)
class TermsSnapshotField(serializers.JSONField):
    pass


@extend_schema_field(EVENT_DETAILS)
class EventDetailsField(serializers.JSONField):
    pass

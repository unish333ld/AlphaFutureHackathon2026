"""Closed schemas for the server-owned blocks shown by the assistant."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from api.contracts import MONEY, MONTHS, RATE, STRING, UUID, obj
from applications.actions import ACTION_NAMES, REASON_CODES
from applications.models import Application

DATE = {"type": "string", "format": "date-time"}
PRODUCT = obj(
    {
        "id": UUID,
        "code": STRING,
        "name": STRING,
        "description": STRING,
        "min_amount": MONEY,
        "max_amount": MONEY,
        "min_term_months": MONTHS,
        "max_term_months": MONTHS,
        "demo_annual_rate": RATE,
    }
)
DRAFT = obj(
    {
        "company": UUID,
        "product": UUID,
        "amount": MONEY,
        "term_months": MONTHS,
        "purpose": STRING,
        "requires_user_confirmation": {"type": "boolean", "enum": [True]},
    }
)
MISSING = obj(
    {
        "state": {"type": "string", "enum": ["missing_information"]},
        "required_fields": {
            "type": "array",
            "items": {"type": "string", "enum": ["ambiguity", "product", "amount", "term_months"]},
        },
    }
)
UNKNOWN = obj(
    {
        "error": {"type": "string", "enum": ["unknown_product_code"]},
        "message": STRING,
        "available_products": {"type": "array", "items": obj({"code": STRING, "name": STRING})},
    }
)
ACTION = obj(
    {
        "action": {"type": "string", "enum": list(ACTION_NAMES)},
        "allowed": {"type": "boolean"},
        "reason_code": {"type": "string", "enum": [*REASON_CODES, None], "nullable": True},
        "target_id": {**UUID, "nullable": True},
    }
)
STATUS = obj(
    {
        "application_id": UUID,
        "number": STRING,
        "status": {"type": "string", "enum": list(Application.Status.values)},
        "lock_version": {"type": "integer", "minimum": 0},
        "product": STRING,
        "available_actions": {"type": "array", "items": ACTION},
        "request": obj(
            {
                "amount": MONEY,
                "term_months": MONTHS,
                "purpose": STRING,
                "revision_no": {"type": "integer"},
            }
        ),
        "missing_information": {"type": "array", "items": STRING},
        "decision": obj(
            {
                "outcome": {"type": "string", "enum": ["approved", "counteroffer", "rejected"]},
                "reason_code": STRING,
                "explanation": STRING,
            }
        ),
        "offer": obj(
            {
                "status": STRING,
                "amount": MONEY,
                "annual_rate": RATE,
                "term_months": MONTHS,
                "monthly_payment": MONEY,
                "expires_at": DATE,
                "sign_before": {**DATE, "nullable": True},
            }
        ),
        "signed": {"type": "boolean"},
        "issued": {"type": "boolean"},
    },
    required=["application_id", "number", "status", "lock_version", "product", "available_actions"],
)
DATA = {
    "get_company_profile": obj(
        {
            "company_id": UUID,
            "name": STRING,
            "kind": STRING,
            "registered_at": {"type": "string", "format": "date"},
            "status": STRING,
            "monthly_financial_history_available": {"type": "boolean"},
        }
    ),
    "list_credit_products": obj({"products": {"type": "array", "items": PRODUCT}}),
    "get_application_status": {
        "oneOf": [STATUS, obj({"state": {"type": "string", "enum": ["no_application_selected"]}})]
    },
    "calculate_payment": {
        "oneOf": [
            obj(
                {
                    "product_code": STRING,
                    "amount": MONEY,
                    "term_months": MONTHS,
                    "demo_annual_rate": RATE,
                    "monthly_payment": MONEY,
                    "total_overpayment": MONEY,
                    "is_preliminary": {"type": "boolean", "enum": [True]},
                }
            ),
            UNKNOWN,
            MISSING,
        ]
    },
    "suggest_application_draft": {"oneOf": [DRAFT, UNKNOWN, MISSING]},
}
FACTS = {
    "type": "array",
    "maxItems": 2,
    "items": {
        "oneOf": [
            obj({"id": STRING, "source": {"type": "string", "enum": [source]}, "data": data})
            for source, data in DATA.items()
        ]
    },
}


@extend_schema_field(FACTS)
class FactsField(serializers.JSONField):
    pass


@extend_schema_field(
    {"oneOf": [{"type": "object", "maxProperties": 0, "additionalProperties": False}, DRAFT]}
)
class DraftField(serializers.JSONField):
    pass

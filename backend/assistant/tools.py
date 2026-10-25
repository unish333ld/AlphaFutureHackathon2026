"""Narrow, read-only facts for the client assistant."""

from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import serializers

from api.selectors import application_queryset
from api.serializers import StrictSerializer
from applications.actions import available_actions, latest_revision
from applications.services import validate_terms
from assistant.intent import resolve_product
from common.access import require_member
from products.calculations import payment_schedule
from products.models import CreditProduct


class PaymentArguments(StrictSerializer):
    product_code = serializers.CharField(max_length=64)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    term_months = serializers.IntegerField(min_value=1, max_value=120)


class DraftArguments(PaymentArguments):
    purpose = serializers.CharField(max_length=500)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_company_profile",
            "description": "Получить базовый профиль выбранной компании. Помесячной финансовой истории нет.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_credit_products",
            "description": "Получить доступные демонстрационные кредитные продукты и границы условий.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_payment",
            "description": "Серверный предварительный расчёт платежа по демо-продукту. Не является одобрением.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_code": {"type": "string"},
                    "amount": {
                        "type": "string",
                        "description": "Сумма в рублях, например 1000000.00",
                    },
                    "term_months": {"type": "integer"},
                },
                "required": ["product_code", "amount", "term_months"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_application_status",
            "description": "Получить статус и следующий шаг выбранной при создании диалога заявки.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_application_draft",
            "description": "Предложить поля черновика для подтверждения клиентом. Ничего не записывает.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_code": {"type": "string"},
                    "amount": {"type": "string"},
                    "term_months": {"type": "integer"},
                    "purpose": {"type": "string"},
                },
                "required": ["product_code", "amount", "term_months", "purpose"],
                "additionalProperties": False,
            },
        },
    },
]


def _product(data):
    product = resolve_product(data["product_code"])
    if product is None:
        return None
    validate_terms(data, product)
    return product


def _unknown_product():
    return {
        "error": "unknown_product_code",
        "message": "Не удалось найти выбранный кредитный продукт. Сначала уточните доступные продукты.",
        "available_products": list(
            CreditProduct.objects.filter(active=True).order_by("code").values("code", "name")
        ),
    }


def run_tool(user, conversation, name, arguments, *, evidence=None):
    require_member(user, conversation.company_id)
    if not isinstance(arguments, dict):
        raise serializers.ValidationError("Аргументы инструмента должны быть объектом.")

    if name == "get_company_profile":
        if arguments:
            raise serializers.ValidationError("Инструмент не принимает аргументы.")
        company = conversation.company
        return {
            "company_id": str(company.id),
            "name": company.name,
            "kind": company.kind,
            "registered_at": company.registered_at.isoformat(),
            "status": company.status,
            "monthly_financial_history_available": False,
        }

    if name == "list_credit_products":
        if arguments:
            raise serializers.ValidationError("Инструмент не принимает аргументы.")
        return {
            "products": [
                {
                    "code": product.code,
                    "id": str(product.id),
                    "name": product.name,
                    "description": product.description,
                    "min_amount": str(product.min_amount),
                    "max_amount": str(product.max_amount),
                    "min_term_months": product.min_term_months,
                    "max_term_months": product.max_term_months,
                    "demo_annual_rate": str(product.annual_rate),
                }
                for product in CreditProduct.objects.filter(active=True).order_by("code")
            ]
        }

    if name == "calculate_payment":
        data = PaymentArguments(data=arguments)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        product = _product(values)
        if product is None:
            return _unknown_product()
        missing = _verify_evidence(conversation, values, product, evidence)
        if missing:
            return missing
        monthly_payment, schedule = payment_schedule(
            values["amount"], product.annual_rate, values["term_months"]
        )
        total_paid = sum((Decimal(row["payment"]) for row in schedule["rows"]), Decimal(0))
        return {
            "product_code": product.code,
            "amount": str(values["amount"]),
            "term_months": values["term_months"],
            "demo_annual_rate": str(product.annual_rate),
            "monthly_payment": str(monthly_payment),
            "total_overpayment": str(total_paid - values["amount"]),
            "is_preliminary": True,
        }

    if name == "get_application_status":
        if arguments:
            raise serializers.ValidationError("Инструмент не принимает аргументы.")
        if not conversation.application_id:
            return {"state": "no_application_selected"}
        app = get_object_or_404(
            application_queryset(user),
            pk=conversation.application_id,
            company_id=conversation.company_id,
        )
        revision = latest_revision(app)
        result = {
            "application_id": str(app.id),
            "number": app.number,
            "status": app.status,
            "lock_version": app.lock_version,
            "product": app.product.name,
            "available_actions": [
                {**action, "target_id": str(action["target_id"]) if action["target_id"] else None}
                for action in available_actions(app, user)
                if action["action"]
                in {
                    "update_draft",
                    "submit",
                    "retry_checks",
                    "provide_information",
                    "revise",
                    "accept_offer",
                    "decline_offer",
                    "sign_agreement",
                }
            ],
        }
        if revision:
            result["request"] = {
                "amount": str(revision.amount),
                "term_months": revision.term_months,
                "purpose": revision.purpose,
                "revision_no": revision.revision_no,
            }
            result["missing_information"] = list(
                revision.information_requests.filter(response_revision__isnull=True).values_list(
                    "question", flat=True
                )[:5]
            )
            assessment = getattr(revision, "assessment", None)
            decision = getattr(assessment, "decision", None)
            if decision:
                result["decision"] = {
                    "outcome": decision.outcome,
                    "reason_code": decision.reason_code,
                    "explanation": decision.explanation,
                }
                offer = getattr(decision, "offer", None)
                if offer:
                    result["offer"] = {
                        "status": offer.status,
                        "amount": str(offer.amount),
                        "annual_rate": str(offer.annual_rate),
                        "term_months": offer.term_months,
                        "monthly_payment": str(offer.monthly_payment),
                        "expires_at": offer.expires_at.isoformat(),
                        "sign_before": offer.sign_before.isoformat() if offer.sign_before else None,
                    }
                    agreement = getattr(offer, "agreement", None)
                    result["signed"] = bool(agreement and agreement.signed_at)
                    result["issued"] = bool(agreement and getattr(agreement, "disbursement", None))
        return result

    if name == "suggest_application_draft":
        data = DraftArguments(data=arguments)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        product = _product(values)
        if product is None:
            return _unknown_product()
        missing = _verify_evidence(conversation, values, product, evidence)
        if missing:
            return missing
        purpose = values["purpose"]
        if evidence is not None:
            # A model cannot invent a purpose or use it to smuggle instructions into a form.
            purpose = evidence.get("purpose") or (
                "Пополнение оборотных средств"
                if product.code == "working-capital"
                else "Приобретение оборудования"
            )
        return {
            "company": str(conversation.company_id),
            "product": str(product.id),
            "amount": str(values["amount"]),
            "term_months": values["term_months"],
            "purpose": purpose,
            "requires_user_confirmation": True,
        }

    raise serializers.ValidationError("Неизвестный инструмент помощника.")


def _verify_evidence(conversation, values, product, evidence):
    if evidence is None:
        # Direct service callers may only use this for explicit, already validated inputs.
        return None
    missing = []
    if evidence.get("ambiguous"):
        missing.append("ambiguity")
    if not conversation.selected_product_id or conversation.selected_product_id != product.id:
        missing.append("product")
    for field in ("amount", "term_months"):
        if field not in evidence or str(values[field]) != str(evidence[field]):
            missing.append(field)
    if missing:
        return {"state": "missing_information", "required_fields": missing}
    return None

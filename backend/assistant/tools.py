"""Narrow, read-only facts for the client assistant."""

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from api.serializers import StrictSerializer
from applications.models import Application
from applications.services import validate_terms
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
    product = CreditProduct.objects.filter(code=data["product_code"], active=True).first()
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


def run_tool(user, conversation, name, arguments):
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
            Application.objects.select_related("company", "product"),
            pk=conversation.application_id,
            company_id=conversation.company_id,
        )
        revision = app.revisions.order_by("-revision_no").first()
        result = {
            "application_id": str(app.id),
            "status": app.status,
            "lock_version": app.lock_version,
            "product": app.product.name,
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
            result["checks"] = list(
                revision.checks.values("kind", "status", "is_mock").order_by("-attempt", "kind")[:6]
            )
            try:
                decision = revision.assessment.decision
            except ObjectDoesNotExist:
                decision = None
            if decision:
                result["decision"] = {
                    "outcome": decision.outcome,
                    "reason_code": decision.reason_code,
                    "explanation": decision.explanation,
                }
                try:
                    offer = decision.offer
                except ObjectDoesNotExist:
                    offer = None
                if offer:
                    result["offer"] = {
                        "status": offer.status,
                        "amount": str(offer.amount),
                        "annual_rate": str(offer.annual_rate),
                        "term_months": offer.term_months,
                        "monthly_payment": str(offer.monthly_payment),
                    }
        return result

    if name == "suggest_application_draft":
        data = DraftArguments(data=arguments)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        product = _product(values)
        if product is None:
            return _unknown_product()
        return {
            "company": str(conversation.company_id),
            "product": str(product.id),
            "amount": str(values["amount"]),
            "term_months": values["term_months"],
            "purpose": values["purpose"],
            "requires_user_confirmation": True,
        }

    raise serializers.ValidationError("Неизвестный инструмент помощника.")

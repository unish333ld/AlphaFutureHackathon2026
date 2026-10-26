"""Server-owned steps; providers may explain facts but cannot choose UI actions."""

import copy
import logging
import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from applications.models import Application
from assistant import services
from assistant.llm import AssistantUnavailable
from assistant.models import Conversation, Interaction, Message
from assistant.tools import run_tool
from common.access import require_member
from common.exceptions import Conflict
from products.models import CreditProduct

logger = logging.getLogger(__name__)


def display_name(value):
    return re.sub(r"\s*·\s*демо$", "", re.sub(r"^Демо\s*·\s*", "", value), flags=re.I)


def initial():
    return {"stage": "start", "values": {}}


@transaction.atomic
def resume(user, company_id, application_id=None):
    get_object_or_404(
        User.objects.select_for_update(), pk=user.pk, is_active=True, system_role="client"
    )
    require_member(user, company_id)
    if application_id:
        get_object_or_404(Application, pk=application_id, company_id=company_id)
    conversation = (
        services.visible_conversations(user)
        .filter(company_id=company_id, application_id=application_id)
        .exclude(flow_context={})
        .first()
    )
    if conversation is None:
        conversation = Conversation.objects.create(
            user=user, company_id=company_id, application_id=application_id, flow_context=initial()
        )
    return conversation


def step_id(conversation):
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"credit-assistant/{conversation.pk}/{conversation.version}"
    )


def _choices(conversation, state):
    stage = state["stage"]
    if stage == "start":
        choices = [
            ("prepare", "Подготовить заявку"),
            ("payment", "Рассчитать платёж"),
            ("products", "Посмотреть продукты"),
            ("question", "Задать вопрос"),
        ]
        if conversation.application_id:
            choices.insert(0, ("status", "Разобраться с заявкой"))
        return choices
    if stage == "product":
        return [
            (f"product:{product.code}", display_name(product.name))
            for product in CreditProduct.objects.filter(active=True).order_by("code")
        ]
    if stage == "result":
        choices = [("start", "Выбрать другую задачу"), ("question", "Задать вопрос")]
        if state.get("message_id") and not state.get("draft_ready"):
            message = conversation.messages.filter(pk=state["message_id"]).first()
            if message and message.suggested_draft:
                choices.insert(0, ("apply_draft", "Проверить параметры заявки"))
        return choices
    if stage == "error":
        choices = [("retry", "Повторить запрос")]
        if state.get("retry_state", {}).get("stage") in {"amount", "term", "question"}:
            choices.append(("edit_input", "Исправить ответ"))
        return [*choices, ("start", "Выбрать другую задачу")]
    return []


def state_for(user, conversation_id):
    conversation = services._owned_conversation(user, conversation_id)
    if not conversation.flow_context:
        raise Conflict("Этот диалог не поддерживает пошаговый режим.", code="flow_required")
    # An interrupted worker must not leave the account waiting forever. A late
    # worker checks the journal again before committing and cannot resurrect it.
    pending = conversation.interactions.filter(state="pending").first()
    if pending and pending.created_at < timezone.now() - timedelta(
        seconds=settings.LLM_TOTAL_TIMEOUT_SECONDS + 20
    ):
        _fail(user, conversation.pk, pending.pk, "request_interrupted")
        conversation.refresh_from_db()
        pending = None
    state = conversation.flow_context
    stage = state["stage"]
    mode = (
        "waiting"
        if pending
        else "choice"
        if stage in {"start", "product"}
        else stage
        if stage in {"result", "error"}
        else "input"
    )
    prompts = {
        "start": "С чем помочь?",
        "product": "Для какой задачи нужен кредит?",
        "amount": "Какая сумма нужна?",
        "term": "На какой срок?",
        "question": "Что хотите узнать?",
        "result": "Результат",
        "error": "Не удалось получить ответ",
    }
    message = (
        conversation.messages.filter(pk=state.get("message_id")).first()
        if state.get("message_id")
        else None
    )
    last = conversation.interactions.order_by("-created_at", "-id").first()
    input_value = state.get("input_value", "")
    if stage in {"amount", "term", "question"}:
        previous = (
            conversation.interactions.filter(
                step_id=step_id(conversation), error_code="invalid_input"
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if previous:
            input_value = previous.payload.get("text", input_value)
        elif pending:
            input_value = pending.payload.get("text", input_value)
    input_state = {
        "kind": "money" if stage == "amount" else "months" if stage == "term" else "text",
        "label": prompts.get(stage, "Ваш вопрос"),
        "hint": "Сумма в рублях, например 1000000,50"
        if stage == "amount"
        else "Целое число месяцев, например 24"
        if stage == "term"
        else "Вопрос о продукте, условиях или заявке",
        "value": input_value,
        "max_length": 2000 if stage == "question" else 32,
    }
    return {
        "conversation_id": conversation.pk,
        "company": conversation.company_id,
        "application": conversation.application_id,
        "version": conversation.version,
        "step_id": step_id(conversation),
        "mode": mode,
        "title": prompts.get(stage, "Результат"),
        "prompt": "Готовим ответ. Заявка остаётся доступной."
        if pending
        else state.get("prompt", ""),
        "choices": []
        if pending
        else [{"id": key, "label": label} for key, label in _choices(conversation, state)],
        "input": input_state if mode == "input" else None,
        "message": message,
        "pending_request_id": pending.request_id if pending else None,
        "last_request_id": last.request_id if last else None,
        "error_code": state.get("error_code"),
        "draft_ready": bool(state.get("draft_ready")),
        "saved_input": state.get("saved_input", ""),
    }


def _message(conversation, content, facts=None, suggested=None):
    return {
        "content": content,
        "facts": facts or [],
        "suggested_draft": suggested or {},
        "questions": [],
        "reply_type": "draft_suggestion" if suggested else "answer",
        "model_status": "available",
    }


def _advance(user, conversation, payload):
    state = copy.deepcopy(conversation.flow_context)
    action = payload.get("action_id")
    text = payload.get("text", "").strip()
    stage = state["stage"]
    if action == "retry":
        state = copy.deepcopy(state["retry_state"])
        conversation.flow_context = state
        return _advance(user, conversation, state.pop("retry_payload"))
    if action == "start":
        return initial(), None
    if action == "edit_input":
        restored = copy.deepcopy(state["retry_state"])
        restored.pop("retry_payload", None)
        restored["input_value"] = state.get("saved_input", "")
        return restored, None
    if action == "question":
        return {**state, "stage": "question", "input_value": ""}, None
    if action == "apply_draft":
        # Only authorizes showing a preview; the existing form still needs its
        # own explicit confirmation and server validation when it is saved.
        return {**state, "draft_ready": True}, None
    if stage == "start":
        if action in {"prepare", "payment"}:
            return {"stage": "product", "intent": action, "values": {}}, None
        tool = "get_application_status" if action == "status" else "list_credit_products"
        result = run_tool(user, conversation, tool, {})
        return {**state, "stage": "result"}, _message(
            conversation,
            "Данные вашей заявки."
            if action == "status"
            else "Выберите продукт при подготовке заявки.",
            [{"id": "fact_1", "source": tool, "data": result}],
        )
    if stage == "product":
        product = get_object_or_404(
            CreditProduct, code=action.removeprefix("product:"), active=True
        )
        conversation.selected_product = product
        state["values"]["product_code"] = product.code
        return {**state, "stage": "amount"}, None
    if stage in {"amount", "term"}:
        product = get_object_or_404(
            CreditProduct, code=state["values"]["product_code"], active=True
        )
        if stage == "amount":
            normalized = text.replace(" ", "").replace("\u00a0", "").replace(",", ".")
            if not re.fullmatch(r"\d{1,16}(\.\d{1,2})?", normalized):
                raise ValidationError(
                    {"text": "Укажите сумму в рублях, не более двух знаков после запятой."}
                )
            amount = Decimal(normalized)
            if not product.min_amount <= amount <= product.max_amount:
                raise ValidationError(
                    {
                        "text": f"Укажите сумму от {product.min_amount:.2f} до {product.max_amount:.2f} ₽."
                    }
                )
            state["values"]["amount"] = f"{amount:.2f}"
            return {**state, "stage": "term"}, None
        if (
            not re.fullmatch(r"\d{1,3}", text)
            or not product.min_term_months <= int(text) <= product.max_term_months
        ):
            raise ValidationError(
                {
                    "text": f"Укажите целое число от {product.min_term_months} до {product.max_term_months} месяцев."
                }
            )
        state["values"]["term_months"] = int(text)
        if state["intent"] == "payment":
            tool, arguments, content = (
                "calculate_payment",
                state["values"],
                "Предварительный расчёт готов.",
            )
        else:
            tool = "suggest_application_draft"
            arguments = {
                **state["values"],
                "purpose": "Пополнение оборотных средств"
                if product.code == "working-capital"
                else "Приобретение оборудования",
            }
            content = "Параметры готовы. Проверьте их в форме и заполните финансовые показатели."
        result = run_tool(user, conversation, tool, arguments)
        return {**state, "stage": "result"}, _message(
            conversation,
            content,
            [{"id": "fact_1", "source": tool, "data": result}],
            result if tool == "suggest_application_draft" else None,
        )
    if stage == "question":
        content, facts, suggested, questions, reply_type, model_status = services._answer(
            user, conversation, text
        )
        return {**state, "stage": "result"}, {
            "content": content,
            "facts": facts,
            "suggested_draft": suggested,
            "questions": questions,
            "reply_type": reply_type,
            "model_status": model_status,
        }
    raise Conflict("Этот шаг уже завершён.", code="stale_step")


def _fail(user, conversation_id, interaction_id, code):
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation_id, user=user)
        interaction = Interaction.objects.select_for_update().get(
            pk=interaction_id, conversation=conversation
        )
        if interaction.state != "pending":
            return
        previous = copy.deepcopy(conversation.flow_context)
        if previous["stage"] == "error" and interaction.payload.get("action_id") == "retry":
            saved_input = previous.get("saved_input", "")
            previous = previous["retry_state"]
        else:
            previous["retry_payload"] = interaction.payload
            saved_input = interaction.payload.get("text", "")
        conversation.flow_context = {
            "stage": "error",
            "values": previous.get("values", {}),
            "retry_state": previous,
            "saved_input": saved_input,
            "error_code": code,
            "prompt": "Ответ не получен. Ввод сохранён. Повторите запрос или продолжите заявку без помощника.",
        }
        conversation.version += 1
        conversation.save(update_fields=["flow_context", "version", "updated_at"])
        interaction.state, interaction.error_code, interaction.finished_at = (
            "failed",
            code,
            timezone.now(),
        )
        interaction.save(update_fields=["state", "error_code", "finished_at"])


def act(user, conversation_id, data):
    payload = {key: data[key] for key in ("action_id", "text") if key in data}
    with transaction.atomic():
        conversation = get_object_or_404(
            Conversation.objects.select_for_update(),
            pk=conversation_id,
            user=user,
            updated_at__gte=timezone.now() - timedelta(days=settings.AI_HISTORY_DAYS),
        )
        require_member(user, conversation.company_id)
        if not settings.AI_ENABLED:
            raise AssistantUnavailable("Помощник отключён. Продолжите в форме заявки.")
        existing = conversation.interactions.filter(request_id=data["request_id"]).first()
        if existing:
            if existing.payload != payload or existing.step_id != data["step_id"]:
                raise Conflict("Идентификатор запроса уже использован.", code="request_mismatch")
            return state_for(user, conversation.pk)
        if (
            conversation.version != data["expected_version"]
            or step_id(conversation) != data["step_id"]
        ):
            raise Conflict("Шаг изменился. Проверьте текущий вопрос.", code="stale_step")
        if conversation.interactions.filter(state="pending").exists():
            raise Conflict("Ответ ещё готовится.", code="request_pending")
        state = conversation.flow_context
        if not state:
            raise Conflict("Нужен пошаговый сценарий.", code="flow_required")
        choices = {key for key, _ in _choices(conversation, state)}
        if choices:
            if payload.get("action_id") not in choices or "text" in payload:
                raise Conflict("Выберите один из текущих вариантов.", code="stale_action")
        elif "action_id" in payload or not payload.get("text", "").strip():
            raise ValidationError({"text": "Введите ответ на текущий вопрос."})
        interaction = Interaction.objects.create(
            conversation=conversation,
            request_id=data["request_id"],
            step_id=data["step_id"],
            payload=payload,
        )
    app_version = None
    if conversation.application_id:
        conversation.application.refresh_from_db()
        app_version = conversation.application.lock_version
    try:
        next_state, message_data = _advance(user, conversation, payload)
    except ValidationError:
        # Invalid fields are not completed steps and are safe to correct.
        with transaction.atomic():
            Conversation.objects.select_for_update().get(pk=conversation.pk)
            Interaction.objects.filter(pk=interaction.pk, state="pending").update(
                state="failed", error_code="invalid_input", finished_at=timezone.now()
            )
        raise
    except Exception as error:
        logger.warning(
            "assistant_request_failed request=%s error_type=%s",
            interaction.request_id,
            type(error).__name__,
        )
        _fail(user, conversation.pk, interaction.pk, "assistant_unavailable")
        return state_for(user, conversation.pk)
    with transaction.atomic():
        if conversation.application_id:
            app = Application.objects.select_for_update().get(pk=conversation.application_id)
            if app.lock_version != app_version:
                _fail(user, conversation.pk, interaction.pk, "application_changed")
                return state_for(user, conversation.pk)
        locked = get_object_or_404(
            Conversation.objects.select_for_update(),
            pk=conversation.pk,
            user=user,
            updated_at__gte=timezone.now() - timedelta(days=settings.AI_HISTORY_DAYS),
        )
        user.refresh_from_db(fields=["is_active", "system_role"])
        if not user.is_active or user.system_role != "client":
            raise PermissionDenied("Помощник доступен только клиенту.")
        require_member(user, locked.company_id)
        journal = Interaction.objects.select_for_update().get(pk=interaction.pk)
        if journal.state != "pending" or locked.version != data["expected_version"]:
            raise Conflict("Состояние изменилось во время ответа.", code="stale_step")
        if message_data:
            message_payload = payload
            if payload.get("action_id") == "retry":
                message_payload = state.get("retry_state", {}).get("retry_payload", payload)
            Message.objects.create(
                conversation=locked,
                role="user",
                content=message_payload.get("text") or message_payload.get("action_id"),
            )
            message = Message.objects.create(
                conversation=locked,
                role="assistant",
                application_version=app_version,
                **message_data,
            )
            next_state["message_id"] = str(message.pk)
            journal.message = message
        locked.flow_context = next_state
        locked.selected_product_id = conversation.selected_product_id
        locked.version += 1
        locked.save(update_fields=["flow_context", "selected_product", "version", "updated_at"])
        journal.state, journal.finished_at = "completed", timezone.now()
        journal.save(update_fields=["state", "finished_at", "message"])
    return state_for(user, locked.pk)

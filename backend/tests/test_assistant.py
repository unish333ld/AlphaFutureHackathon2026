import json
from unittest.mock import patch

from applications.models import Application
from assistant.models import Conversation, Message
from decisions.models import CreditDecision


def endpoint(api, user, method, suffix="", data=None):
    api.force_authenticate(user=user)
    return getattr(api, method)(f"/api/v1/assistant/conversations/{suffix}", data, format="json")


def new_conversation(api, user, app):
    response = endpoint(
        api,
        user,
        "post",
        data={"company_id": str(app.company_id), "application_id": str(app.id)},
    )
    assert response.status_code == 201, response.data
    return response.data["id"]


def test_conversation_scope_and_application_binding(demo, api):
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    assert endpoint(api, demo["client"], "get").data["count"] == 1
    assert endpoint(api, demo["outsider"], "get").data["count"] == 0
    assert endpoint(api, demo["outsider"], "get", f"{conversation_id}/").status_code == 404
    assert endpoint(api, demo["specialist"], "get", f"{conversation_id}/").status_code == 403
    assert (
        endpoint(
            api, demo["outsider"], "post", data={"company_id": str(app.company_id)}
        ).status_code
        == 404
    )
    other_app = demo["applications"]["rejected"]
    assert (
        endpoint(
            api,
            demo["client"],
            "post",
            data={"company_id": str(app.company_id), "application_id": str(other_app.id)},
        ).status_code
        == 404
    )


def test_disabled_assistant_keeps_dialogue_and_application_unchanged(demo, api, settings):
    settings.AI_ENABLED = False
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    response = endpoint(
        api,
        demo["client"],
        "post",
        f"{conversation_id}/messages/",
        {"text": "Какой статус?", "expected_version": 0},
    )
    assert response.status_code == 503
    assert Message.objects.count() == 0
    assert Conversation.objects.get(pk=conversation_id).version == 0
    app.refresh_from_db()
    assert app.lock_version == 0


def test_payment_fact_is_computed_by_server_without_credit_decision(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    first = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "calculate_payment",
                    "arguments": json.dumps(
                        {
                            "product_code": app.product.code,
                            "amount": "1000000.00",
                            "term_months": 24,
                        }
                    ),
                },
            }
        ],
    }
    with patch(
        "assistant.services.chat", side_effect=[first, {"content": "Платёж предварительный."}]
    ):
        response = endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Какой платёж?", "expected_version": 0},
        )
    assert response.status_code == 200, response.data
    assert response.data["version"] == 1
    fact = response.data["message"]["facts"][0]
    assert fact["source"] == "calculate_payment"
    assert fact["data"]["monthly_payment"]
    assert fact["data"]["is_preliminary"] is True
    assert Message.objects.filter(conversation_id=conversation_id).count() == 2
    assert CreditDecision.objects.count() == 0
    assert Application.objects.get(pk=app.pk).lock_version == 0
    assert (
        endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Ещё раз", "expected_version": 0},
        ).status_code
        == 409
    )


def test_invalid_tool_arguments_do_not_persist_or_change_application(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    first = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "function": {
                    "name": "get_application_status",
                    "arguments": json.dumps(
                        {"application_id": str(demo["applications"]["rejected"].id)}
                    ),
                },
            }
        ],
    }
    with patch("assistant.services.chat", return_value=first):
        response = endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Покажи чужую заявку", "expected_version": 0},
        )
    assert response.status_code == 503
    assert Message.objects.count() == 0
    assert Application.objects.get(pk=app.pk).lock_version == 0


def test_model_numbers_are_replaced_with_safe_text(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    with patch("assistant.services.chat", return_value={"content": "Ставка точно 1%."}):
        response = endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Какая ставка?", "expected_version": 0},
        )
    assert response.status_code == 200
    assert "1%" not in response.data["message"]["content"]


def test_invented_rate_is_replaced_with_server_product_summary(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    first = {
        "content": None,
        "tool_calls": [
            {
                "id": "products_1",
                "function": {"name": "list_credit_products", "arguments": "{}"},
            }
        ],
    }
    with patch("assistant.services.chat", side_effect=[first, {"content": "Ставка точно 99%."}]):
        response = endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Какие продукты доступны?", "expected_version": 0},
        )
    assert response.status_code == 200
    content = response.data["message"]["content"]
    assert "99%" not in content
    assert app.product.name in content
    assert response.data["message"]["facts"][0]["source"] == "list_credit_products"


def test_draft_suggestion_requires_normal_application_api(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    first = {
        "content": None,
        "tool_calls": [
            {
                "id": "draft_1",
                "function": {
                    "name": "suggest_application_draft",
                    "arguments": json.dumps(
                        {
                            "product_code": app.product.code,
                            "amount": "1000000.00",
                            "term_months": 24,
                            "purpose": "Пополнение оборотных средств",
                        }
                    ),
                },
            }
        ],
    }
    before = Application.objects.count()
    with patch(
        "assistant.services.chat",
        side_effect=[first, {"content": "Предлагаю черновик для проверки."}],
    ):
        response = endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Подготовь черновик", "expected_version": 0},
        )
    assert response.status_code == 200, response.data
    draft = response.data["message"]["suggested_draft"]
    assert draft["company"] == str(app.company_id)
    assert draft["product"] == str(app.product_id)
    assert draft["requires_user_confirmation"] is True
    assert Application.objects.count() == before

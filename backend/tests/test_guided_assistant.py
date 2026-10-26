"""The step journal is the source of truth when a browser loses a response."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from assistant.models import Conversation, Interaction, Message


def call(api, user, method, path, body=None):
    api.force_authenticate(user=user)
    return getattr(api, method)(f"/api/v1/{path}", body, format="json")


def start(api, user, app):
    result = call(
        api,
        user,
        "post",
        "assistant/conversations/current/",
        {"company_id": str(app.company_id)},
    )
    assert result.status_code == 200, result.data
    return result.data


def send(api, user, step, **payload):
    return call(
        api,
        user,
        "post",
        f"assistant/conversations/{step['conversation_id']}/step/",
        {
            "step_id": step["step_id"],
            "expected_version": step["version"],
            "request_id": str(uuid.uuid4()),
            **payload,
        },
    )


def test_guided_choices_input_validation_replay_and_no_credit_mutation(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    original_version = app.lock_version
    client = demo["client"]
    step = start(api, client, app)
    assert step["mode"] == "choice" and step["input"] is None
    assert (
        call(
            api, demo["outsider"], "get", f"assistant/conversations/{step['conversation_id']}/step/"
        ).status_code
        == 404
    )
    assert send(api, client, step, text="Одобрить").status_code == 409
    request_id = str(uuid.uuid4())
    body = {
        "step_id": step["step_id"],
        "expected_version": step["version"],
        "request_id": request_id,
        "action_id": "prepare",
    }
    path = f"assistant/conversations/{step['conversation_id']}/step/"
    product_step = call(api, client, "post", path, body)
    assert product_step.status_code == 200, product_step.data
    assert product_step.data["mode"] == "choice"
    assert call(api, client, "post", path, body).data["step_id"] == product_step.data["step_id"]
    assert send(api, client, step, action_id="prepare").status_code == 409
    assert call(api, client, "post", path, {**body, "action_id": "payment"}).status_code == 409
    product = app.product
    amount_step = send(api, client, product_step.data, action_id=f"product:{product.code}")
    assert amount_step.status_code == 200, amount_step.data
    assert amount_step.data["mode"] == "input"
    assert send(api, client, amount_step.data, action_id="start").status_code == 400
    assert send(api, client, amount_step.data, text="неизвестно").status_code == 400
    reloaded = call(api, client, "get", path)
    assert reloaded.data["input"]["value"] == "неизвестно"
    term_step = send(api, client, amount_step.data, text="1000000,50")
    assert term_step.status_code == 200, term_step.data
    result = send(api, client, term_step.data, text="12")
    assert result.status_code == 200, result.data
    assert result.data["mode"] == "result"
    assert result.data["message"]["suggested_draft"]["amount"] == "1000000.50"
    assert Message.objects.filter(conversation_id=step["conversation_id"]).count() == 2
    assert (
        call(
            api,
            client,
            "post",
            f"assistant/conversations/{step['conversation_id']}/messages/",
            {"text": "Обход", "expected_version": result.data["version"]},
        ).status_code
        == 409
    )
    app.refresh_from_db()
    assert app.lock_version == original_version


def test_guided_failed_request_keeps_step_and_allows_controlled_retry(demo, api, settings):
    settings.AI_ENABLED = True
    user = demo["client"]
    step = start(api, user, demo["applications"]["approval"])
    with patch("assistant.flow._advance", side_effect=RuntimeError("private provider details")):
        failed = send(api, user, step, action_id="products")
    assert failed.status_code == 200
    assert failed.data["mode"] == "error"
    assert "private provider details" not in str(failed.data)
    assert Interaction.objects.get(conversation_id=step["conversation_id"]).state == "failed"
    retry = send(api, user, failed.data, action_id="retry")
    assert retry.status_code == 200, retry.data
    assert retry.data["mode"] == "result"
    assert retry.data["message"]["facts"][0]["source"] == "list_credit_products"
    assert (
        Message.objects.get(conversation_id=step["conversation_id"], role="user").content
        == "products"
    )


@pytest.mark.django_db(transaction=True)
def test_two_tabs_cannot_advance_one_step_twice(demo, settings):
    settings.AI_ENABLED = True
    user = demo["client"]
    initial = start(APIClient(), user, demo["applications"]["approval"])
    entered, release = Event(), Event()
    from assistant import flow

    original = flow._advance

    def delayed(*args):
        entered.set()
        assert release.wait(timeout=5), "The competing request did not complete"
        return original(*args)

    with (
        patch("assistant.flow._advance", side_effect=delayed),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        first = pool.submit(send, APIClient(), user, initial, action_id="prepare")
        assert entered.wait(timeout=5)
        second = send(APIClient(), user, initial, action_id="prepare")
        assert second.status_code == 409, second.data
        release.set()
        completed = first.result(timeout=5)
    assert completed.status_code == 200, completed.data
    assert Conversation.objects.get(pk=initial["conversation_id"]).version == 1
    assert (
        Interaction.objects.filter(
            conversation_id=initial["conversation_id"], state="completed"
        ).count()
        == 1
    )


def test_old_company_and_other_role_cannot_resume_or_act(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    step = start(api, demo["client"], app)
    assert (
        call(
            api,
            demo["specialist"],
            "post",
            "assistant/conversations/current/",
            {"company_id": str(app.company_id)},
        ).status_code
        == 403
    )
    assert send(api, demo["outsider"], step, action_id="prepare").status_code == 404
    assert Interaction.objects.filter(conversation_id=step["conversation_id"]).count() == 0

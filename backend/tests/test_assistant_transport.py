"""Provider routing and quota failures never grant the model business authority."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest
from django.core.cache import cache

from assistant.llm import AssistantUnavailable, chat
from assistant.models import Message
from tests.test_assistant import endpoint, new_conversation


def response(message, model=None):
    return io.BytesIO(json.dumps({"choices": [{"message": message}], "model": model}).encode())


def configure_router(settings):
    settings.LLM_PROVIDER = "openrouter"
    settings.LLM_BASE_URL = "https://openrouter.ai/api/v1"
    settings.LLM_API_KEY = "tests-only-key"
    settings.LLM_MODEL = "google/gemma-4-26b-a4b-it:free"
    settings.LLM_FALLBACK_MODELS = ("nvidia/nemotron-3.5-lightning:free",)
    settings.LLM_LOCAL_FALLBACK_BASE_URL = "http://127.0.0.1:11434/v1"
    settings.LLM_LOCAL_FALLBACK_MODEL = "qwen2.5:7b-instruct-q4_0"
    settings.LLM_TIMEOUT_SECONDS = 10
    cache.delete("assistant:openrouter-paused")


def test_openrouter_uses_explicit_free_models_and_pins_selected_model(settings):
    configure_router(settings)
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, json.loads(request.data), timeout))
        return response(
            {"content": "Готово."},
            "nvidia/nemotron-3.5-lightning",
        )

    with patch("assistant.llm.urlopen", side_effect=fake_urlopen):
        first = chat([{"role": "user", "content": "Привет"}], tools=[{"type": "function"}])
        chat([{"role": "user", "content": "Продолжи"}], model=first["_model"])

    assert first["_model"] == "nvidia/nemotron-3.5-lightning:free"
    assert calls[0][0] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls[0][1]["models"] == [
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3.5-lightning:free",
    ]
    assert calls[0][1]["tool_choice"] == "auto"
    assert calls[0][1]["provider"] == {
        "require_parameters": True,
        "max_price": {"prompt": 0, "completion": 0, "request": 0},
    }
    assert calls[1][1]["models"][0] == "nvidia/nemotron-3.5-lightning:free"
    assert "tools" not in calls[1][1]
    assert all(model.endswith(":free") for model in calls[1][1]["models"])


def test_rate_limit_uses_local_fallback_and_pauses_cloud(settings):
    configure_router(settings)
    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        if "openrouter.ai" in request.full_url:
            raise HTTPError(request.full_url, 429, "rate limit", {}, None)
        return response({"content": "Локальный ответ."})

    with patch("assistant.llm.urlopen", side_effect=fake_urlopen):
        first = chat([{"role": "user", "content": "Привет"}])
        second = chat([{"role": "user", "content": "Ещё"}], backend=first["_backend"])

    assert first["_backend"] == second["_backend"] == "local"
    assert urls.count("https://openrouter.ai/api/v1/chat/completions") == 1
    assert urls.count("http://127.0.0.1:11434/v1/chat/completions") == 2


def test_missing_key_uses_local_fallback_without_cloud_request(settings):
    configure_router(settings)
    settings.LLM_API_KEY = ""
    with patch("assistant.llm.urlopen", return_value=response({"content": "Локально."})) as send:
        result = chat([{"role": "user", "content": "Привет"}])
    assert result["_backend"] == "local"
    assert send.call_args.args[0].full_url.startswith("http://127.0.0.1:11434/")


def test_unlisted_response_model_never_enters_conversation(settings):
    configure_router(settings)
    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        if "openrouter.ai" in request.full_url:
            return response({"content": "Непроверенный ответ."}, "some-paid-or-closed-model")
        return response({"content": "Локальный ответ."})

    with patch("assistant.llm.urlopen", side_effect=fake_urlopen):
        result = chat([{"role": "user", "content": "Привет"}])
    assert result["_backend"] == "local"
    assert result["content"] == "Локальный ответ."
    assert len(urls) == 2


def test_empty_cloud_answer_uses_local_fallback(settings):
    configure_router(settings)

    def fake_urlopen(request, timeout):
        if "openrouter.ai" in request.full_url:
            return response({"content": ""}, "google/gemma-4-26b-a4b-it:free")
        return response({"content": "Локальный ответ."})

    with patch("assistant.llm.urlopen", side_effect=fake_urlopen):
        result = chat([{"role": "user", "content": "Привет"}])
    assert result["_backend"] == "local"
    assert result["content"] == "Локальный ответ."


def test_all_providers_down_returns_unavailable_without_leaking_key(settings):
    configure_router(settings)
    with patch("assistant.llm.urlopen", side_effect=URLError("network unavailable")):
        with pytest.raises(AssistantUnavailable) as error:
            chat([{"role": "user", "content": "Привет"}])
    assert "tests-only-key" not in str(error.value)


def test_final_model_failure_keeps_verified_facts(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    tool_call = {
        "content": None,
        "tool_calls": [
            {
                "id": "products_1",
                "function": {"name": "list_credit_products", "arguments": "{}"},
            }
        ],
    }
    with patch("assistant.services.chat", side_effect=[tool_call, AssistantUnavailable()]):
        result = endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Какие продукты доступны?", "expected_version": 0},
        )
    assert result.status_code == 200
    assert result.data["model_status"] == "degraded"
    assert result.data["message"]["facts"][0]["source"] == "list_credit_products"
    assert Message.objects.filter(conversation_id=conversation_id).count() == 2


def test_all_providers_down_before_tools_does_not_store_message(demo, api, settings):
    settings.AI_ENABLED = True
    app = demo["applications"]["approval"]
    conversation_id = new_conversation(api, demo["client"], app)
    with patch("assistant.services.chat", side_effect=AssistantUnavailable()):
        result = endpoint(
            api,
            demo["client"],
            "post",
            f"{conversation_id}/messages/",
            {"text": "Какие продукты доступны?", "expected_version": 0},
        )
    assert result.status_code == 503
    assert Message.objects.filter(conversation_id=conversation_id).count() == 0


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd/v1",
        "https://user:secret@example.test/v1",
        "https://example.test/v1?api_key=secret",
        "https://example.test/v1#secret",
        "https://example.test/invalid",
    ],
)
def test_provider_configuration_does_not_forward_embedded_credentials(settings, url):
    settings.LLM_PROVIDER = "compatible"
    settings.LLM_BASE_URL = url
    with patch("assistant.llm.urlopen") as send:
        with pytest.raises(AssistantUnavailable):
            chat([])
    send.assert_not_called()


@pytest.mark.parametrize("payload", [b"[]", b"null", b"not json", b"x" * 262145])
def test_malformed_or_oversized_provider_response_is_a_safe_error(settings, payload):
    settings.LLM_PROVIDER = "compatible"
    settings.LLM_BASE_URL = "https://example.test/v1"
    with patch("assistant.llm.urlopen", return_value=io.BytesIO(payload)):
        with pytest.raises(AssistantUnavailable):
            chat([])


def test_slow_drip_response_is_bounded_by_total_deadline(settings):
    from assistant.llm import _request, _TransportFailure

    settings.LLM_PROVIDER = "compatible"
    with (
        patch("assistant.llm.urlopen", return_value=io.BytesIO(b"x" * 20000)),
        patch("assistant.llm.monotonic", side_effect=[0, 0, 6, 11]),
    ):
        with pytest.raises(_TransportFailure):
            _request("https://example.test/v1", "", ["test-model"], [], None, 5)


def test_final_completion_requests_closed_json_schema_and_bounded_tokens(settings):
    settings.LLM_PROVIDER = "compatible"
    settings.LLM_BASE_URL = "https://example.test/v1"
    with patch("assistant.llm.urlopen", return_value=response({"content": "{}"})) as send:
        chat([])
    body = json.loads(send.call_args.args[0].data)
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert body["max_tokens"] == settings.LLM_MAX_OUTPUT_TOKENS


def test_provider_redirect_cannot_forward_authorization():
    from assistant.llm import _NoRedirect

    assert _NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test") is None


def test_saturated_provider_slot_fails_fast_and_does_not_queue_network(settings):
    from assistant.llm import PROVIDER_SLOT

    assert PROVIDER_SLOT.acquire(blocking=False)
    try:
        with patch("assistant.llm.urlopen") as send:
            with pytest.raises(AssistantUnavailable, match="Помощник занят"):
                chat([])
        send.assert_not_called()
    finally:
        PROVIDER_SLOT.release()
    settings.LLM_PROVIDER = "compatible"
    settings.LLM_BASE_URL = "https://example.test/v1"
    with patch("assistant.llm.urlopen", side_effect=URLError("unavailable")):
        with pytest.raises(AssistantUnavailable):
            chat([])
    # A transport failure must release the slot for a later explicit request.
    with patch("assistant.llm.urlopen", return_value=response({"content": "{}"})):
        assert chat([])["content"] == "{}"


def test_paid_slug_is_not_called_with_free_only_and_uses_local_model(settings):
    configure_router(settings)
    settings.LLM_MODEL = "nvidia/nemotron-3-super-120b-a12b"
    with patch("assistant.llm.urlopen", return_value=response({"content": "{}"})) as send:
        result = chat([])
    assert result["_backend"] == "local"
    assert send.call_count == 1
    assert send.call_args.args[0].full_url == "http://127.0.0.1:11434/v1/chat/completions"


@pytest.mark.parametrize(
    "provider,expected", [("openrouter", "router-test-key"), ("compatible", "")]
)
def test_openrouter_key_alias_is_never_forwarded_to_a_compatible_endpoint(
    monkeypatch, provider, expected
):
    import runpy
    from pathlib import Path

    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-test-key")
    config = runpy.run_path(str(Path(__file__).parents[1] / "config/settings.py"))
    assert config["LLM_API_KEY"] == expected


def test_live_capability_command_requires_real_probe_and_never_displays_key(settings):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.AI_ENABLED = False
    output = io.StringIO()
    with patch("assistant.management.commands.check_assistant.chat") as send:
        with pytest.raises(CommandError, match="AI_ENABLED=false"):
            call_command("check_assistant", live=True, stdout=output)
    send.assert_not_called()
    settings.AI_ENABLED = True
    settings.LLM_API_KEY = "do-not-print-this-key"
    tool = {
        "_backend": "local",
        "_model": "local-test-model",
        "tool_calls": [
            {
                "id": "read_1",
                "type": "function",
                "function": {"name": "read_demo_fact", "arguments": "{}"},
            }
        ],
    }
    final = {
        "_backend": "local",
        "_model": "local-test-model",
        "content": json.dumps(
            {
                "answer_key": "facts",
                "source_ids": ["fact_1"],
                "questions": [],
            }
        ),
    }
    with patch("assistant.management.commands.check_assistant.chat", side_effect=[tool, final]):
        call_command("check_assistant", live=True, stdout=output)
    assert '"actual_backend": "local"' in output.getvalue()
    assert "do-not-print-this-key" not in output.getvalue()

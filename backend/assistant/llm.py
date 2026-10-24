"""Bounded OpenAI-compatible transport with explicit free-model and local fallbacks."""

import json
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import APIException

MAX_RESPONSE_BYTES = 262144
OPENROUTER_PAUSE_KEY = "assistant:openrouter-paused"


class AssistantUnavailable(APIException):
    status_code = 503
    default_detail = "Савелий сейчас недоступен. Кредитный кабинет работает без помощника."
    default_code = "assistant_unavailable"


class _TransportFailure(Exception):
    def __init__(self, status=None):
        self.status = status
        super().__init__("LLM transport failure")


def _endpoint(base_url):
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not base_url.endswith("/v1"):
        raise _TransportFailure()
    return f"{base_url}/chat/completions"


def _request(base_url, api_key, models, messages, tools, timeout, *, openrouter=False):
    if not models or (openrouter and not api_key):
        raise _TransportFailure()
    body = {
        "model": models[0],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 512,
    }
    if openrouter:
        body.pop("model")
        body["models"] = models
        body["reasoning"] = {"enabled": False}
    if tools:
        body.update({"tools": tools, "tool_choice": "auto"})
    request = Request(
        _endpoint(base_url),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key or 'ollama'}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise _TransportFailure()
        result = json.loads(payload)
        message = result["choices"][0]["message"]
        if not isinstance(message, dict):
            raise _TransportFailure()
        if not message.get("tool_calls") and not (
            isinstance(message.get("content"), str) and message["content"].strip()
        ):
            raise _TransportFailure()
        if openrouter and _selected_model(result.get("model"), models) is None:
            raise _TransportFailure()
        return message, result.get("model")
    except HTTPError as exc:
        raise _TransportFailure(exc.code) from exc
    except (URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise _TransportFailure() from exc


def _remaining(deadline):
    return min(settings.LLM_TIMEOUT_SECONDS, max(0, deadline - monotonic()))


def _selected_model(reported_model, candidates):
    # OpenRouter may report the canonical slug without the :free variant.
    for candidate in candidates:
        if reported_model == candidate or reported_model == candidate.removesuffix(":free"):
            return candidate
    return None


def chat(messages, *, tools=None, deadline=None, backend=None, model=None):
    """Try the configured provider once, then local Ollama if available.

    The returned metadata pins the preferred route for a follow-up after tool calls.
    It is never persisted in conversation messages.
    """
    deadline = deadline if deadline is not None else monotonic() + 75
    openrouter = settings.LLM_PROVIDER == "openrouter"
    if settings.LLM_PROVIDER not in {"openrouter", "compatible"}:
        raise AssistantUnavailable("Неверная конфигурация LLM_PROVIDER.")

    candidates = (
        (settings.LLM_MODEL, *settings.LLM_FALLBACK_MODELS) if openrouter else (settings.LLM_MODEL,)
    )
    if model in candidates:
        candidates = (model, *(candidate for candidate in candidates if candidate != model))

    if backend != "local" and not (openrouter and cache.get(OPENROUTER_PAUSE_KEY)):
        timeout = _remaining(deadline)
        if timeout > 0:
            try:
                message, reported_model = _request(
                    settings.LLM_BASE_URL,
                    settings.LLM_API_KEY,
                    candidates,
                    messages,
                    tools,
                    timeout,
                    openrouter=openrouter,
                )
                return {
                    **message,
                    "_backend": "primary",
                    "_model": _selected_model(reported_model, candidates),
                }
            except _TransportFailure as exc:
                # Do not spend the free quota on a tight loop after a limit/configuration error.
                if openrouter and exc.status in {401, 402, 403, 429}:
                    cache.set(OPENROUTER_PAUSE_KEY, True, 300)

    if openrouter and settings.LLM_LOCAL_FALLBACK_BASE_URL:
        timeout = _remaining(deadline)
        if timeout > 0:
            try:
                message, _ = _request(
                    settings.LLM_LOCAL_FALLBACK_BASE_URL,
                    "",
                    (settings.LLM_LOCAL_FALLBACK_MODEL,),
                    messages,
                    tools,
                    timeout,
                )
                return {**message, "_backend": "local", "_model": settings.LLM_LOCAL_FALLBACK_MODEL}
            except _TransportFailure:
                pass
    raise AssistantUnavailable()

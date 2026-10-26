"""Bounded OpenAI-compatible transport with explicit free-model and local fallbacks."""

import json
import logging
import uuid
from http.client import HTTPException
from threading import BoundedSemaphore
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import APIException

from assistant.contracts import ANSWER_SCHEMA

MAX_RESPONSE_BYTES = 262144
OPENROUTER_PAUSE_KEY = "assistant:openrouter-paused"
logger = logging.getLogger(__name__)
PROVIDER_SLOT = BoundedSemaphore(1)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Never forward the provider key to a redirect target.
urlopen = build_opener(_NoRedirect()).open


class AssistantUnavailable(APIException):
    status_code = 503
    default_detail = "Помощник сейчас недоступен. Заявку можно продолжить без него."
    default_code = "assistant_unavailable"


class _TransportFailure(Exception):
    def __init__(self, status=None):
        self.status = status
        super().__init__("LLM transport failure")


def _endpoint(base_url):
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not base_url.endswith("/v1")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise _TransportFailure()
    return f"{base_url}/chat/completions"


def _request(base_url, api_key, models, messages, tools, timeout, *, openrouter=False):
    if not models or (openrouter and not api_key):
        raise _TransportFailure()
    if (
        openrouter
        and settings.LLM_OPENROUTER_FREE_ONLY
        and any(not candidate.endswith(":free") for candidate in models)
    ):
        raise _TransportFailure()
    body = {
        "model": models[0],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
    }
    if openrouter:
        body.pop("model")
        body["models"] = models
        body["reasoning"] = {"enabled": False}
        body["provider"] = {"require_parameters": True}
        if settings.LLM_OPENROUTER_FREE_ONLY:
            body["provider"]["max_price"] = {"prompt": 0, "completion": 0, "request": 0}
    if tools:
        body.update({"tools": tools, "tool_choice": "auto"})
    else:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "assistant_answer", "strict": True, "schema": ANSWER_SCHEMA},
        }
    request = Request(
        _endpoint(base_url),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key or 'ollama'}",
        },
        method="POST",
    )
    request_id, started, status = uuid.uuid4().hex, monotonic(), "error"
    try:
        with urlopen(request, timeout=timeout) as response:
            # read1 performs at most one raw read, so a slow byte stream cannot
            # keep a worker alive forever by resetting the socket idle timeout.
            chunks, size = [], 0
            read = getattr(response, "read1", response.read)
            while True:
                remaining = started + timeout - monotonic()
                if remaining <= 0:
                    raise _TransportFailure()
                raw = getattr(getattr(response, "fp", None), "raw", None)
                sock = getattr(raw, "_sock", None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk = read(min(8192, MAX_RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise _TransportFailure()
                chunks.append(chunk)
            payload = b"".join(chunks)
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
        status = "ok"
        return message, result.get("model")
    except HTTPError as exc:
        raise _TransportFailure(exc.code) from exc
    except (
        OSError,
        HTTPException,
        URLError,
        TimeoutError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        raise _TransportFailure() from exc
    finally:
        logger.info(
            "assistant_provider request_id=%s status=%s duration_ms=%d",
            request_id,
            status,
            int((monotonic() - started) * 1000),
        )


def _remaining(deadline):
    return min(settings.LLM_TIMEOUT_SECONDS, max(0, deadline - monotonic()))


def _selected_model(reported_model, candidates):
    # OpenRouter may report the canonical slug without the :free variant.
    for candidate in candidates:
        if reported_model == candidate or reported_model == candidate.removesuffix(":free"):
            return candidate
    return None


def chat(messages, *, tools=None, deadline=None, backend=None, model=None):
    # One network call per worker; spare Gunicorn threads serve the credit API.
    # Do not queue additional calls beyond their useful request lifetime.
    if not PROVIDER_SLOT.acquire(blocking=False):
        raise AssistantUnavailable("Помощник занят. Продолжите заявку или повторите вопрос позже.")
    try:
        return _chat(messages, tools=tools, deadline=deadline, backend=backend, model=model)
    finally:
        PROVIDER_SLOT.release()


def _chat(messages, *, tools=None, deadline=None, backend=None, model=None):
    """Try the configured provider once, then local Ollama if available.

    The returned metadata pins the preferred route for a follow-up after tool calls.
    It is never persisted in conversation messages.
    """
    deadline = (
        deadline if deadline is not None else monotonic() + settings.LLM_TOTAL_TIMEOUT_SECONDS
    )
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

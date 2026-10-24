"""Small OpenAI-compatible Chat Completions transport without provider lock-in."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework.exceptions import APIException


class AssistantUnavailable(APIException):
    status_code = 503
    default_detail = "Савелий сейчас недоступен. Кредитный кабинет работает без помощника."
    default_code = "assistant_unavailable"


def chat(messages, *, tools=None):
    base_url = settings.LLM_BASE_URL
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not base_url.endswith("/v1"):
        raise AssistantUnavailable("Неверная конфигурация LLM_BASE_URL.")
    body = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 320,
    }
    if tools:
        body.update({"tools": tools, "tool_choice": "auto"})
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.LLM_API_KEY or 'ollama'}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.LLM_TIMEOUT_SECONDS) as response:
            payload = response.read(262145)
        if len(payload) > 262144:
            raise ValueError("LLM response too large")
        result = json.loads(payload)
        message = result["choices"][0]["message"]
        if not isinstance(message, dict):
            raise ValueError("Invalid LLM message")
        return message
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise AssistantUnavailable() from exc

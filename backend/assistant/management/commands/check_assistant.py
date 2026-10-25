"""Probe the configured real model without reading company or conversation data."""

import json
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from assistant.contracts import ModelAnswer
from assistant.llm import AssistantUnavailable, chat

PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_demo_fact",
        "description": "Read one synthetic capability-check fact. No business data or mutations.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}


class Command(BaseCommand):
    help = "Show safe assistant configuration; --live probes native tools and JSON schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--live", action="store_true", help="Make two bounded real model calls."
        )

    def handle(self, *args, **options):
        self.stdout.write(
            json.dumps(
                {
                    "enabled": settings.AI_ENABLED,
                    "provider": settings.LLM_PROVIDER,
                    "primary_model": settings.LLM_MODEL,
                    "key_configured": bool(settings.LLM_API_KEY),
                    "free_only": settings.LLM_OPENROUTER_FREE_ONLY,
                    "local_fallback_model": settings.LLM_LOCAL_FALLBACK_MODEL
                    if settings.LLM_LOCAL_FALLBACK_BASE_URL
                    else None,
                },
                ensure_ascii=False,
            )
        )
        if not options["live"]:
            return
        if not settings.AI_ENABLED:
            raise CommandError("AI_ENABLED=false; model was not called.")
        started = monotonic()
        deadline = started + settings.LLM_TOTAL_TIMEOUT_SECONDS
        messages = [
            {
                "role": "system",
                "content": (
                    "You are checking tool calling, not answering a customer. "
                    "First call read_demo_fact with empty arguments. After receiving fact_1, "
                    "return only JSON: "
                    '{"answer_key":"facts","source_ids":["fact_1"],"questions":[]}.'
                ),
            },
            {"role": "user", "content": "Проверь соединение: вызови read_demo_fact."},
        ]
        try:
            first = chat(messages, tools=[PROBE_TOOL], deadline=deadline)
            calls = first.get("tool_calls") or []
            if len(calls) != 1:
                raise ValueError("Expected one native tool call")
            call = calls[0]
            if (
                call["function"]["name"] != "read_demo_fact"
                or json.loads(call["function"]["arguments"]) != {}
            ):
                raise ValueError("Unexpected tool or arguments")
            messages.extend(
                [
                    {"role": "assistant", "content": None, "tool_calls": calls},
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": '{"id":"fact_1","data":{"synthetic":true}}',
                    },
                ]
            )
            final = chat(
                messages,
                deadline=deadline,
                backend=first.get("_backend"),
                model=first.get("_model"),
            )
            answer = ModelAnswer(data=json.loads(final.get("content") or ""))
            answer.is_valid(raise_exception=True)
            if final.get("tool_calls") or answer.validated_data != {
                "answer_key": "facts",
                "source_ids": ["fact_1"],
                "questions": [],
            }:
                raise ValueError("Unexpected structured answer")
        except (AssistantUnavailable, ValidationError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(
                "Real model probe failed: check endpoint, key, model capabilities and limits. "
                "No company data was read. Provider payload and credentials are not displayed."
            ) from exc
        self.stdout.write(
            self.style.SUCCESS(
                json.dumps(
                    {
                        "native_tools": "passed",
                        "json_schema": "passed",
                        "actual_backend": final.get("_backend"),
                        "actual_model": final.get("_model") or settings.LLM_MODEL,
                        "duration_seconds": round(monotonic() - started, 2),
                        "real_model": True,
                    },
                    ensure_ascii=False,
                )
            )
        )

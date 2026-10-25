"""Explicit HTTP TEST DOUBLE for isolated QA. This is not a language model.

Run with --test-provider; never configure this endpoint for a product demonstration.
No prompts, credentials or response bodies are logged.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def answer(key="facts", sources=("fact_1",), questions=()):
    return {
        "content": json.dumps(
            {"answer_key": key, "source_ids": list(sources), "questions": list(questions)},
            ensure_ascii=False,
        )
    }


def respond(body):
    messages = body["messages"]
    tool_messages = [message for message in messages if message["role"] == "tool"]
    if tool_messages:
        facts = [json.loads(message["content"]) for message in tool_messages]
        return answer(sources=[fact["id"] for fact in facts])
    text = next(
        message["content"] for message in reversed(messages) if message["role"] == "user"
    ).lower()
    context = next(
        (
            json.loads(message["content"])
            for message in messages
            if message["role"] == "system"
            and message["content"].startswith('{"confirmed_product_code"')
        ),
        {},
    )
    evidence = context.get("request_evidence", {})
    selected = context.get("confirmed_product_code")
    if selected and evidence.get("amount") and evidence.get("term_months"):
        name, arguments = (
            "suggest_application_draft",
            {
                "product_code": selected,
                "amount": evidence["amount"],
                "term_months": evidence["term_months"],
                "purpose": evidence.get("purpose", "Пополнение оборотных средств"),
            },
        )
    elif any(word in text for word in ("статус", "решение", "предложение", "банку")):
        name, arguments = "get_application_status", {}
    elif any(word in text for word in ("продукт", "миллион", "оборотные")):
        name, arguments = "list_credit_products", {}
    else:
        return answer("form_fields", ())
    return {
        "content": None,
        "tool_calls": [
            {
                "id": "qa_read_1",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
            }
        ],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"QA TEST DOUBLE - NOT A MODEL")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 100000:
            self.send_error(400)
            return
        try:
            message = respond(json.loads(self.rfile.read(length)))
            payload = json.dumps(
                {"model": "qa-test-double", "choices": [{"message": message}]}, ensure_ascii=False
            ).encode()
        except ValueError, KeyError, StopIteration:
            self.send_error(400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-provider", action="store_true", required=True)
    parser.add_argument("--port", type=int, default=19001)
    options = parser.parse_args()
    print("QA TEST DOUBLE listening on loopback; this is not a model.", flush=True)
    ThreadingHTTPServer(("127.0.0.1", options.port), Handler).serve_forever()

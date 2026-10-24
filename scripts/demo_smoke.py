"""Check the running demo over HTTP; uses only Python's standard library."""

import argparse
import json
import os
import sys
import uuid
from decimal import Decimal
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


class HttpSession:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))
        self.csrf = None

    def request(self, method, path, payload=None, *, expected=200, csrf=True, headers=None):
        request_headers = dict(headers or {})
        if csrf and self.csrf and method != "GET":
            request_headers["X-CSRFToken"] = self.csrf
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=body, headers=request_headers, method=method)
        try:
            response = self.opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            check(
                response.status == expected,
                f"{method} {path}: expected {expected}, got {response.status}",
            )
            raw = response.read()
            if raw and "json" in response.headers.get("Content-Type", ""):
                return json.loads(raw)
            return raw

    def login(self, username, password):
        self.csrf = self.request("GET", "/api/v1/session/csrf/")["csrf_token"]
        result = self.request(
            "POST", "/api/v1/session/login/", {"username": username, "password": password}
        )
        check(result["user"]["username"] == username, "Session user mismatch")
        self.csrf = result["csrf_token"]
        check(
            any(
                cookie.name == "sessionid" and cookie.has_nonstandard_attr("HttpOnly")
                for cookie in self.cookies
            ),
            "Session cookie must be HttpOnly",
        )


class StaticAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in {"href", "src"} and value and value.startswith("/static/"):
                self.paths.add(value)


def run(base_url, password, verify_application=None):
    public = HttpSession(base_url)
    check(
        public.request("GET", "/api/v1/health/") == {"status": "ok", "database": "ok"},
        "Health check failed",
    )
    assets = StaticAssets()
    for path in ("/api/docs/", "/api/redoc/", "/api/session/login/"):
        page = public.request("GET", path).decode()
        assets.feed(page)
    check(bool(assets.paths), "Swagger/ReDoc static asset references missing")
    for path in sorted(assets.paths):
        check(bool(public.request("GET", path)), f"Empty static resource: {path}")
    schema = public.request("GET", "/api/schema/?format=json")
    check("/api/v1/agreements/{id}/disburse/" in schema["paths"], "OpenAPI workflow missing")

    client = HttpSession(base_url)
    client.login("client", password)
    if verify_application:
        saved = client.request("GET", f"/api/v1/applications/{verify_application}/")
        check(saved["status"] == "issued", "Issued application did not survive restart")
        check(
            saved["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]["disbursement"]
            is not None,
            "Disbursement did not survive restart",
        )
        return {
            "status": "ok",
            "persisted_application_id": str(verify_application),
            "static_assets": len(assets.paths),
        }

    staff = HttpSession(base_url)
    staff.login("specialist", password)
    outsider = HttpSession(base_url)
    outsider.login("outsider", password)
    companies = {
        item["inn"]: item for item in client.request("GET", "/api/v1/companies/")["results"]
    }
    product = next(
        item
        for item in client.request("GET", "/api/v1/products/")["results"]
        if item["code"] == "working-capital"
    )
    result = {"status": "ok", "static_assets": len(assets.paths), "scenarios": {}}
    financial = {
        "monthly_revenue": "1500000.00",
        "monthly_expenses": "900000.00",
        "monthly_debt_payments": "50000.00",
    }
    for index, scenario in enumerate(
        ("approval", "counteroffer", "needs_info", "rejected", "check_error"), 1
    ):
        values = financial.copy()
        if scenario == "counteroffer":
            values = {
                "monthly_revenue": "500000.00",
                "monthly_expenses": "400000.00",
                "monthly_debt_payments": "20000.00",
            }
        elif scenario == "needs_info":
            values = dict.fromkeys(financial)
        payload = {
            "company": companies[f"{index:010d}"]["id"],
            "product": product["id"],
            "amount": "1000000.00",
            "term_months": 24,
            "purpose": f"Автоматическая проверка демо: {scenario}",
            **values,
        }
        if scenario == "approval":
            client.request("POST", "/api/v1/applications/", payload, csrf=False, expected=403)
            client.request("POST", "/api/v1/applications/", [], expected=400)
            client.request(
                "POST", "/api/v1/applications/", {**payload, "status": "issued"}, expected=400
            )
        draft = client.request("POST", "/api/v1/applications/", payload, expected=201)
        app_path = f"/api/v1/applications/{draft['id']}/"
        reviewed = client.request(
            "POST", app_path + "submit/", {"lock_version": draft["lock_version"]}
        )
        if scenario == "needs_info":
            check(reviewed["status"] == "needs_info", "Missing finances must request information")
            revision = {
                key: value for key, value in payload.items() if key not in {"company", "product"}
            }
            reviewed = client.request(
                "POST",
                app_path + "provide-information/",
                {**revision, **financial, "lock_version": reviewed["lock_version"]},
            )
            check(
                reviewed["revisions"][0]["revision_no"] == 2, "Response must create a new revision"
            )
        elif scenario == "check_error":
            check(reviewed["status"] == "checking", "Technical error must remain checking")
            check(
                reviewed["revisions"][0]["assessment"] is None,
                "Technical error must not create an assessment",
            )
            reviewed = client.request(
                "POST", app_path + "retry-checks/", {"lock_version": reviewed["lock_version"]}
            )
            check(len(reviewed["revisions"][0]["checks"]) == 6, "Retry must preserve prior checks")
        check(reviewed["status"] == "review", f"{scenario}: review state missing")
        actions = {item["action"]: item for item in reviewed["available_actions"]}
        check(actions["decide"]["reason_code"] == "role_required", "Client must not decide")
        queue = staff.request(
            "GET", f"/api/v1/staff/applications/?assignment=free&search={draft['number']}"
        )
        check(queue["count"] == 1, "Unassigned application missing from free queue")
        row = queue["results"][0]
        check(
            "revisions" not in row and row["amount"] == payload["amount"],
            "Queue must use a compact current-revision projection",
        )
        reviewed = staff.request(
            "POST",
            f"/api/v1/staff/applications/{draft['id']}/claim/",
            {"lock_version": reviewed["lock_version"]},
        )
        if scenario == "approval":
            mine = staff.request(
                "GET", f"/api/v1/staff/applications/?assignment=mine&search={draft['number']}"
            )
            check(mine["count"] == 1, "Assigned application missing from my queue")
            reviewed = staff.request(
                "POST",
                f"/api/v1/staff/applications/{draft['id']}/release/",
                {"lock_version": reviewed["lock_version"]},
            )
            check(reviewed["assigned_to"] is None, "Release did not clear assignment")
            reviewed = staff.request(
                "POST",
                f"/api/v1/staff/applications/{draft['id']}/claim/",
                {"lock_version": reviewed["lock_version"]},
            )
        check(
            any(
                item["action"] == "decide" and item["allowed"]
                for item in reviewed["available_actions"]
            ),
            "Assigned specialist must be able to run the policy",
        )
        decided = staff.request(
            "POST",
            f"/api/v1/staff/applications/{draft['id']}/decide/",
            {"lock_version": reviewed["lock_version"]},
        )
        decision = decided["revisions"][0]["assessment"]["decision"]
        if scenario == "rejected":
            check(
                decided["status"] == "rejected" and decision["offer"] is None,
                "Negative checks must reject without an offer",
            )
            check(decided["assigned_to"] is None, "Rejection must release assignment")
        elif scenario == "counteroffer":
            check(decision["outcome"] == "counteroffer", "Counteroffer missing")
            check(
                Decimal(decision["offer"]["amount"]) < Decimal(payload["amount"]),
                "Counteroffer must reduce amount",
            )
            check(
                Decimal(decision["offer"]["monthly_payment"]) <= Decimal("30000.00"),
                "Counteroffer exceeds capacity",
            )
        elif scenario == "approval":
            offer = decision["offer"]
            accepted = client.request(
                "POST",
                f"/api/v1/offers/{offer['id']}/accept/",
                {"lock_version": decided["lock_version"]},
            )
            agreement = accepted["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
            agreement_path = f"/api/v1/agreements/{agreement['id']}/"
            client.request(
                "POST",
                agreement_path + "sign/",
                {
                    "lock_version": accepted["lock_version"],
                    "document_hash": agreement["document_hash"],
                    "confirm_simulation": True,
                },
            )
            version = client.request("GET", app_path)["lock_version"]
            headers = {"Idempotency-Key": str(uuid.uuid4())}
            issued = staff.request(
                "POST", agreement_path + "disburse/", {"lock_version": version}, headers=headers
            )
            repeated = staff.request(
                "POST", agreement_path + "disburse/", {"lock_version": version}, headers=headers
            )
            check(issued == repeated, "Idempotent repeat returned a different result")
            check(
                issued["amount"] == payload["amount"] and issued["is_simulated"] is True,
                "Incorrect simulated issuance",
            )
            check(
                client.request("GET", app_path)["status"] == "issued",
                "Issued status was not persisted",
            )
            outsider.request("GET", app_path, expected=404)
            outsider.request("GET", agreement_path, expected=404)
            result["approval_application_id"] = draft["id"]
        result["scenarios"][scenario] = {
            "application_id": draft["id"],
            "outcome": decision["outcome"],
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--verify-application", type=uuid.UUID)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        parser.error("--base-url must be an HTTP origin without credentials or a path")
    password = os.getenv("DEMO_PASSWORD", "")
    if not password:
        parser.error("Set DEMO_PASSWORD in the environment")
    try:
        result = run(args.base_url, password, args.verify_application)
    except Exception as error:
        print(f"DEMO CHECK FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

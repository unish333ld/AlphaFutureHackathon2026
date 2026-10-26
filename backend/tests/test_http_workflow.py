import json
import uuid
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest


@pytest.mark.django_db(transaction=True)
def test_credit_lifecycle_over_real_http_with_sessions_csrf_and_role_changes(demo, live_server):
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))

    def http(method, path, payload=None, *, csrf=None, expected=200, headers=None):
        request_headers = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        if csrf:
            request_headers["X-CSRFToken"] = csrf
        request = Request(live_server.url + path, data=body, method=method, headers=request_headers)
        try:
            response = opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            assert response.code == expected, (path, response.code, raw[:300])
            return (
                json.loads(raw)
                if raw and "json" in response.headers.get("Content-Type", "")
                else raw
            )

    def login(username):
        token = http("GET", "/api/v1/session/csrf/")["csrf_token"]
        result = http(
            "POST",
            "/api/v1/session/login/",
            {"username": username, "password": "TestsOnly2026!password"},
            csrf=token,
        )
        assert result["user"]["username"] == username
        return result["csrf_token"]

    assert http("GET", "/api/v1/health/")["database"] == "ok"
    assert b"swagger" in http("GET", "/api/docs/").lower()
    assert "/api/v1/applications/" in http("GET", "/api/schema/?format=json")["paths"]
    csrf = login("client")
    assert any(
        cookie.name == "sessionid" and cookie.has_nonstandard_attr("HttpOnly") for cookie in cookies
    )
    assert http("GET", "/api/v1/companies/")["count"] == 5
    assert http("GET", "/api/v1/products/")["count"] == 2
    source = demo["applications"]["approval"]
    data = {
        "company": str(source.company_id),
        "product": str(source.product_id),
        "amount": "1000000.00",
        "term_months": 24,
        "purpose": "Синтетический сквозной HTTP-тест",
        "monthly_revenue": "1500000.00",
        "monthly_expenses": "900000.00",
        "monthly_debt_payments": "50000.00",
    }
    http("POST", "/api/v1/applications/", data, expected=403)
    created = http("POST", "/api/v1/applications/", data, csrf=csrf, expected=201)
    app_path = f"/api/v1/applications/{created['id']}/"
    reviewed = http(
        "POST", app_path + "submit/", {"lock_version": created["lock_version"]}, csrf=csrf
    )
    assert reviewed["status"] == "review"
    csrf = login("specialist")
    reviewed = http(
        "POST",
        f"/api/v1/staff/applications/{created['id']}/claim/",
        {"lock_version": reviewed["lock_version"]},
        csrf=csrf,
    )
    decided = http(
        "POST",
        f"/api/v1/staff/applications/{created['id']}/decide/",
        {"lock_version": reviewed["lock_version"]},
        csrf=csrf,
    )
    offer = decided["revisions"][0]["assessment"]["decision"]["offer"]
    csrf = login("client")
    accepted = http(
        "POST",
        f"/api/v1/offers/{offer['id']}/accept/",
        {"lock_version": decided["lock_version"]},
        csrf=csrf,
    )
    agreement = accepted["revisions"][0]["assessment"]["decision"]["offer"]["agreement"]
    agreement_path = f"/api/v1/agreements/{agreement['id']}/"
    document = http(
        "POST",
        agreement_path + "generate-document/",
        {"lock_version": accepted["lock_version"], "document_hash": agreement["document_hash"]},
        csrf=csrf,
    )
    attempt = http(
        "POST",
        agreement_path + "signature-attempt/",
        {
            "lock_version": accepted["lock_version"],
            "document_hash": agreement["document_hash"],
            "document_id": document["id"],
            "pdf_sha256": document["pdf_sha256"],
            "acknowledged": True,
            "confirm_simulation": True,
        },
        csrf=csrf,
    )
    signed = http(
        "POST",
        agreement_path + "sign/",
        {
            "lock_version": accepted["lock_version"],
            "document_hash": agreement["document_hash"],
            "confirm_simulation": True,
            "document_id": document["id"],
            "pdf_sha256": document["pdf_sha256"],
            "attempt_id": attempt["id"],
            "code": attempt["demo_code"],
        },
        csrf=csrf,
    )
    assert signed["signed_at"] is not None
    version = http("GET", app_path)["lock_version"]
    csrf = login("specialist")
    key = {"Idempotency-Key": str(uuid.uuid4())}
    issued = http(
        "POST", agreement_path + "disburse/", {"lock_version": version}, csrf=csrf, headers=key
    )
    repeated = http(
        "POST", agreement_path + "disburse/", {"lock_version": version}, csrf=csrf, headers=key
    )
    assert repeated == issued
    assert issued["amount"] == "1000000.00" and issued["is_simulated"] is True
    assert http("GET", app_path)["status"] == "issued"
    csrf = login("outsider")
    http("GET", app_path, expected=404)
    http("GET", agreement_path, expected=404)
    assert http("GET", "/api/v1/disbursements/")["count"] == 0
    http("POST", "/api/v1/session/logout/", csrf=csrf, expected=204)
    http("GET", "/api/v1/me/", expected=403)

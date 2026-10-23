import runpy
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIClient

SETTINGS_FILE = Path(__file__).resolve().parents[1] / "config" / "settings.py"


@pytest.mark.parametrize("secret", ["", "short", "x" * 49])
def test_settings_refuse_missing_or_short_secret(monkeypatch, secret):
    monkeypatch.setenv("DJANGO_SECRET_KEY", secret)
    with pytest.raises(ImproperlyConfigured, match="at least 50"):
        runpy.run_path(str(SETTINGS_FILE))


def test_settings_enable_secure_cookies_and_explicit_hosts(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "synthetic-test-secret-" * 4)
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("DJANGO_COOKIE_SECURE", "true")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "demo.example.invalid")
    monkeypatch.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://demo.example.invalid")
    config = runpy.run_path(str(SETTINGS_FILE))
    assert config["DEBUG"] is False
    assert config["SESSION_COOKIE_SECURE"] is True
    assert config["CSRF_COOKIE_SECURE"] is True
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["ALLOWED_HOSTS"] == ["demo.example.invalid"]
    assert config["CSRF_TRUSTED_ORIGINS"] == ["https://demo.example.invalid"]


def test_login_and_writes_reject_foreign_origin_and_prelogin_csrf_token(demo):
    api = APIClient(enforce_csrf_checks=True)
    token = api.get("/api/v1/session/csrf/").data["csrf_token"]
    credentials = {"username": "client", "password": "TestsOnly2026!password"}
    assert (
        api.post(
            "/api/v1/session/login/",
            credentials,
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://untrusted.example.invalid",
        ).status_code
        == 403
    )
    logged_in = api.post(
        "/api/v1/session/login/",
        credentials,
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="http://testserver",
    )
    assert logged_in.status_code == 200
    rotated = logged_in.data["csrf_token"]
    payment = {"amount": "1200", "annual_rate": "0", "term_months": 12}
    assert (
        api.post("/api/v1/calculator/payment/", payment, HTTP_X_CSRFTOKEN=token).status_code == 403
    )
    assert (
        api.post(
            "/api/v1/calculator/payment/",
            payment,
            HTTP_X_CSRFTOKEN=rotated,
            HTTP_ORIGIN="https://untrusted.example.invalid",
        ).status_code
        == 403
    )
    assert (
        api.post(
            "/api/v1/calculator/payment/",
            payment,
            HTTP_X_CSRFTOKEN=rotated,
            HTTP_ORIGIN="http://testserver",
        ).status_code
        == 200
    )


def test_logout_invalidates_old_session_on_server(demo):
    api = APIClient(enforce_csrf_checks=True)
    token = api.get("/api/v1/session/csrf/").data["csrf_token"]
    response = api.post(
        "/api/v1/session/login/",
        {"username": "client", "password": "TestsOnly2026!password"},
        HTTP_X_CSRFTOKEN=token,
    )
    session = api.cookies["sessionid"].value
    assert api.post("/api/v1/session/logout/").status_code == 403
    assert (
        api.post(
            "/api/v1/session/logout/", HTTP_X_CSRFTOKEN=response.data["csrf_token"]
        ).status_code
        == 204
    )
    replay = APIClient()
    replay.cookies["sessionid"] = session
    assert replay.get("/api/v1/me/").status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("patch", "applications/{application}/"),
        ("post", "applications/{application}/retry-checks/"),
        ("post", "applications/{application}/provide-information/"),
        ("post", "applications/{application}/revise/"),
        ("post", "offers/{offer}/accept/"),
        ("post", "offers/{offer}/decline/"),
        ("post", "agreements/{agreement}/sign/"),
    ],
)
def test_foreign_mutations_return_404_before_processing_payload(
    demo, api, signed_deal, method, path
):
    app = signed_deal.offer.decision.assessment.revision.application
    version = app.lock_version
    api.force_authenticate(user=demo["outsider"])
    target = path.format(application=app.id, offer=signed_deal.offer_id, agreement=signed_deal.id)
    assert getattr(api, method)(f"/api/v1/{target}", {}, format="json").status_code == 404
    app.refresh_from_db()
    assert app.status == "signed" and app.lock_version == version

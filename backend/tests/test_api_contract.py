import json
import uuid
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from agreements.services import disburse
from api.serializers import (
    ApplicationCreateSerializer,
    DraftUpdateSerializer,
    InformationRequestInputSerializer,
    LoginRequestSerializer,
    PaymentRequestSerializer,
    RevisionSubmitSerializer,
    SignRequestSerializer,
    VersionSerializer,
)
from applications.models import Application
from applications.services import create_application
from companies.models import Company
from products.models import CreditProduct

# Every authenticated operation, including object actions, must reject anonymous callers.
PROTECTED_OPERATIONS = [
    ("get", "me/"),
    ("post", "session/logout/"),
    ("post", "calculator/payment/"),
    ("get", "companies/"),
    ("get", "companies/{id}/"),
    ("get", "products/"),
    ("get", "products/{id}/"),
    ("get", "applications/"),
    ("post", "applications/"),
    ("get", "applications/{id}/"),
    ("patch", "applications/{id}/"),
    ("post", "applications/{id}/submit/"),
    ("post", "applications/{id}/retry-checks/"),
    ("post", "applications/{id}/provide-information/"),
    ("post", "applications/{id}/revise/"),
    ("get", "applications/{id}/events/"),
    ("get", "staff/applications/"),
    ("get", "staff/applications/{id}/"),
    ("post", "staff/applications/{id}/request-information/"),
    ("post", "staff/applications/{id}/decide/"),
    ("get", "offers/"),
    ("get", "offers/{id}/"),
    ("post", "offers/{id}/accept/"),
    ("post", "offers/{id}/decline/"),
    ("get", "agreements/"),
    ("get", "agreements/{id}/"),
    ("post", "agreements/{id}/sign/"),
    ("post", "agreements/{id}/disburse/"),
    ("get", "disbursements/"),
    ("get", "disbursements/{id}/"),
]


@pytest.mark.parametrize("method,path", PROTECTED_OPERATIONS)
def test_every_business_operation_requires_authentication(api, method, path):
    path = path.format(id=uuid.UUID(int=1))
    response = getattr(api, method)(f"/api/v1/{path}")
    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path", [operation for operation in PROTECTED_OPERATIONS if operation[0] != "get"]
)
def test_every_authenticated_write_requires_csrf(demo, method, path):
    api = APIClient(enforce_csrf_checks=True)
    api.force_login(demo["client"])
    response = getattr(api, method)(
        f"/api/v1/{path.format(id=uuid.UUID(int=1))}", {}, format="json"
    )
    assert response.status_code == 403
    assert "CSRF" in str(response.data)


@pytest.mark.parametrize(
    "serializer_class",
    [
        ApplicationCreateSerializer,
        DraftUpdateSerializer,
        InformationRequestInputSerializer,
        LoginRequestSerializer,
        PaymentRequestSerializer,
        RevisionSubmitSerializer,
        SignRequestSerializer,
        VersionSerializer,
    ],
)
@pytest.mark.parametrize("payload", [[], "text", 42, None])
def test_all_request_serializers_report_non_object_errors_as_a_dictionary(
    serializer_class, payload
):
    serializer = serializer_class(data=payload)
    assert not serializer.is_valid()
    assert isinstance(serializer.errors, dict)
    assert "non_field_errors" in serializer.errors


def test_api_operation_matrix_matches_openapi(api):
    schema = api.get("/api/schema/?format=json").json()
    documented = {
        (method, path.removeprefix("/api/v1/"))
        for path, operations in schema["paths"].items()
        if path.startswith("/api/v1/")
        for method in operations
        if method in {"get", "post", "patch", "put", "delete"}
    }
    public = {("get", "health/"), ("get", "session/csrf/"), ("post", "session/login/")}
    assert documented == set(PROTECTED_OPERATIONS) | public


def test_all_read_endpoints_return_authorized_data_without_secrets(demo, api, signed_deal):
    app = signed_deal.offer.decision.assessment.revision.application
    app.refresh_from_db()
    issuance = disburse(demo["specialist"], signed_deal.id, app.lock_version, uuid.uuid4())
    api.force_authenticate(user=demo["client"])
    for path in (
        "me/",
        f"companies/{app.company_id}/",
        f"products/{app.product_id}/",
        f"applications/{app.id}/events/",
        "offers/",
        f"offers/{signed_deal.offer_id}/",
        "agreements/",
        f"agreements/{signed_deal.id}/",
        "disbursements/",
        f"disbursements/{issuance.id}/",
    ):
        response = api.get(f"/api/v1/{path}")
        assert response.status_code == 200, path
        payload = response.content.decode()
        for secret in ("TestsOnly2026!password", '"password"', '"is_superuser"', '"session_key"'):
            assert secret not in payload, path
    assert api.get(f"/api/v1/disbursements/{issuance.id}/").data["agreement"] == signed_deal.id
    api.force_authenticate(user=demo["specialist"])
    assert api.get(f"/api/v1/staff/applications/{app.id}/").data["status"] == "issued"


@pytest.mark.parametrize(
    "resource", ["companies", "products", "offers", "agreements", "disbursements"]
)
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_readonly_resources_do_not_expose_generic_writes(demo, api, resource, method):
    api.force_authenticate(user=demo["specialist"])
    suffix = "" if method == "post" else f"{uuid.UUID(int=1)}/"
    response = getattr(api, method)(f"/api/v1/{resource}/{suffix}", {}, format="json")
    assert response.status_code == 405


def test_revoked_membership_removes_company_and_all_financial_access(demo, api, signed_deal):
    app = signed_deal.offer.decision.assessment.revision.application
    demo["client"].memberships.filter(company=app.company).update(active=False)
    api.force_authenticate(user=demo["client"])
    for path in (
        f"companies/{app.company_id}/",
        f"applications/{app.id}/",
        f"applications/{app.id}/events/",
        f"offers/{signed_deal.offer_id}/",
        f"agreements/{signed_deal.id}/",
    ):
        assert api.get(f"/api/v1/{path}").status_code == 404
    assert str(app.company_id) not in json.dumps(api.get("/api/v1/companies/").json())
    assert api.post(f"/api/v1/agreements/{signed_deal.id}/sign/", {}).status_code == 404


def test_session_is_rejected_after_user_is_deactivated(demo):
    api = APIClient()
    api.force_login(demo["specialist"])
    user = demo["specialist"]
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert api.get("/api/v1/me/").status_code == 403
    assert api.get("/api/v1/staff/applications/").status_code == 403


def test_pagination_is_bounded_and_application_list_has_no_n_plus_one(demo, api):
    source = demo["applications"]["approval"]
    api.force_authenticate(user=demo["client"])
    with CaptureQueriesContext(connection) as initial:
        assert api.get("/api/v1/applications/").status_code == 200
    for index in range(26):
        create_application(
            demo["client"],
            {
                "company": source.company_id,
                "product": source.product_id,
                "amount": source.revisions.get().amount,
                "term_months": 24,
                "purpose": f"Синтетическая заявка {index}",
            },
        )
    with CaptureQueriesContext(connection) as expanded:
        response = api.get("/api/v1/applications/?page_size=10000")
    assert len(expanded) == len(initial) == 2
    assert response.data["count"] == 31
    assert len(response.data["results"]) == 25
    assert response.data["next"] is not None
    page_two = api.get("/api/v1/applications/?page=2")
    assert len(page_two.data["results"]) == 6
    assert not (
        {item["id"] for item in response.data["results"]}
        & {item["id"] for item in page_two.data["results"]}
    )
    assert api.get("/api/v1/applications/?page=999").status_code == 404


@pytest.mark.parametrize("payload", [[], "string", 42, None])
def test_non_object_json_is_validation_error(demo, api, payload):
    api.force_authenticate(user=demo["client"])
    response = api.post(
        "/api/v1/applications/", json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400
    assert Application.objects.count() == 5


def test_malformed_json_and_resource_ids_are_safe_errors(demo, api):
    api.force_authenticate(user=demo["client"])
    assert (
        api.post("/api/v1/applications/", '{"amount":', content_type="application/json").status_code
        == 400
    )
    assert api.get("/api/v1/applications/not-a-uuid/").status_code == 404
    assert api.get(f"/api/v1/applications/{uuid.uuid4()}/").status_code == 404
    product = CreditProduct.objects.get(code="equipment")
    product.active = False
    product.save()
    assert api.get(f"/api/v1/products/{product.id}/").status_code == 404
    foreign = Company.objects.get(inn="0000000006")
    assert api.get(f"/api/v1/companies/{foreign.id}/").status_code == 404


@pytest.mark.parametrize("browser", [False, True])
def test_login_throttle_limits_both_login_interfaces(demo, browser):
    cache.clear()
    api = APIClient(enforce_csrf_checks=True)
    csrf = api.get("/api/v1/session/csrf/").data["csrf_token"]
    path = "/api/session/login/" if browser else "/api/v1/session/login/"
    for _ in range(10):
        response = api.post(
            path,
            {"username": "client", "password": "incorrect"},
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == (200 if browser else 403)
    limited = api.post(path, {"username": "client", "password": "incorrect"}, HTTP_X_CSRFTOKEN=csrf)
    assert limited.status_code == 429


def test_browser_login_rotates_session_and_prevents_external_redirect(demo):
    api = APIClient(enforce_csrf_checks=True)
    csrf = api.get("/api/v1/session/csrf/").data["csrf_token"]
    response = api.post(
        "/api/session/login/?next=https://example.invalid/",
        {"username": "client", "password": "TestsOnly2026!password"},
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 302
    assert response["Location"] == "/api/docs/"
    assert api.get("/api/v1/me/").data["username"] == "client"


@pytest.mark.django_db
def test_health_checks_database_and_hides_database_errors(api):
    response = api.get("/api/v1/health/")
    assert response.data == {"status": "ok", "database": "ok"}
    with patch("api.views.connection.cursor", side_effect=DatabaseError("private db details")):
        failure = api.get("/api/v1/health/")
    assert failure.status_code == 503
    assert failure.data == {"status": "unavailable", "database": "unavailable"}
    assert b"private db details" not in failure.content

from pathlib import Path

import jsonschema
import yaml
from rest_framework.test import APIClient

from applications import services


def nullable_to_jsonschema(value):
    """OpenAPI 3.0 nullable is not a JSON Schema keyword."""
    if isinstance(value, list):
        return [nullable_to_jsonschema(item) for item in value]
    if not isinstance(value, dict):
        return value
    converted = {
        key: nullable_to_jsonschema(item) for key, item in value.items() if key != "nullable"
    }
    return {"anyOf": [converted, {"type": "null"}]} if value.get("nullable") else converted


def assert_response(schema, payload, path, method="get", status=200):
    contract = schema["paths"][path][method]["responses"][str(status)]["content"][
        "application/json"
    ]["schema"]
    document = nullable_to_jsonschema({"components": schema["components"], "allOf": [contract]})
    jsonschema.Draft4Validator(document, format_checker=jsonschema.FormatChecker()).validate(
        payload
    )


def test_actual_queue_detail_history_and_json_fields_follow_openapi(demo, api, signed_deal):
    schema = api.get("/api/schema/?format=json").json()
    app = signed_deal.offer.decision.assessment.revision.application
    for role in ("client", "specialist"):
        api.force_authenticate(user=demo[role])
        for path, documented in [
            (f"applications/{app.pk}/", "/api/v1/applications/{id}/"),
            (f"applications/{app.pk}/events/", "/api/v1/applications/{id}/events/"),
            (f"offers/{signed_deal.offer_id}/", "/api/v1/offers/{id}/"),
            (f"agreements/{signed_deal.pk}/", "/api/v1/agreements/{id}/"),
        ]:
            response = api.get("/api/v1/" + path)
            assert response.status_code == 200
            assert_response(schema, response.json(), documented)
    assert_response(
        schema, api.get("/api/v1/staff/applications/").json(), "/api/v1/staff/applications/"
    )
    calculator = api.post(
        "/api/v1/calculator/payment/",
        {"amount": "1000.00", "annual_rate": "0.0000", "term_months": 12},
        format="json",
    )
    assert_response(schema, calculator.json(), "/api/v1/calculator/payment/", "post")
    # Empty draft snapshot, missing assessment, and check.error have explicit shapes too.
    for scenario in ("counteroffer", "needs_info", "check_error"):
        source = demo["applications"][scenario]
        assert_response(
            schema,
            api.get(f"/api/v1/applications/{source.pk}/").json(),
            "/api/v1/applications/{id}/",
        )
        services.submit_application(demo["client"], source.pk, 0)
        assert_response(
            schema,
            api.get(f"/api/v1/applications/{source.pk}/").json(),
            "/api/v1/applications/{id}/",
        )


def test_general_field_conflict_and_csrf_errors_follow_schema(demo, api, reviewed_app):
    schema = api.get("/api/schema/?format=json").json()
    api.force_authenticate(user=demo["specialist"])
    path = f"/api/v1/staff/applications/{reviewed_app.pk}/claim/"
    for payload, status in [
        ({"lock_version": -1}, 400),
        ({"lock_version": 0}, 409),
        ({"lock_version": reviewed_app.lock_version, "role": "specialist"}, 400),
    ]:
        response = api.post(path, payload, format="json")
        assert response.status_code == status
        assert_response(
            schema, response.json(), "/api/v1/staff/applications/{id}/claim/", "post", status
        )
    csrf_client = APIClient(enforce_csrf_checks=True)
    response = csrf_client.post(
        "/api/v1/session/login/", {"username": "client", "password": "incorrect"}, format="json"
    )
    assert response.status_code == 403 and response["Content-Type"] == "application/json"
    assert response.json()["code"] == "csrf_failed"
    assert_response(schema, response.json(), "/api/v1/session/login/", "post", 403)


def test_published_openapi_matches_generated_contract(api):
    stored = yaml.safe_load((Path(__file__).resolve().parents[2] / "docs/openapi.yaml").read_text())
    generated = api.get("/api/schema/?format=json").json()
    assert stored == generated

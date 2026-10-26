"""Independent jury checks: real HTTP cookies/CSRF and PostgreSQL races."""

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from fractions import Fraction
from http.cookiejar import CookieJar
from threading import Barrier
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest
from django.db import connection
from django.utils import timezone

from accounts.models import User
from agreements.models import Agreement, AgreementDocument, Disbursement, SignatureConfirmation
from offers.models import Offer
from products.calculations import payment_schedule


class Session:
    """No force_authenticate; login really rotates the token and sets HttpOnly cookie."""

    def __init__(self, url, username):
        self.url = url
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))
        self.csrf = None
        status, before = self.request("GET", "session/csrf/")
        assert status == 200
        self.csrf = before["csrf_token"]
        status, logged_in = self.request(
            "POST", "session/login/", {"username": username, "password": "TestsOnly2026!password"}
        )
        assert status == 200
        self.csrf = logged_in["csrf_token"]
        assert self.csrf != before["csrf_token"]
        assert any(
            cookie.name == "sessionid" and cookie.has_nonstandard_attr("HttpOnly")
            for cookie in self.cookies
        )

    def request(self, method, path, payload=None, *, headers=None, csrf=True):
        headers = dict(headers or {})
        if csrf and self.csrf:
            headers["X-CSRFToken"] = self.csrf
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        request = Request(self.url + "/api/v1/" + path, body, headers, method=method)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            data = json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw
            return response.status, data


def race(*requests):
    assert connection.vendor == "postgresql", "Concurrency evidence requires PostgreSQL"
    barrier = Barrier(len(requests))

    def send(request):
        barrier.wait(timeout=5)
        return request()

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        return list(executor.map(send, requests))


def signing_session(live_server, demo, agreement):
    client = Session(live_server.url, "client")
    app = agreement.offer.decision.assessment.revision.application
    app.refresh_from_db()
    base = f"agreements/{agreement.id}/"
    payload = {"lock_version": app.lock_version, "document_hash": agreement.document_hash}
    status, document = client.request("POST", base + "generate-document/", payload)
    assert status == 200
    payload.update(document_id=document["id"], pdf_sha256=document["pdf_sha256"])
    status, attempt = client.request(
        "POST",
        base + "signature-attempt/",
        {**payload, "acknowledged": True, "confirm_simulation": True},
    )
    assert status == 200
    return (
        client,
        app,
        {
            **payload,
            "attempt_id": attempt["id"],
            "code": attempt["demo_code"],
            "confirm_simulation": True,
        },
    )


@pytest.mark.django_db(transaction=True)
def test_two_real_http_signatures_commit_one_audit_and_no_disbursement(
    demo, agreement, live_server
):
    first, app, payload = signing_session(live_server, demo, agreement)
    second = Session(live_server.url, "client")
    path = f"agreements/{agreement.pk}/sign/"
    results = race(
        lambda: first.request("POST", path, payload),
        lambda: second.request("POST", path, payload),
    )
    assert sorted(status for status, _ in results) == [200, 409]
    agreement.refresh_from_db()
    app.refresh_from_db()
    assert agreement.signed_at and app.status == "signed"
    assert SignatureConfirmation.objects.filter(agreement=agreement).count() == 1
    assert app.events.filter(event_type="signed").count() == 1
    assert not Disbursement.objects.filter(agreement=agreement).exists()
    assert first.request("POST", path, payload)[0] == 409


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_key", [True, False])
def test_real_http_issue_race_and_lost_response_recovery(demo, signed_deal, live_server, same_key):
    first = Session(live_server.url, "specialist")
    second = Session(live_server.url, "specialist")
    other_user = User.objects.create_user(
        username="jury-second", password="TestsOnly2026!password", system_role="specialist"
    )
    other = Session(live_server.url, other_user.username)
    client = Session(live_server.url, "client")
    app = signed_deal.offer.decision.assessment.revision.application
    app.refresh_from_db()
    path = f"agreements/{signed_deal.pk}/disburse/"
    payload = {"lock_version": app.lock_version}
    first_key = str(uuid.uuid4())
    second_key = first_key if same_key else str(uuid.uuid4())
    assert client.request("POST", path, payload, headers={"Idempotency-Key": first_key})[0] == 403
    assert other.request("POST", path, payload, headers={"Idempotency-Key": first_key})[0] == 409
    results = race(
        lambda: first.request("POST", path, payload, headers={"Idempotency-Key": first_key}),
        lambda: second.request("POST", path, payload, headers={"Idempotency-Key": second_key}),
    )
    assert sorted(status for status, _ in results) == ([200, 200] if same_key else [200, 409])
    assert Disbursement.objects.filter(agreement=signed_deal).count() == 1
    operation = Disbursement.objects.get(agreement=signed_deal)
    # Treat the successful POST response as lost: first read, then conscious replay of its key.
    status, state = first.request("GET", f"applications/{app.pk}/")
    assert status == 200 and state["status"] == "issued"
    status, replay = first.request(
        "POST", path, payload, headers={"Idempotency-Key": str(operation.idempotency_key)}
    )
    assert status == 200 and replay["id"] == str(operation.pk)
    assert (
        first.request("POST", path, payload, headers={"Idempotency-Key": str(uuid.uuid4())})[0]
        == 409
    )
    assert app.events.filter(event_type="issued").count() == 1


@pytest.mark.django_db(transaction=True)
def test_real_http_claim_race_and_no_alternate_assignment_bypass(demo, reviewed_app, live_server):
    User.objects.create_user(
        username="jury-second", password="TestsOnly2026!password", system_role="specialist"
    )
    sessions = [Session(live_server.url, name) for name in ("specialist", "jury-second")]
    version = {"lock_version": reviewed_app.lock_version}
    base = f"staff/applications/{reviewed_app.pk}/"
    results = race(
        *(
            lambda session=session: session.request("POST", base + "claim/", version)
            for session in sessions
        )
    )
    assert sorted(status for status, _ in results) == [200, 409]
    loser = sessions[next(index for index, (status, _) in enumerate(results) if status == 409)]
    reviewed_app.refresh_from_db()
    current = {"lock_version": reviewed_app.lock_version}
    for suffix, payload in [
        ("release/", current),
        ("decide/", current),
        ("request-information/", {**current, "question": "Недопустимый обход назначения"}),
    ]:
        assert loser.request("POST", base + suffix, payload)[0] == 409
    assert loser.request("POST", f"applications/{reviewed_app.pk}/retry-checks/", current)[0] == 409
    assert reviewed_app.events.filter(event_type="assignment_claimed").count() == 1


@pytest.mark.django_db(transaction=True)
def test_real_http_accept_races_expiry_read_without_creating_agreement(demo, offer, live_server):
    first = Session(live_server.url, "client")
    second = Session(live_server.url, "client")
    app = offer.decision.assessment.revision.application
    app.refresh_from_db()
    Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    results = race(
        lambda: first.request(
            "POST", f"offers/{offer.pk}/accept/", {"lock_version": app.lock_version}
        ),
        lambda: second.request("GET", f"applications/{app.pk}/"),
    )
    assert [status for status, _ in results] == [409, 200]
    app.refresh_from_db()
    assert app.status == "expired" and app.assigned_to_id is None
    assert not Agreement.objects.filter(offer=offer).exists()
    assert app.events.filter(event_type="expired").count() == 1


@pytest.mark.django_db(transaction=True)
def test_real_http_document_version_access_legacy_sign_and_csrf(demo, agreement, live_server):
    client, app, payload = signing_session(live_server, demo, agreement)
    outsider = Session(live_server.url, "outsider")
    accountant = Session(live_server.url, "accountant")
    staff = Session(live_server.url, "specialist")
    base = f"agreements/{agreement.pk}/"
    document = AgreementDocument.objects.get(pk=payload["document_id"])
    digest = hashlib.sha256(bytes(document.pdf_data)).hexdigest()
    for path in (
        f"applications/{app.pk}/",
        f"offers/{agreement.offer_id}/",
        base,
        base + "pdf/",
        base + "pdf/?kind=signed_copy",
    ):
        assert outsider.request("GET", path)[0] == 404
    assert outsider.request("POST", base + "sign/", payload)[0] == 404
    assert (
        outsider.request("POST", base + "cancel-signature/", {"attempt_id": payload["attempt_id"]})[
            0
        ]
        == 404
    )
    assert accountant.request("POST", base + "sign/", payload)[0] == 403
    assert client.request("POST", base + "sign/", payload, csrf=False)[0] == 403
    assert (
        client.request(
            "POST",
            base + "sign/",
            {
                "lock_version": app.lock_version,
                "document_hash": agreement.document_hash,
                "confirm_simulation": True,
            },
        )[0]
        == 400
    )
    assert (
        staff.request(
            "POST", f"staff/applications/{app.pk}/release/", {"lock_version": app.lock_version}
        )[0]
        == 200
    )
    assert client.request("POST", base + "sign/", payload)[0] == 409
    agreement.refresh_from_db()
    document.refresh_from_db()
    assert agreement.signed_at is None
    assert not SignatureConfirmation.objects.filter(agreement=agreement).exists()
    assert hashlib.sha256(bytes(document.pdf_data)).hexdigest() == digest
    assert client.request("POST", "session/logout/")[0] == 204
    assert client.request("GET", "me/")[0] == 403


def rational_schedule(amount, annual_rate, months):
    """Exact rational closed form and integer kopecks, independent of Decimal implementation."""
    principal = int(Fraction(amount) * 100)
    rate = Fraction(annual_rate) / 1200

    def rounded(value):
        return (2 * value.numerator + value.denominator) // (2 * value.denominator)

    fixed = rounded(
        Fraction(principal, months) if not rate else principal * rate / (1 - (1 + rate) ** -months)
    )
    balance = principal
    rows = []
    for month in range(1, months + 1):
        interest = rounded(balance * rate)
        payment = balance + interest if month == months else min(fixed, balance + interest)
        repaid = payment - interest
        balance -= repaid
        rows.append((payment, repaid, interest, balance))
    return fixed, rows


@pytest.mark.parametrize(
    "amount,rate,months",
    [
        ("1100000.00", "27", 24),
        ("300000.37", "27", 12),
        ("30000000.00", "27", 60),
        ("300000.01", "0", 60),
    ],
)
def test_exact_rational_oracle_checks_all_payments(amount, rate, months):
    fixed, rows = rational_schedule(amount, rate, months)
    payment, actual = payment_schedule(amount, rate, months)
    assert int(payment * 100) == fixed
    assert [
        tuple(
            int(Fraction(row[key]) * 100) for key in ("payment", "principal", "interest", "balance")
        )
        for row in actual["rows"]
    ] == rows
    assert sum(row[1] for row in rows) == int(Fraction(amount) * 100)
    assert rows[-1][3] == 0
    if amount == "1100000.00":
        assert fixed == 5981825 and rows[-1][0] == 5981830
        assert sum(row[2] for row in rows) == 33563805
        assert sum(row[0] for row in rows) == 143563805

import pytest
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.models import User
from agreements import services as deals
from agreements.models import Agreement
from applications import services
from applications.models import Application
from offers.models import Offer
from tests.signing import sign_with_code


@pytest.fixture(autouse=True)
def test_runtime(settings):
    settings.DEBUG = False
    # API tests must work in a fresh checkout without generated static manifests.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    cache.clear()


@pytest.fixture
def demo(db, settings, monkeypatch):
    settings.DEMO_MODE = True
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    monkeypatch.setenv("DEMO_PASSWORD", "TestsOnly2026!password")
    cache.clear()
    call_command("seed_demo", verbosity=0)
    return {
        "client": User.objects.get(username="client"),
        "specialist": User.objects.get(username="specialist"),
        "outsider": User.objects.get(username="outsider"),
        "accountant": User.objects.get(username="accountant"),
        "applications": {
            app.purpose.rsplit(": ", 1)[-1]: app.application
            for app in (a.revisions.first() for a in Application.objects.all())
        },
    }


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def reviewed_app(demo):
    app = demo["applications"]["approval"]
    services.submit_application(demo["client"], app.id, app.lock_version)
    app.refresh_from_db()
    return app


@pytest.fixture
def offer(demo, reviewed_app):
    services.claim_application(demo["specialist"], reviewed_app.id, reviewed_app.lock_version)
    reviewed_app.refresh_from_db()
    services.make_decision(demo["specialist"], reviewed_app.id, reviewed_app.lock_version)
    return Offer.objects.get(decision__assessment__revision__application=reviewed_app)


@pytest.fixture
def agreement(demo, offer):
    app = offer.decision.assessment.revision.application
    deals.respond_to_offer(demo["client"], offer.id, app.lock_version, accept=True)
    return Agreement.objects.get(offer=offer)


@pytest.fixture
def signed_deal_factory(demo):
    def create(scenario="approval"):
        app = demo["applications"][scenario]
        services.submit_application(demo["client"], app.id, app.lock_version)
        app.refresh_from_db()
        services.claim_application(demo["specialist"], app.id, app.lock_version)
        app.refresh_from_db()
        services.make_decision(demo["specialist"], app.id, app.lock_version)
        offer = Offer.objects.get(decision__assessment__revision__application=app)
        app.refresh_from_db()
        deals.respond_to_offer(demo["client"], offer.id, app.lock_version, accept=True)
        agreement = Agreement.objects.get(offer=offer)
        app.refresh_from_db()
        return sign_with_code(
            demo["client"], agreement.id, app.lock_version, agreement.document_hash
        )

    return create


@pytest.fixture
def signed_deal(signed_deal_factory):
    return signed_deal_factory()

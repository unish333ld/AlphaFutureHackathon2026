import pytest
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.models import User
from applications.models import Application


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

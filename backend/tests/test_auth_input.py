import pytest
from rest_framework.test import APIClient

from accounts.models import User
from api.serializers import LoginRequestSerializer


def test_password_serializer_preserves_whitespace():
    password = "  synthetic QA password 42!  "
    serializer = LoginRequestSerializer(data={"username": "qa-user", "password": password})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["password"] == password


@pytest.mark.django_db
def test_login_matches_the_exact_password_including_spaces(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    password = "  synthetic QA password 42!  "
    User.objects.create_user(username="qa-exact-password", password=password)
    api = APIClient(enforce_csrf_checks=True)
    csrf = api.get("/api/v1/session/csrf/").data["csrf_token"]
    response = api.post(
        "/api/v1/session/login/",
        {"username": "qa-exact-password", "password": password},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200
    assert api.get("/api/v1/me/").data["username"] == "qa-exact-password"


@pytest.mark.django_db
def test_login_does_not_accept_a_password_with_extra_spaces(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    User.objects.create_user(username="qa-no-trim", password="Synthetic QA password 42!")
    api = APIClient(enforce_csrf_checks=True)
    csrf = api.get("/api/v1/session/csrf/").data["csrf_token"]
    response = api.post(
        "/api/v1/session/login/",
        {"username": "qa-no-trim", "password": " Synthetic QA password 42! "},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 403
    assert api.get("/api/v1/me/").status_code == 403

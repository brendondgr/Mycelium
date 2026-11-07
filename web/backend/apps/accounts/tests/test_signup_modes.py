"""The five sign-up modes and optional verification (``[signup]`` in mycelium.toml).

The suite default is the institution profile (code + verified email); each test
here switches the mode it is about.
"""

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client

from apps.accounts.permissions import user_email_verified


@pytest.fixture
def api_client() -> Client:
    return Client(enforce_csrf_checks=True)


def _register(client: Client, **overrides):
    client.get("/api/auth/csrf/")
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    payload = {
        "username": "newuser",
        "email": "new@example.com",
        "password": "safe-pass-123",
        "password_confirm": "safe-pass-123",
        "first_name": "Jamie",
        "last_name": "Rivera",
    }
    payload.update(overrides)
    return client.post(
        "/api/auth/register/",
        data=payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


@pytest.mark.django_db
def test_policy_endpoint_reports_the_mode(api_client, settings):
    settings.SIGNUP_MODE = "domain"
    settings.SIGNUP_ALLOWED_DOMAINS = ["fsu.edu"]
    body = api_client.get("/api/auth/signup-policy/").json()
    assert body == {"mode": "domain", "verify_email": True, "domains": ["fsu.edu"]}

    settings.SIGNUP_MODE = "open"
    settings.SIGNUP_VERIFY_EMAIL = False
    body = api_client.get("/api/auth/signup-policy/").json()
    assert body == {"mode": "open", "verify_email": False, "domains": []}


@pytest.mark.django_db
def test_closed_refuses_everyone(api_client, settings):
    settings.SIGNUP_MODE = "closed"
    response = _register(api_client, access_code=settings.SIGNUP_ACCESS_CODE)
    assert response.status_code == 403
    assert response.json()["reason"] == "signup_closed"
    assert not User.objects.filter(username="newuser").exists()


@pytest.mark.django_db
def test_invite_mode_refuses_a_code(api_client, settings):
    settings.SIGNUP_MODE = "invite"
    response = _register(api_client, access_code=settings.SIGNUP_ACCESS_CODE)
    assert response.status_code == 403
    assert response.json()["reason"] == "invite_required"


@pytest.mark.django_db
def test_code_mode_still_needs_the_code(api_client, settings):
    response = _register(api_client, access_code="wrong")
    assert response.status_code == 400
    assert "access_code" in response.json()
    response = _register(api_client, access_code=settings.SIGNUP_ACCESS_CODE)
    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_code_mode_with_no_code_configured_admits_nobody(api_client, settings):
    settings.SIGNUP_ACCESS_CODE = ""
    response = _register(api_client, access_code="")
    assert response.status_code == 400


@pytest.mark.django_db
def test_open_mode_needs_nothing_and_is_active_at_once(api_client, settings):
    settings.SIGNUP_MODE = "open"
    settings.SIGNUP_VERIFY_EMAIL = False
    response = _register(api_client)
    assert response.status_code == 201, response.content
    assert response.json()["is_verified"] is True  # active: nothing to prove
    user = User.objects.get(username="newuser")
    assert user_email_verified(user)
    # ...but the address itself was never proved, so it is not marked as such.
    assert user.profile.is_verified is False


@pytest.mark.django_db
def test_open_mode_with_verification_waits_for_the_code(api_client, settings):
    settings.SIGNUP_MODE = "open"
    settings.SIGNUP_VERIFY_EMAIL = True
    response = _register(api_client)
    assert response.status_code == 201
    assert response.json()["is_verified"] is False


@pytest.mark.django_db
def test_domain_mode_admits_only_allowed_addresses(api_client, settings):
    settings.SIGNUP_MODE = "domain"
    settings.SIGNUP_ALLOWED_DOMAINS = ["fsu.edu"]
    response = _register(api_client, email="someone@gmail.com")
    assert response.status_code == 400
    assert response.json()["reason"] == "domain_required"

    response = _register(api_client, email="ada@cs.fsu.edu")
    assert response.status_code == 201, response.content
    # A domain is proved by mail, so the account waits for its code.
    assert response.json()["is_verified"] is False


@pytest.mark.django_db
def test_without_verification_an_account_can_create_a_lab(api_client, settings):
    settings.SIGNUP_MODE = "open"
    settings.SIGNUP_VERIFY_EMAIL = False
    assert _register(api_client).status_code == 201
    csrf = api_client.cookies[settings.CSRF_COOKIE_NAME].value
    response = api_client.post(
        "/api/auth/labs/",
        data={"name": "Forest Lab"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code in (200, 201), response.content

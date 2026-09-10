"""Password reset by emailed link, and the signed-in password change."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, override_settings

from apps.accounts import password_reset
from apps.accounts.views import RESET_REQUESTED_MESSAGE

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD = "pw-Str0ng-1234"
NEW_PASSWORD = "n3w-Str0ng-9876"


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        username="ada", email="ada@example.com", password=PASSWORD
    )


def _post(client: Client, path: str, payload: dict | None = None):
    client.get("/api/auth/csrf/")
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    return client.post(
        path,
        data=payload or {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _request(email: str):
    """Ask for a reset link from a fresh anonymous client."""
    return _post(
        Client(enforce_csrf_checks=True), "/api/auth/password/reset/", {"email": email}
    )


def _link_parts() -> tuple[str, str]:
    """The uid/token pair out of the most recent reset email."""
    body = mail.outbox[-1].body
    match = re.search(r"[?&]uid=([^&\s]+)&token=([^&\s]+)", body)
    assert match, f"no reset link in body: {body!r}"
    return match.group(1), match.group(2)


# -- requesting -----------------------------------------------------------------


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_request_mails_a_link_to_a_known_address(user: User) -> None:
    mail.outbox.clear()
    response = _request("ada@example.com")

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ada@example.com"]


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_request_matches_the_address_case_insensitively(user: User) -> None:
    mail.outbox.clear()
    _request("ADA@Example.COM")
    assert len(mail.outbox) == 1


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_an_unknown_address_is_answered_identically(user: User) -> None:
    """The endpoint must not be usable to test whether someone has an account."""
    client = Client(enforce_csrf_checks=True)

    mail.outbox.clear()
    known = _post(client, "/api/auth/password/reset/", {"email": "ada@example.com"})
    mailed = len(mail.outbox)

    mail.outbox.clear()
    unknown = _post(
        client, "/api/auth/password/reset/", {"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"detail": RESET_REQUESTED_MESSAGE}
    assert mailed == 1 and len(mail.outbox) == 0


# -- spending the link ----------------------------------------------------------


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_the_link_sets_a_new_password(user: User) -> None:
    mail.outbox.clear()
    _request(user.email)
    uid, token = _link_parts()

    response = _post(
        Client(enforce_csrf_checks=True),
        "/api/auth/password/reset/confirm/",
        {
            "uid": uid,
            "token": token,
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_spent_link_cannot_be_used_twice(user: User) -> None:
    mail.outbox.clear()
    _request(user.email)
    uid, token = _link_parts()
    payload = {
        "uid": uid,
        "token": token,
        "password": NEW_PASSWORD,
        "password_confirm": NEW_PASSWORD,
    }
    client = Client(enforce_csrf_checks=True)

    first = _post(client, "/api/auth/password/reset/confirm/", payload)
    assert first.status_code == 200
    second = _post(client, "/api/auth/password/reset/confirm/", payload)

    assert second.status_code == 400
    assert "token" in second.json()


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_the_link_is_refused_once_the_window_closes(user: User) -> None:
    mail.outbox.clear()
    _request(user.email)
    uid, token = _link_parts()

    # Age the token rather than shrink the window: the generator stamps the
    # issue time into the token itself, so moving its clock forward is the only
    # way to test the boundary it actually enforces.
    aged = datetime.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 60)
    with patch.object(default_token_generator, "_now", return_value=aged):
        response = _post(
            Client(enforce_csrf_checks=True),
            "/api/auth/password/reset/verify/",
            {"uid": uid, "token": token},
        )
    assert response.json()["valid"] is False


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_verify_reports_a_live_link(user: User) -> None:
    mail.outbox.clear()
    _request(user.email)
    uid, token = _link_parts()

    response = _post(
        Client(enforce_csrf_checks=True),
        "/api/auth/password/reset/verify/",
        {"uid": uid, "token": token},
    )
    assert response.json() == {"valid": True}


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_forged_link_is_refused(user: User) -> None:
    response = _post(
        Client(enforce_csrf_checks=True),
        "/api/auth/password/reset/confirm/",
        {
            "uid": "not-a-uid",
            "token": "not-a-token",
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
    )
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_weak_password_is_refused_and_the_link_survives(user: User) -> None:
    mail.outbox.clear()
    _request(user.email)
    uid, token = _link_parts()
    client = Client(enforce_csrf_checks=True)

    weak = _post(
        client,
        "/api/auth/password/reset/confirm/",
        {
            "uid": uid,
            "token": token,
            "password": "12345678",
            "password_confirm": "12345678",
        },
    )
    assert weak.status_code == 400
    assert "password" in weak.json()

    # The password never changed, so the token still verifies.
    good = _post(
        client,
        "/api/auth/password/reset/confirm/",
        {
            "uid": uid,
            "token": token,
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
    )
    assert good.status_code == 200


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_mismatched_confirmation_is_refused(user: User) -> None:
    mail.outbox.clear()
    _request(user.email)
    uid, token = _link_parts()

    response = _post(
        Client(enforce_csrf_checks=True),
        "/api/auth/password/reset/confirm/",
        {
            "uid": uid,
            "token": token,
            "password": NEW_PASSWORD,
            "password_confirm": "something-else-9876",
        },
    )
    assert response.status_code == 400
    assert "password_confirm" in response.json()


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_reset_also_activates_the_account(user: User) -> None:
    """Holding the link proves the mailbox, so it counts as verification."""
    assert user.profile.is_verified is False
    mail.outbox.clear()
    _request(user.email)
    uid, token = _link_parts()

    _post(
        Client(enforce_csrf_checks=True),
        "/api/auth/password/reset/confirm/",
        {
            "uid": uid,
            "token": token,
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
    )

    user.refresh_from_db()
    assert user.profile.is_verified is True


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_the_emailed_link_is_absolute_and_not_loopback(user: User) -> None:
    url = password_reset.reset_url(user)
    assert url.startswith("http")
    assert "localhost" not in url and "127.0.0.1" not in url


# -- changing a password you still know ------------------------------------------


def test_password_change_needs_the_current_password(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = _post(
        client,
        "/api/auth/password/change/",
        {
            "current_password": "wrong",
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
    )

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_password_change_keeps_the_actor_signed_in(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = _post(
        client,
        "/api/auth/password/change/",
        {
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    # The session was re-stamped, so this browser is still signed in.
    assert client.get("/api/auth/me/").status_code == 200


def test_password_change_requires_authentication(user: User) -> None:
    response = _post(
        Client(enforce_csrf_checks=True),
        "/api/auth/password/change/",
        {
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
    )
    assert response.status_code in (401, 403)

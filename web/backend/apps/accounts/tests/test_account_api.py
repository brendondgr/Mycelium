"""The Account page's API: identity fields, and the sign-up address check."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test import Client

PASSWORD = "pw-Str0ng-1234"


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        username="ada",
        email="ada@example.com",
        password=PASSWORD,
        first_name="Ada",
        last_name="Lovelace",
    )


@pytest.fixture
def client_for(user: User) -> Client:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return client


def _send(client: Client, method: str, path: str, payload: dict | None = None):
    client.get("/api/auth/csrf/")
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    return getattr(client, method)(
        path,
        data=payload or {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


# -- reading and editing --------------------------------------------------------


def test_account_returns_identity_from_both_tables(
    user: User, client_for: Client
) -> None:
    body = client_for.get("/api/auth/account/").json()

    assert body["username"] == "ada"
    assert body["email"] == "ada@example.com"
    assert body["first_name"] == "Ada"
    assert body["institution"] == ""
    assert body["is_verified"] is False
    assert body["pending_email"] == ""


def test_account_patch_writes_name_and_affiliation(
    user: User, client_for: Client
) -> None:
    response = _send(
        client_for,
        "patch",
        "/api/auth/account/",
        {"first_name": "Augusta", "institution": "Analytical Engine Lab"},
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Augusta"
    assert user.last_name == "Lovelace"  # untouched by a partial write
    assert user.profile.institution == "Analytical Engine Lab"


def test_account_patch_leaves_research_interests_alone(
    user: User, client_for: Client
) -> None:
    """A name edit must not write back the interests it happened to load."""
    profile = user.profile
    profile.interests = {"areas": ["symbolic computation"]}
    profile.save(update_fields=["interests"])

    _send(client_for, "patch", "/api/auth/account/", {"first_name": "Augusta"})

    profile.refresh_from_db()
    assert profile.interests == {"areas": ["symbolic computation"]}


def test_account_will_not_rename_the_username_or_email(
    user: User, client_for: Client
) -> None:
    """Both are read-only here: each has its own endpoint, or none at all."""
    _send(
        client_for,
        "patch",
        "/api/auth/account/",
        {"username": "hacker", "email": "hacker@example.com"},
    )

    user.refresh_from_db()
    assert user.username == "ada"
    assert user.email == "ada@example.com"


def test_account_requires_authentication() -> None:
    assert Client().get("/api/auth/account/").status_code in (401, 403)


# -- the sign-up duplicate check ------------------------------------------------


def test_email_check_reports_a_taken_address(user: User) -> None:
    response = _send(
        Client(enforce_csrf_checks=True),
        "post",
        "/api/auth/email/check/",
        {"email": "ADA@example.com", "access_code": settings.SIGNUP_ACCESS_CODE},
    )

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_email_check_reports_a_free_address(db) -> None:
    response = _send(
        Client(enforce_csrf_checks=True),
        "post",
        "/api/auth/email/check/",
        {"email": "nobody@example.com", "access_code": settings.SIGNUP_ACCESS_CODE},
    )

    assert response.json()["available"] is True


def test_email_check_refuses_without_the_invite_code(user: User) -> None:
    """It is an enumeration oracle, so it lives behind the sign-up gate."""
    response = _send(
        Client(enforce_csrf_checks=True),
        "post",
        "/api/auth/email/check/",
        {"email": "ada@example.com", "access_code": "000000"},
    )

    assert response.status_code == 400
    assert "available" not in response.json()


def test_email_check_rejects_a_malformed_address(db) -> None:
    response = _send(
        Client(enforce_csrf_checks=True),
        "post",
        "/api/auth/email/check/",
        {"email": "not-an-address", "access_code": settings.SIGNUP_ACCESS_CODE},
    )
    assert response.status_code == 400


# -- the constraint behind the check --------------------------------------------


@pytest.mark.skipif(
    connection.vendor not in ("postgresql", "sqlite"),
    reason="the unique index is created with raw SQL for these two backends",
)
def test_the_database_refuses_a_duplicate_address(user: User) -> None:
    """The serializer check is a courtesy; this is the guarantee.

    Two sign-ups racing each other both pass a Python-side existence query. Reset
    now looks an account up *by* its address, so a duplicate decides whose
    account a reset link opens.
    """
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(
            username="ada2", email="ADA@EXAMPLE.COM", password=PASSWORD
        )


def test_blank_addresses_are_still_allowed(db) -> None:
    """The index is partial: service accounts and fixtures have no address."""
    User.objects.create_user(username="svc1", email="", password=PASSWORD)
    User.objects.create_user(username="svc2", email="", password=PASSWORD)
    assert User.objects.filter(email="").count() == 2

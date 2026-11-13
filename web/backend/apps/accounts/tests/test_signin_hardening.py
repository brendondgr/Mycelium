"""Go-public Phase 2: sign-in and account hardening.

Each test is named after the abuse it prevents (plan
``20261112-go-public-readiness``, Phase 2).
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, override_settings

from apps.accounts import email_verification, signup_gate
from apps.accounts.client_ip import client_ip
from apps.accounts.models import (
    AuditEvent,
    AuthorWork,
    EmailVerification,
    Lab,
    LabMembership,
    Profile,
)
from apps.billing.services import create_lab_workspace

from .conftest import verified

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD = "pw-Str0ng-1234"


@pytest.fixture(autouse=True)
def _mail_sends_immediately(monkeypatch):
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, *args, **kwargs: func()
    )


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        username="ada", email="ada@example.com", password=PASSWORD
    )


def _csrf(client: Client) -> str:
    client.get("/api/auth/csrf/")
    return client.cookies[settings.CSRF_COOKIE_NAME].value


def _send(client: Client, method: str, path: str, payload: dict | None = None, **extra):
    token = _csrf(client)
    return getattr(client, method)(
        path,
        data=payload or {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
        **extra,
    )


def _login(client: Client, password: str, username: str = "ada", **extra):
    return _send(
        client,
        "post",
        "/api/auth/login/",
        {"username": username, "password": password},
        **extra,
    )


def _code_from_outbox() -> str:
    body = mail.outbox[-1].body
    digits = [word for word in body.split() if word.isdigit() and len(word) == 6]
    assert digits, body
    return digits[0]


# -- brute force -------------------------------------------------------------------


@pytest.mark.django_db
@override_settings(LOGIN_MAX_FAILURES=5)
def test_login_throttled(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    for _ in range(5):
        assert _login(client, "wrong").status_code == 401
    # Locked: even the right password is refused, and the answer says so.
    locked = _login(client, PASSWORD)
    assert locked.status_code == 429
    # Another address is not locked out of the same account.
    other = Client(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.9")
    assert _login(other, PASSWORD).status_code == 200


@pytest.mark.django_db
@override_settings(LOGIN_MAX_FAILURES=100, LOGIN_MAX_FAILURES_PER_IP=6)
def test_login_spraying_from_one_address_is_throttled(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    for n in range(6):
        _login(client, "Password1", username=f"someone{n}")
    assert _login(client, PASSWORD).status_code == 429


@pytest.mark.django_db
@override_settings(LOGIN_MAX_FAILURES=3)
def test_admin_login_shares_the_lockout(user: User) -> None:
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = Client()
    for _ in range(3):
        client.post("/admin/login/", {"username": "ada", "password": "wrong"})
    response = client.post(
        "/admin/login/", {"username": "ada", "password": PASSWORD, "next": "/admin/"}
    )
    assert response.status_code == 200  # the form again, not a redirect in
    assert "_auth_user_id" not in client.session
    # And the API door is locked for the same pair.
    assert _login(Client(enforce_csrf_checks=True), PASSWORD).status_code == 429


@pytest.mark.django_db
def test_basic_auth_rejected(user: User) -> None:
    token = base64.b64encode(f"ada:{PASSWORD}".encode()).decode()
    response = Client().get("/api/auth/account/", HTTP_AUTHORIZATION=f"Basic {token}")
    assert response.status_code in (401, 403)


# -- CSRF on the doors that create a session ---------------------------------------


@pytest.mark.django_db
def test_login_requires_csrf(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        "/api/auth/login/",
        data={"username": "ada", "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_register_requires_csrf() -> None:
    response = Client(enforce_csrf_checks=True).post(
        "/api/auth/register/",
        data={
            "username": "eve",
            "email": "eve@example.com",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "access_code": settings.SIGNUP_ACCESS_CODE,
        },
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not User.objects.filter(username="eve").exists()


@pytest.mark.django_db
def test_form_encoded_login_refused(user: User) -> None:
    """Only JSON is parsed, so a plain cross-site HTML form cannot post a login."""
    client = Client(enforce_csrf_checks=True)
    token = _csrf(client)
    response = client.post(
        "/api/auth/login/",
        {"username": "ada", "password": PASSWORD},
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 415


# -- the client address cannot be chosen by the client -----------------------------


def test_client_ip_reads_the_hop_nginx_set() -> None:
    request = SimpleNamespace(
        META={"REMOTE_ADDR": "172.18.0.5", "HTTP_X_FORWARDED_FOR": "6.6.6.6, 1.2.3.4"}
    )
    assert client_ip(request) == "1.2.3.4"
    assert signup_gate.client_subject(request) == "1.2.3.4"
    assert client_ip(SimpleNamespace(META={"REMOTE_ADDR": "9.9.9.9"})) == "9.9.9.9"


def test_demo_ignores_cf_connecting_ip() -> None:
    from apps.demo.middleware import client_ip as demo_ip

    request = SimpleNamespace(
        META={
            "REMOTE_ADDR": "172.18.0.5",
            "HTTP_CF_CONNECTING_IP": "6.6.6.6",
            "HTTP_X_FORWARDED_FOR": "1.2.3.4",
        }
    )
    assert demo_ip(request) == "1.2.3.4"


@pytest.mark.django_db
def test_signup_ban_not_evaded_by_rotating_forwarded_for() -> None:
    for n in range(settings.SIGNUP_CODE_MAX_FAILURES):
        client = Client(enforce_csrf_checks=True)
        _send(
            client,
            "post",
            "/api/auth/register/",
            {"username": f"u{n}", "email": f"u{n}@x.edu", "access_code": "000000"},
            HTTP_X_FORWARDED_FOR=f"10.1.1.{n}, 203.0.113.7",
        )
    assert signup_gate.is_shadow_banned("203.0.113.7") is True


# -- the activation gate -----------------------------------------------------------


@pytest.mark.django_db
def test_unverified_account_gated_when_verification_required(
    user: User, settings
) -> None:
    settings.API_REQUIRE_VERIFIED_EMAIL = True
    settings.SIGNUP_VERIFY_EMAIL = True
    client = Client()
    client.force_login(user)

    assert client.get("/api/auth/watch/me/").status_code == 403
    # Everything needed to become verified, or to leave, still answers.
    assert client.get("/api/auth/me/").status_code == 200
    assert client.get("/api/auth/account/").status_code == 200
    assert client.get("/api/auth/account/export/").status_code == 200

    verified(user)
    assert client.get("/api/auth/watch/me/").status_code == 200


@pytest.mark.django_db
def test_activation_gate_inert_when_verification_off(user: User, settings) -> None:
    settings.API_REQUIRE_VERIFIED_EMAIL = True
    settings.SIGNUP_VERIFY_EMAIL = False
    settings.SIGNUP_MODE = "open"
    client = Client()
    client.force_login(user)
    assert client.get("/api/auth/watch/me/").status_code == 200


# -- codes and enumeration ---------------------------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_code_attempts_cannot_exceed_the_budget(user: User) -> None:
    """Each guess reserves an attempt in the database before it is compared."""
    email_verification.issue(user, user.email)
    row = EmailVerification.objects.get(user=user)
    compared = []
    real = email_verification.hmac.compare_digest

    def counting(a, b):
        compared.append(1)
        return real(a, b)

    with patch.object(email_verification.hmac, "compare_digest", counting):
        for _ in range(email_verification.MAX_ATTEMPTS + 5):
            with pytest.raises(email_verification.VerificationError):
                email_verification.verify(user, "000000")
    assert len(compared) <= email_verification.MAX_ATTEMPTS
    row.refresh_from_db()
    assert row.attempts == email_verification.MAX_ATTEMPTS
    assert row.consumed_at is not None


@pytest.mark.django_db
def test_password_reset_does_the_same_work_for_any_address(
    user: User, settings
) -> None:
    """The request only enqueues; the lookup and the send happen off the request."""
    settings.PASSWORD_RESET_MAIL_ASYNC = True
    queued = []
    with patch(
        "apps.accounts.tasks.send_password_reset.apply_async",
        side_effect=lambda args, retry: queued.append(args),
    ):
        known = _send(
            Client(enforce_csrf_checks=True),
            "post",
            "/api/auth/password/reset/",
            {"email": "ada@example.com"},
        )
        unknown = _send(
            Client(enforce_csrf_checks=True),
            "post",
            "/api/auth/password/reset/",
            {"email": "nobody@example.com"},
        )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert queued == [["ada@example.com"], ["nobody@example.com"]]
    assert mail.outbox == []


# -- sessions ----------------------------------------------------------------------


@pytest.mark.django_db
def test_sign_out_everywhere_ends_other_sessions(user: User) -> None:
    laptop, phone = Client(enforce_csrf_checks=True), Client(enforce_csrf_checks=True)
    assert _login(laptop, PASSWORD).status_code == 200
    assert _login(phone, PASSWORD).status_code == 200

    response = _send(phone, "post", "/api/auth/sessions/revoke/")
    assert response.status_code == 200
    assert response.json()["ended"] == 1
    assert laptop.get("/api/auth/me/").status_code == 401
    assert phone.get("/api/auth/me/").status_code == 200
    assert AuditEvent.objects.filter(action="account.sessions_revoked").exists()


# -- privacy rights: deletion and export -------------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_account_delete_cascades(user: User) -> None:
    lab = create_lab_workspace(user, "Ada's own lab").lab  # hers alone
    AuthorWork.objects.create(user=user, source="openalex", source_id="W1", title="T")
    bystander = User.objects.create_user(username="bo", email="bo@example.com")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    assert _send(client, "post", "/api/auth/account/delete/request/").status_code == 202
    code = _code_from_outbox()

    # Both proofs are required.
    wrong_password = _send(
        client, "delete", "/api/auth/account/", {"password": "nope", "code": code}
    )
    assert wrong_password.status_code == 400
    assert User.objects.filter(pk=user.pk).exists()

    response = _send(
        client, "delete", "/api/auth/account/", {"password": PASSWORD, "code": code}
    )
    assert response.status_code == 204
    assert not User.objects.filter(pk=user.pk).exists()
    assert not Profile.objects.filter(user_id=user.pk).exists()
    assert not AuthorWork.objects.filter(user_id=user.pk).exists()
    assert not Lab.objects.filter(pk=lab.pk).exists()
    assert User.objects.filter(pk=bystander.pk).exists()
    event = AuditEvent.objects.get(action="account.delete")
    assert event.target_id == str(user.pk) and event.actor is None
    assert client.get("/api/auth/me/").status_code == 401


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=LOCMEM)
def test_account_delete_refused_for_sole_owner_of_shared_lab(user: User) -> None:
    lab = create_lab_workspace(user, "Shared lab").lab
    other = User.objects.create_user(username="bo", email="bo@example.com")
    LabMembership.objects.create(lab=lab, user=other)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = _send(client, "post", "/api/auth/account/delete/request/")
    assert response.status_code == 409
    assert response.json()["reason"] == "sole_owner"
    assert mail.outbox == []


@pytest.mark.django_db
def test_export_contains_only_own_data(user: User) -> None:
    other = User.objects.create_user(username="bo", email="bo@example.com")
    AuthorWork.objects.create(
        user=user, source="openalex", source_id="MINE", title="Mine"
    )
    AuthorWork.objects.create(
        user=other, source="openalex", source_id="THEIRS", title="Theirs"
    )
    client = Client()
    client.force_login(user)

    response = client.get("/api/auth/account/export/")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")
    body = response.json()
    assert body["account"]["username"] == "ada"
    text = response.content.decode()
    assert "MINE" in text
    assert "THEIRS" not in text and "bo@example.com" not in text
    assert "pbkdf2" not in text and "argon2" not in text  # no password hash
    works = body["records"]["accounts.AuthorWork.user"]
    assert [w["source_id"] for w in works] == ["MINE"]
    assert "accounts.Profile.user" in body["records"]
    assert all(
        "embedding" not in row for row in body["records"]["accounts.Profile.user"]
    )

"""Email verification: the code, its bounds, and what it activates."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts import email_verification
from apps.accounts.models import EmailVerification, Lab, LabMembership

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture(autouse=True)
def _mail_sends_immediately(monkeypatch):
    """Run ``on_commit`` hooks inline for the duration of a test.

    ``email_verification`` deliberately mails on commit, so a rolled-back sign-up
    can never leave a live code in a real inbox. Tests run inside a transaction
    that is rolled back and never commits, so without this the outbox stays empty
    and every assertion about the mail would pass vacuously.
    """
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, *args, **kwargs: func()
    )


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        username="ada", email="ada@example.com", password="pw-Str0ng-1234"
    )


@pytest.fixture
def client_for(user: User) -> Client:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return client


def _post(client: Client, path: str, payload: dict | None = None):
    client.get("/api/auth/csrf/")
    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    return client.post(
        path,
        data=payload or {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _code_from_outbox() -> str:
    """The six digits the code email actually carries."""
    body = mail.outbox[-1].body
    digits = [word for word in body.split() if word.isdigit() and len(word) == 6]
    assert digits, f"no code in body: {body!r}"
    return digits[0]


# -- the service ---------------------------------------------------------------


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_issue_mails_a_code_and_stores_only_its_hash(user: User) -> None:
    mail.outbox.clear()
    issued = email_verification.issue(user, user.email)

    assert len(mail.outbox) == 1
    code = _code_from_outbox()
    assert len(code) == 6
    # The plaintext code must never be recoverable from the row.
    assert code not in issued.verification.code_hash
    assert issued.verification.code_hash != code


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_verify_accepts_the_code_and_activates_the_account(user: User) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)

    email_verification.verify(user, _code_from_outbox())

    user.refresh_from_db()
    assert user.profile.is_verified is True


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_code_is_worth_exactly_one_use(user: User) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)
    code = _code_from_outbox()

    email_verification.verify(user, code)
    with pytest.raises(email_verification.CodeInvalid):
        email_verification.verify(user, code)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_wrong_codes_are_capped(user: User) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)
    real = _code_from_outbox()
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(email_verification.MAX_ATTEMPTS - 1):
        with pytest.raises(email_verification.CodeInvalid):
            email_verification.verify(user, wrong)
    with pytest.raises(email_verification.TooManyAttempts):
        email_verification.verify(user, wrong)

    # The budget is spent, so even the right code no longer works.
    with pytest.raises(email_verification.VerificationError):
        email_verification.verify(user, real)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_an_expired_code_is_refused(user: User) -> None:
    mail.outbox.clear()
    issued = email_verification.issue(user, user.email)
    code = _code_from_outbox()

    EmailVerification.objects.filter(pk=issued.verification.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(email_verification.CodeExpired):
        email_verification.verify(user, code)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_resend_replaces_the_outstanding_code(user: User) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)
    first = _code_from_outbox()
    email_verification.issue(user, user.email)
    second = _code_from_outbox()

    with pytest.raises(email_verification.CodeInvalid):
        email_verification.verify(user, first)
    email_verification.verify(user, second)
    user.refresh_from_db()
    assert user.profile.is_verified is True


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_resend_cooldown_blocks_a_second_immediate_send(user: User) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)
    with pytest.raises(email_verification.ResendTooSoon):
        email_verification.issue(user, user.email, enforce_cooldown=True)


# -- the API -------------------------------------------------------------------


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_verify_endpoint_activates_and_reports_the_account(
    user: User, client_for: Client
) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)

    response = _post(
        client_for, "/api/auth/email/verify/", {"code": _code_from_outbox()}
    )

    assert response.status_code == 200
    assert response.json()["is_verified"] is True


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_verify_endpoint_rejects_a_wrong_code(
    user: User, client_for: Client
) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)
    real = _code_from_outbox()
    wrong = "000000" if real != "000000" else "111111"

    response = _post(client_for, "/api/auth/email/verify/", {"code": wrong})

    assert response.status_code == 400
    assert "code" in response.json()
    user.refresh_from_db()
    assert user.profile.is_verified is False


# -- changing the address ------------------------------------------------------


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_change_waits_for_the_new_address_to_answer(
    user: User, client_for: Client
) -> None:
    mail.outbox.clear()
    response = _post(
        client_for,
        "/api/auth/email/change/",
        {"new_email": "ada@newlab.example.com", "current_password": "pw-Str0ng-1234"},
    )

    assert response.status_code == 202
    user.refresh_from_db()
    # Not applied yet — a typo must not take the account's reset path with it.
    assert user.email == "ada@example.com"
    assert mail.outbox[-1].to == ["ada@newlab.example.com"]

    confirmed = _post(
        client_for, "/api/auth/email/verify/", {"code": _code_from_outbox()}
    )
    assert confirmed.status_code == 200
    user.refresh_from_db()
    assert user.email == "ada@newlab.example.com"


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_change_needs_the_current_password(
    user: User, client_for: Client
) -> None:
    response = _post(
        client_for,
        "/api/auth/email/change/",
        {"new_email": "ada@newlab.example.com", "current_password": "wrong"},
    )
    assert response.status_code == 400


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_email_change_refuses_an_address_another_account_holds(
    user: User, client_for: Client
) -> None:
    User.objects.create_user(
        username="grace", email="grace@example.com", password="pw-Str0ng-1234"
    )
    response = _post(
        client_for,
        "/api/auth/email/change/",
        {"new_email": "GRACE@example.com", "current_password": "pw-Str0ng-1234"},
    )
    assert response.status_code == 400
    assert "already exists" in str(response.json())


# -- what activation unlocks ---------------------------------------------------


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_an_unverified_account_cannot_start_a_lab(
    user: User, client_for: Client
) -> None:
    response = _post(client_for, "/api/auth/labs/", {"name": "Ada Lab"})

    assert response.status_code == 403
    assert not Lab.objects.filter(name="Ada Lab").exists()


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_verifying_unlocks_starting_a_lab(user: User, client_for: Client) -> None:
    mail.outbox.clear()
    email_verification.issue(user, user.email)
    _post(client_for, "/api/auth/email/verify/", {"code": _code_from_outbox()})

    response = _post(client_for, "/api/auth/labs/", {"name": "Ada Lab"})

    assert response.status_code == 201
    lab = Lab.objects.get(name="Ada Lab")
    assert LabMembership.objects.filter(user=user, lab=lab, is_lead=True).exists()


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_an_unverified_lab_owner_cannot_edit_the_lab_profile_or_invite(
    user: User, client_for: Client
) -> None:
    """A lab account provisioned at sign-up exists, but stays a shell.

    Registration builds the org row inside its own transaction, when nobody is
    verified yet — so the gate lands on the writes that follow, not on sign-up.
    """
    from apps.billing.services import create_lab_workspace

    lab = create_lab_workspace(user, "Shell Lab").lab

    client_for.get("/api/auth/csrf/")
    csrf = client_for.cookies[settings.CSRF_COOKIE_NAME].value
    edited = client_for.patch(
        f"/api/auth/labs/{lab.slug}/profile/",
        data={"statement": "We study things."},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert edited.status_code == 403

    invited = _post(
        client_for,
        f"/api/auth/labs/{lab.slug}/invitations/",
        {"identifier": "someone@example.com", "role": "member"},
    )
    assert invited.status_code == 403

    # Reading the lab is untouched — verification gates building, not browsing.
    assert client_for.get(f"/api/auth/labs/{lab.slug}/profile/").status_code == 200

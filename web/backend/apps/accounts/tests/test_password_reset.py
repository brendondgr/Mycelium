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

from apps.accounts import email_verification, password_reset
from apps.accounts.models import EmailVerification
from apps.accounts.views import RESET_REQUESTED_MESSAGE

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD = "pw-Str0ng-1234"
NEW_PASSWORD = "n3w-Str0ng-9876"


@pytest.fixture(autouse=True)
def _mail_sends_immediately(monkeypatch):
    """Run ``on_commit`` hooks inline; see ``test_email_verification`` for why."""
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, *args, **kwargs: func()
    )


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


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_asking_for_a_reset_changes_nothing(user: User) -> None:
    """A reset request is an *offer*, never a revocation.

    Asking for a link must not touch the account: the old password keeps
    working, sessions stay alive, and nothing happens until someone who can read
    the mailbox actually spends the link. Anything else would turn this
    unauthenticated endpoint into a way to lock a stranger out of their account
    by typing their address.
    """
    before = User.objects.values_list("password", flat=True).get(pk=user.pk)
    mail.outbox.clear()

    _request(user.email)

    after = User.objects.values_list("password", flat=True).get(pk=user.pk)
    assert after == before
    user.refresh_from_db()
    assert user.check_password(PASSWORD)
    assert len(mail.outbox) == 1  # the offer went out, the account is untouched


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_an_unspent_link_leaves_the_old_password_working(user: User) -> None:
    """Ignoring the email costs nothing, even after several requests."""
    mail.outbox.clear()
    _request(user.email)
    _request(user.email)

    user.refresh_from_db()
    assert user.check_password(PASSWORD)


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


@override_settings(
    EMAIL_BACKEND=LOCMEM, EMAIL_APP_BASE_URL="https://mycelium.example.edu"
)
def test_the_emailed_link_is_absolute_and_not_loopback(user: User) -> None:
    """On an instance with a public origin, the mailed link uses it."""
    url = password_reset.reset_url(user)
    assert url.startswith("https://mycelium.example.edu/reset-password?")
    assert "localhost" not in url and "127.0.0.1" not in url


@override_settings(EMAIL_BACKEND=LOCMEM, EMAIL_APP_BASE_URL="http://localhost:11050")
def test_a_local_only_instance_mails_its_local_origin(user: User) -> None:
    """With no public origin (a single-machine install), the link points at
    the local gateway rather than someone else's site or a bare path."""
    url = password_reset.reset_url(user)
    assert url.startswith("http://localhost:11050/reset-password?")


# -- changing a password from inside the app -------------------------------------
#
# Two steps, and the proof is the mailbox — not the old password. A signed-in
# browser on its own is not enough; a code sent to the account's own address is.
# The current password is deliberately never asked for: the person changing a
# password is often the person who cannot remember it, and anyone who could
# produce it could sign out and use `password/reset/` instead, which never asked.


@pytest.fixture
def signed_in(user: User) -> Client:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    return client


def _request_change(client: Client):
    return _post(client, "/api/auth/password/change/request/", {})


def _confirm_change(client: Client, code: str):
    return _post(
        client,
        "/api/auth/password/change/",
        {
            "code": code,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
    )


def _code_from_outbox() -> str:
    body = mail.outbox[-1].body
    digits = [word for word in body.split() if word.isdigit() and len(word) == 6]
    assert digits, f"no code in body: {body!r}"
    return digits[0]


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_signed_in_session_alone_cannot_change_the_password(
    user: User, signed_in: Client
) -> None:
    """An unlocked browser is not authority; something outside it must agree."""
    response = _post(
        signed_in,
        "/api/auth/password/change/",
        {
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
    )

    assert response.status_code == 400
    assert "code" in response.json()
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_the_emailed_code_completes_the_change(
    user: User, signed_in: Client
) -> None:
    mail.outbox.clear()
    assert _request_change(signed_in).status_code == 202
    assert mail.outbox[-1].to == [user.email]

    response = _confirm_change(signed_in, _code_from_outbox())

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    # The session was re-stamped, so this browser is still signed in.
    assert signed_in.get("/api/auth/me/").status_code == 200


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_someone_who_forgot_their_password_can_still_change_it(
    user: User, signed_in: Client
) -> None:
    """The case the old design got wrong.

    Being signed in and not remembering your password is the *normal* reason to
    change one. Asking for the old password would have sent this person out to
    the signed-out reset flow to prove the very same thing — the mailbox — so it
    is not asked for at either step.
    """
    mail.outbox.clear()
    assert _request_change(signed_in).status_code == 202

    response = _confirm_change(signed_in, _code_from_outbox())

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_wrong_code_leaves_the_password_alone(
    user: User, signed_in: Client
) -> None:
    mail.outbox.clear()
    _request_change(signed_in)
    real = _code_from_outbox()
    wrong = "000000" if real != "000000" else "111111"

    response = _confirm_change(signed_in, wrong)

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_code_is_worth_one_change(user: User, signed_in: Client) -> None:
    """The code is the whole proof, so it must not be replayable."""
    mail.outbox.clear()
    _request_change(signed_in)
    code = _code_from_outbox()

    assert _confirm_change(signed_in, code).status_code == 200
    assert _confirm_change(signed_in, code).status_code == 400


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_verification_code_cannot_be_spent_on_a_password(
    user: User, signed_in: Client
) -> None:
    """Codes are scoped to a purpose, and the scope is enforced, not decorative."""
    mail.outbox.clear()
    email_verification.issue(user, user.email)  # a sign-up confirmation code

    response = _confirm_change(signed_in, _code_from_outbox())

    assert response.status_code == 400
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_a_password_code_does_not_settle_a_pending_email_change(
    user: User, signed_in: Client
) -> None:
    """The reverse direction: one flow's proof must not leak into another's."""
    email_verification.issue(
        user, "moved@example.com", EmailVerification.Purpose.CHANGE
    )
    mail.outbox.clear()
    _request_change(signed_in)

    assert _confirm_change(signed_in, _code_from_outbox()).status_code == 200

    user.refresh_from_db()
    assert user.email == "ada@example.com"
    assert email_verification.pending_email(user) == "moved@example.com"


@override_settings(EMAIL_BACKEND=LOCMEM)
def test_password_change_requires_authentication(user: User) -> None:
    anonymous = Client(enforce_csrf_checks=True)
    assert _request_change(anonymous).status_code in (401, 403)
    assert _confirm_change(anonymous, "123456").status_code in (401, 403)

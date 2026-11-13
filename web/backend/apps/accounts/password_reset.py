"""Password reset by emailed link.

The flow starts in a browser that is signed out and often on a different device
from the one that lost the password, so it is a link rather than a code: the
recipient clicks once and lands on a form, instead of copying digits between
windows.

The token is Django's own :data:`~django.contrib.auth.tokens.default_token_generator`
rather than anything invented here, and the choice matters. That generator HMACs
the user's primary key together with the *current password hash* and
``last_login``, so a token stops working the instant the password changes or the
user signs in — which makes it single-use without a table to write, and makes a
stolen link worthless the moment it has been used once. ``PASSWORD_RESET_TIMEOUT``
bounds the rest.

The one thing this module refuses to do is say whether an address is registered.
:func:`request_reset` returns the same nothing either way and the view answers
200 either way, so the endpoint cannot be walked to enumerate accounts.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.core.mail import app_url, send_email

logger = logging.getLogger(__name__)

#: Where the emailed link lands in the app.
RESET_PATH = "/reset-password"


class ResetTokenInvalid(Exception):
    """The uid/token pair does not identify a live reset request."""


def request_reset(email: str) -> bool:
    """Mail a reset link to ``email`` if it belongs to an account.

    Returns whether a message went out, for logging and tests only. Callers must
    not vary their response on it — see the module docstring.
    """
    address = str(email or "").strip()
    if not address:
        return False

    user = (
        User.objects.filter(email__iexact=address, is_active=True)
        .order_by("pk")
        .first()
    )
    if user is None:
        logger.info("Password reset requested for an unknown address")
        return False

    outcome = send_email(
        "password_reset",
        to=user.email,
        context={
            "recipient_name": (user.first_name or "").strip(),
            "reset_url": reset_url(user),
            "expires_in": _expires_in(),
        },
        fail_silently=True,
    )
    if not outcome.sent:
        logger.error("Password reset email not accepted for user %s", user.pk)
    return bool(outcome.sent)


def request_reset_later(email: str) -> None:
    """Hand the lookup and the send to the worker; return at once either way.

    The view's only work is this enqueue, which costs the same whether or not
    the address belongs to anyone — so the response time can no longer tell a
    prober which addresses have accounts, as the inline send did. With no worker
    reachable it falls back to sending inline (a degraded instance should still
    let people reset a password). ``PASSWORD_RESET_MAIL_ASYNC = False`` sends
    inline always, for tests and single-process setups.
    """
    address = str(email or "").strip()
    if not address:
        return

    def _dispatch() -> None:
        if not getattr(settings, "PASSWORD_RESET_MAIL_ASYNC", True):
            request_reset(address)
            return
        try:
            from .tasks import send_password_reset

            send_password_reset.apply_async(args=[address], retry=False)
        except Exception:  # noqa: BLE001 — no broker: still send the mail
            logger.warning("Password reset queued inline: no task broker")
            request_reset(address)

    transaction.on_commit(_dispatch)


def reset_url(user: User) -> str:
    """The absolute link mailed to ``user``."""
    query = urlencode(
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
    )
    return f"{app_url(RESET_PATH)}?{query}"


def resolve(uid: str, token: str) -> User:
    """The user a live uid/token pair belongs to.

    Raises :class:`ResetTokenInvalid` for every failure mode — bad encoding,
    unknown user, inactive user, spent or expired token — because telling them
    apart would leak which accounts exist.
    """
    try:
        pk = force_str(urlsafe_base64_decode(str(uid or "")))
        user = User.objects.get(pk=pk, is_active=True)
    except Exception as exc:
        raise ResetTokenInvalid("That reset link is not valid.") from exc

    if not default_token_generator.check_token(user, str(token or "")):
        raise ResetTokenInvalid("That reset link has expired or was already used.")
    return user


def confirm_reset(uid: str, token: str, password: str) -> User:
    """Set a new password for the account the link identifies.

    Verifying the link also verifies the mailbox: the only way to hold this token
    is to have read mail sent to the account's address. So a reset marks the
    profile verified, which is what activates the account — a user who lost their
    password on an unverified account is not made to chase a second code.
    """
    user = resolve(uid, token)
    validate_password(password, user)  # raises DjangoValidationError

    user.set_password(password)
    user.save(update_fields=["password"])

    profile = getattr(user, "profile", None)
    if profile is not None and not profile.is_verified:
        profile.is_verified = True
        profile.save(update_fields=["is_verified"])
        # The mailbox is now proved, so lab invitations sent to it are theirs.
        from .services import claim_pending_invitations

        claim_pending_invitations(user)

    return user


def _expires_in() -> str:
    """``PASSWORD_RESET_TIMEOUT`` phrased for a reader, not a machine."""
    seconds = int(getattr(settings, "PASSWORD_RESET_TIMEOUT", 3600))
    hours = seconds // 3600
    if hours >= 24:
        days = hours // 24
        return "1 day" if days == 1 else f"{days} days"
    if hours >= 1:
        return "1 hour" if hours == 1 else f"{hours} hours"
    minutes = max(1, seconds // 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


__all__ = [
    "ResetTokenInvalid",
    "confirm_reset",
    "request_reset",
    "reset_url",
    "resolve",
]


# Re-exported so callers can catch Django's validator error without importing it.
PasswordPolicyError = DjangoValidationError

"""Proving that a person controls an email address.

Three flows need that proof and all run through here: confirming the address a
new account signed up with, confirming an address a signed-in user wants to move
to, and authorising a password change from inside the app. Each is a six-digit
code mailed to the address in question, because the person is already in front
of the app — a link would only send them to a second tab to come back from.

What verification *means* here is activation. Mycelium mails invitations to
people who have never heard of it, so an account that has not answered its own
mailbox is not allowed to stand up an organization and start inviting from it;
:mod:`apps.accounts.permissions` reads the flag this module sets.

Codes are scoped to a purpose and looked up by it, which is a security property
rather than bookkeeping: a code mailed to confirm an address cannot be redirected
into changing a password, so no flow can be tricked into spending another's
proof.

Three bounds keep a six-digit secret honest:

* **Expiry.** :data:`CODE_TTL` from issue, not from last use.
* **Attempts.** :data:`MAX_ATTEMPTS` wrong guesses burn the code — the next
  attempt needs a fresh one, which costs an email.
* **Resend cooldown.** :data:`RESEND_COOLDOWN` stops the resend button being
  turned into a mail cannon aimed at someone else's inbox.

The code is never persisted. What the row holds is a ``SECRET_KEY``-keyed HMAC,
salted per row: a plain digest of a six-digit number is reversed by counting to
a million, and a database dump should not hand out live codes.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.core.mail import send_email

from . import institution, invites
from .models import EmailVerification

logger = logging.getLogger(__name__)

#: How long an issued code stays usable.
CODE_TTL = timedelta(minutes=30)
#: Wrong guesses allowed against one code before it is burned.
MAX_ATTEMPTS = 5
#: Minimum gap between two sends for the same purpose.
RESEND_COOLDOWN = timedelta(seconds=60)

#: Human phrasing of :data:`CODE_TTL` for the email body.
EXPIRES_IN = "30 minutes"

_HMAC_SALT = "apps.accounts.email_verification"

#: Which template carries the code, per purpose.
#:
#: A password change gets its own wording rather than the generic code email. A
#: bare "here is a code" arriving while someone is being socially engineered is
#: indistinguishable from every phishing message ever sent; the mail should say
#: what the code will do so an unexpected one reads as an alarm.
_TEMPLATES = {
    EmailVerification.Purpose.PASSWORD: "password_change_code",
    EmailVerification.Purpose.DELETE: "account_delete_code",
}
_DEFAULT_TEMPLATE = "verification_code"


class VerificationError(Exception):
    """Base class for every refusal this module makes."""


class CodeInvalid(VerificationError):
    """No live code matches what was submitted."""


class CodeExpired(VerificationError):
    """A code existed but its window has closed."""


class TooManyAttempts(VerificationError):
    """The attempt budget for the outstanding code is spent."""


class ResendTooSoon(VerificationError):
    """A code was mailed moments ago; wait out the cooldown."""


class EmailTaken(VerificationError):
    """The address was claimed by another account between issue and confirm."""


@dataclass(frozen=True)
class Issued:
    """The row that was created, and whether its email actually went out."""

    verification: EmailVerification
    mailed: bool


def issue(
    user: User,
    email: str,
    purpose: str = EmailVerification.Purpose.SIGNUP,
    *,
    enforce_cooldown: bool = False,
) -> Issued:
    """Mail ``user`` a fresh code for ``email`` and record it.

    Any earlier outstanding code for the same purpose is consumed first, so a
    user only ever has one live code per flow and a resend genuinely replaces
    rather than widens the guessing surface.

    The send happens on transaction commit. Mailing from inside the transaction
    would let a rollback leave a real code in a real inbox for an account that
    does not exist.
    """
    address = str(email or "").strip()
    if not address:
        raise CodeInvalid("No address to verify.")

    now = timezone.now()
    outstanding = _outstanding(user, purpose)
    if enforce_cooldown and outstanding is not None:
        if now - outstanding.created_at < RESEND_COOLDOWN:
            raise ResendTooSoon(
                "A code was just sent. Wait a minute before asking for another."
            )
    if outstanding is not None:
        outstanding.consumed_at = now
        outstanding.save(update_fields=["consumed_at"])

    code = _new_code()
    verification = EmailVerification(
        user=user,
        email=address,
        purpose=purpose,
        expires_at=now + CODE_TTL,
    )
    verification.code_hash = _hash(verification.pk, code)
    verification.save()

    mailed = _deliver(user, address, code, purpose)
    return Issued(verification=verification, mailed=mailed)


def verify(
    user: User,
    code: str,
    purpose: str = EmailVerification.Purpose.SIGNUP,
) -> EmailVerification:
    """Check ``code`` and, on success, apply what it proves.

    A sign-up code marks the profile verified. A change code does that *and*
    moves ``User.email`` to the address that answered. Either way the row is
    consumed, so a code is worth exactly one use.
    """
    submitted = "".join(ch for ch in str(code or "") if ch.isdigit())
    verification = _outstanding(user, purpose)
    if verification is None:
        raise CodeInvalid("That code is not valid. Ask for a new one.")

    now = timezone.now()
    if verification.expires_at <= now:
        verification.consumed_at = now
        verification.save(update_fields=["consumed_at"])
        raise CodeExpired("That code has expired. Ask for a new one.")

    # Reserve an attempt *before* comparing, in one conditional UPDATE. Reading
    # the counter and writing it back later let concurrent guesses each see the
    # same count and each get a comparison, so the budget of MAX_ATTEMPTS could be
    # spent many times over by firing requests in parallel. Here the database
    # hands out at most MAX_ATTEMPTS comparisons per code, however many arrive.
    reserved = EmailVerification.objects.filter(
        pk=verification.pk, consumed_at__isnull=True, attempts__lt=MAX_ATTEMPTS
    ).update(attempts=F("attempts") + 1)
    if not reserved:
        EmailVerification.objects.filter(
            pk=verification.pk, consumed_at__isnull=True
        ).update(consumed_at=now)
        raise TooManyAttempts("Too many wrong codes. Ask for a new one.")
    verification.refresh_from_db(fields=["attempts"])

    if not submitted or not hmac.compare_digest(
        verification.code_hash, _hash(verification.pk, submitted)
    ):
        remaining = MAX_ATTEMPTS - verification.attempts
        if remaining <= 0:
            raise TooManyAttempts("Too many wrong codes. Ask for a new one.")
        raise CodeInvalid("That code is not correct.")

    with transaction.atomic():
        if purpose == EmailVerification.Purpose.CHANGE:
            if _email_taken(verification.email, exclude=user):
                raise EmailTaken("An account with that email already exists.")
            user.email = verification.email
            user.save(update_fields=["email"])
        verification.consumed_at = now
        verification.save(update_fields=["consumed_at"])
        profile = user.profile
        if not profile.is_verified:
            profile.is_verified = True
            profile.save(update_fields=["is_verified"])
        # The proved address decides the institution — a change code can move
        # a person to another one, or to none.
        institution.verified_then_sync(user)

    # An invitation addressed to the address they just proved is claimed now.
    # Someone who was invited but signed up on their own — rather than through
    # the link — would otherwise sit outside the lab that asked for them with
    # nothing to tell either party why. Deferred to commit, and never allowed to
    # fail the verification it rides on.
    transaction.on_commit(lambda: invites.claim_for_verified_email(user))
    # Legacy in-app lab invitations sent to this address become visible (and
    # answerable) only now that the mailbox is proved.
    from .services import claim_pending_invitations

    transaction.on_commit(lambda: claim_pending_invitations(user))

    return verification


def pending_email(user: User) -> str:
    """The address a live change request is waiting on, or ``""``."""
    outstanding = _outstanding(user, EmailVerification.Purpose.CHANGE)
    if outstanding is None or outstanding.expires_at <= timezone.now():
        return ""
    return outstanding.email


def _outstanding(user: User, purpose: str) -> EmailVerification | None:
    return (
        EmailVerification.objects.filter(
            user=user, purpose=purpose, consumed_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )


def _email_taken(email: str, *, exclude: User) -> bool:
    return (
        User.objects.filter(email__iexact=email).exclude(pk=exclude.pk).exists()
    )


def _new_code() -> str:
    """A six-digit code, uniformly drawn, leading zeros preserved."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash(row_id, code: str) -> str:
    return salted_hmac(f"{_HMAC_SALT}:{row_id}", code).hexdigest()


def _deliver(user: User, address: str, code: str, purpose: str) -> bool:
    """Mail the code on commit; report whether the send was even attempted.

    Failures are swallowed and logged rather than raised. A verification email
    that cannot be sent must not take down the sign-up that triggered it — the
    account exists, and the person can ask for another code from the screen they
    are already looking at.
    """
    template = _TEMPLATES.get(purpose, _DEFAULT_TEMPLATE)
    context = {
        "recipient_name": (user.first_name or "").strip(),
        "code": code,
        "expires_in": EXPIRES_IN,
    }

    def _send() -> None:
        try:
            outcome = send_email(
                template,
                to=address,
                context=context,
                fail_silently=True,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Verification code send failed for user %s", user.pk)
            return
        if not outcome.sent:
            logger.error(
                "Verification code not accepted for user %s (%s)", user.pk, address
            )

    transaction.on_commit(_send)
    return True

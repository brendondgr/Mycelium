"""The shared-code sign-up gate: the code + a brute-force shadow ban.

Used only when the instance's ``signup.mode`` is ``"code"`` (see
``apps.accounts.signup_policy`` for the other modes); then registration is
closed unless the caller presents ``settings.SIGNUP_ACCESS_CODE``.
Because that is a single shared secret on a public endpoint, it needs a guessing
budget: three consecutive misses from the same client trip a one-hour **shadow**
ban.

"Shadow" is the whole point of the policy — a banned client is never told it is
banned. Every attempt during the ban returns the same generic "that code is not
valid" body a plain miss returns, and a *correct* code is refused too, so a prober
cannot use the response to confirm either the code or the ban. Only the clock
lifts it.

State lives in the ``signup`` Redis cache (never process memory) so a ban survives
a redeploy and is shared by every web process. Reads fail **closed**, matching
``apps.integrations.services.state``: if Redis is unreachable we treat the client
as banned rather than hand out an unmetered guessing surface at exactly the moment
we cannot count guesses.
"""

from __future__ import annotations

import hmac

from django.conf import settings
from django.core.cache import caches

# The one message the endpoint ever returns for a code problem. Wrong code,
# missing code, and shadow-banned are deliberately indistinguishable.
INVALID_CODE_MESSAGE = "That verification code is not valid."


def _cache():
    # Looked up per call (not captured at import) so test overrides of CACHES take
    # effect, mirroring the Discord state module.
    return caches["signup"]


def client_subject(request) -> str:
    """The client identity a ban is keyed on: the originating IP.

    Read by the same rule as every other per-client control
    (:func:`apps.accounts.client_ip.client_ip`): the right-most
    ``X-Forwarded-For`` hop, which nginx sets. The left-most hop used to be read
    here, and the client writes that one — so a prober could rotate it on every
    request and never reach the ban.
    """
    from .client_ip import client_ip

    return client_ip(request)


def code_matches(value: str) -> bool:
    """Constant-time compare of a submitted code against the live one."""
    expected = str(settings.SIGNUP_ACCESS_CODE or "")
    submitted = str(value or "").strip()
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


def is_shadow_banned(subject: str) -> bool:
    """True while ``subject`` is serving a ban (fail-closed on a cache error)."""
    try:
        return bool(_cache().get(_ban_key(subject)))
    except Exception:
        return True  # fail closed


def record_failure(subject: str) -> None:
    """Count a wrong code; trip the shadow ban once the threshold is crossed."""
    fail_key = _fail_key(subject)
    try:
        try:
            count = _cache().incr(fail_key)
        except ValueError:
            # No counter yet — `add` (not `set`) so two concurrent first-misses
            # cannot each install a fresh window.
            window = settings.SIGNUP_CODE_FAILURE_WINDOW_SECONDS
            _cache().add(fail_key, 1, timeout=window)
            count = _cache().get(fail_key) or 1
        if int(count) >= settings.SIGNUP_CODE_MAX_FAILURES:
            _cache().set(
                _ban_key(subject), True, timeout=settings.SIGNUP_CODE_LOCKOUT_SECONDS
            )
            _cache().delete(fail_key)
    except Exception:
        # Best-effort: a lost count is acceptable because the ban *check* fails
        # closed, so a cache outage never weakens the gate.
        pass


def clear_failures(subject: str) -> None:
    """Reset the streak after a correct code (and for tests / manual relief)."""
    try:
        _cache().delete(_fail_key(subject))
        _cache().delete(_ban_key(subject))
    except Exception:
        pass


def _fail_key(subject: str) -> str:
    return f"signup_fail:{subject}"


def _ban_key(subject: str) -> str:
    return f"signup_ban:{subject}"

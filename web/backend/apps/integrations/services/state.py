"""Ephemeral Discord-link state in Redis (the ``discord`` cache).

Two concerns, both of which must survive a bot/web restart and must never live in
process memory:

* **OAuth ``state`` nonces** — CSRF protection for the account-bind callback. A
  forged callback must not bind an attacker's Discord to a victim's session, so the
  nonce is CSPRNG, single-use, short-TTL, and tied to the Django session that
  started the flow (not derived from the session cookie).
* **``/activate`` lockout** — 5 failures in the window → a 1-hour block, keyed on
  the redeeming ``discord_user_id``.

Failure policy is deliberately *closed*: if Redis is unreachable, nonce validation
returns "invalid" and the lockout check returns "locked", so an outage can never be
used to bypass CSRF or brute-force a code.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from django.conf import settings
from django.core.cache import caches

_NONCE_TTL = 600  # 10 minutes


def _cache():
    # Looked up per call (not captured at import) so test overrides of CACHES and
    # a swapped-in backend take effect.
    return caches["discord"]


class StateBackendError(RuntimeError):
    """Raised when the ephemeral-state backend cannot be used to *start* a flow."""


# --------------------------------------------------------------------------- #
# OAuth state nonces
# --------------------------------------------------------------------------- #
def issue_state(session_key: str, payload: dict[str, Any] | None = None) -> str:
    """Mint a single-use nonce bound to ``session_key``; return it for the URL."""
    nonce = secrets.token_urlsafe(32)
    try:
        _cache().set(
            _nonce_key(nonce),
            {"session": session_key or "", "payload": payload or {}},
            timeout=_NONCE_TTL,
        )
    except Exception as exc:  # Redis down — cannot safely begin the flow.
        raise StateBackendError("state backend unavailable") from exc
    return nonce


def consume_state(nonce: str, session_key: str) -> dict[str, Any] | None:
    """Validate + delete a nonce. Returns its payload, or None if invalid.

    Single-use (deleted on read), session-bound (constant-time compare), and
    fail-closed (Redis error → None).
    """
    if not nonce:
        return None
    try:
        stored = _cache().get(_nonce_key(nonce))
    except Exception:
        return None  # fail closed
    if not stored:
        return None
    try:
        _cache().delete(_nonce_key(nonce))
    except Exception:
        pass
    expected = str(stored.get("session") or "")
    if not hmac.compare_digest(expected, session_key or ""):
        return None
    return stored.get("payload") or {}


def _nonce_key(nonce: str) -> str:
    return f"oauth_state:{nonce}"


# --------------------------------------------------------------------------- #
# /activate lockout
# --------------------------------------------------------------------------- #
def is_locked_out(discord_user_id: str) -> bool:
    """True if this snowflake is currently locked out (fail-closed on error)."""
    try:
        return bool(_cache().get(_lock_key(discord_user_id)))
    except Exception:
        return True  # fail closed: refuse redemption while the backend is down


def record_failure(discord_user_id: str) -> None:
    """Count a failed redemption; trip a lockout once the threshold is crossed."""
    fail_key = _fail_key(discord_user_id)
    window = settings.DISCORD_ACTIVATION_FAILURE_WINDOW_SECONDS
    try:
        try:
            count = _cache().incr(fail_key)
        except ValueError:
            _cache().add(fail_key, 1, timeout=window)
            count = 1
        if count >= settings.DISCORD_ACTIVATION_MAX_FAILURES:
            _cache().set(
                _lock_key(discord_user_id),
                True,
                timeout=settings.DISCORD_ACTIVATION_LOCKOUT_SECONDS,
            )
            _cache().delete(fail_key)
    except Exception:
        # Best-effort: a lost failure count is acceptable; the lock check itself
        # fails closed, so an outage never *weakens* the lockout.
        pass


def clear_failures(discord_user_id: str) -> None:
    """Reset counters after a successful redemption."""
    try:
        _cache().delete(_fail_key(discord_user_id))
        _cache().delete(_lock_key(discord_user_id))
    except Exception:
        pass


def _fail_key(discord_user_id: str) -> str:
    return f"activate_fail:{discord_user_id}"


def _lock_key(discord_user_id: str) -> str:
    return f"activate_lock:{discord_user_id}"

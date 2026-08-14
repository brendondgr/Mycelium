"""Path B — activation code issue + redemption (the OAuth fallback).

Issue (portal, authenticated): generate plaintext, display once, persist only its
sha256. Redeem (``/activate`` in any server Mylo is in): rate-limited, single-use, TTL-
bound, and it binds *the redeeming Discord account* to *the issuing Mycelium user*.

Code policy: an 8-char code over a 30-symbol ambiguity-free alphabet ≈ 39 bits. 8
(not 6 digits/20 bits) because a guessed code binds an attacker's Discord to the
victim's account — the margin has to survive a lockout, not rely on it. A fast hash
is correct here: this is a high-entropy API-key-style secret, not a password.

Known limitation (surface it in the UI): Path B binds the identity but does NOT
grant DM rights the way Path A does, so reachability then depends on the user's
mutual-server DM toggle, which we cannot see or change — expect a higher dm_ok=False
rate. Instrument the split by ``link_method``.
"""

from __future__ import annotations

import enum
import hashlib
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from . import probe, resolve, state
from .resolve import ConsumeOutcome

# 30 symbols, no 0/O/1/I/L/U — unambiguous when read aloud or off a screen.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_LENGTH = 8


def generate_plaintext() -> str:
    """A fresh code as raw chars (no dash). Display formatted; store the hash."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


def format_for_display(plaintext: str) -> str:
    p = plaintext.upper()
    return f"{p[:4]}-{p[4:]}" if len(p) == _LENGTH else p


def normalize(code_input: str) -> str:
    """Uppercase; strip dashes/whitespace. Lookup-by-hash is the comparison."""
    return "".join(ch for ch in (code_input or "").upper() if ch in _ALPHABET)


def hash_code(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def issue_code(user) -> str:
    """Create a code for ``user`` (superseding any prior live one); return plaintext."""
    plaintext = generate_plaintext()
    expires_at = timezone.now() + timezone.timedelta(
        seconds=settings.DISCORD_ACTIVATION_TTL_SECONDS
    )
    resolve.store_activation_code(user, hash_code(plaintext), expires_at)
    return format_for_display(plaintext)


class RedeemOutcome(enum.StrEnum):
    OK = "ok"
    LOCKED_OUT = "locked_out"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    ALREADY_USED = "already_used"
    REBIND_REJECTED = "rebind_rejected"


@dataclass
class RedeemResult:
    outcome: RedeemOutcome
    dm_ok: bool | None = None


_CONSUME_MAP = {
    ConsumeOutcome.NOT_FOUND: RedeemOutcome.NOT_FOUND,
    ConsumeOutcome.EXPIRED: RedeemOutcome.EXPIRED,
    ConsumeOutcome.ALREADY_USED: RedeemOutcome.ALREADY_USED,
    ConsumeOutcome.REBIND_REJECTED: RedeemOutcome.REBIND_REJECTED,
}


def redeem(code_input: str, discord_user_id: str) -> RedeemResult:
    """Redeem a code for a Discord user. Rate-limited and lockout-guarded."""
    discord_user_id = str(discord_user_id)
    if state.is_locked_out(discord_user_id):
        return RedeemResult(RedeemOutcome.LOCKED_OUT)

    result = resolve.consume_activation_code(
        hash_code(normalize(code_input)), discord_user_id
    )
    if result.outcome is not ConsumeOutcome.OK:
        # Every failure — bad, expired, used, cross-user — counts toward lockout.
        state.record_failure(discord_user_id)
        return RedeemResult(_CONSUME_MAP[result.outcome])

    state.clear_failures(discord_user_id)
    dm_ok = _probe_quietly(result.identity)
    return RedeemResult(RedeemOutcome.OK, dm_ok=dm_ok)


def _probe_quietly(identity) -> bool | None:
    """Probe reachability inline; never let a probe failure fail the bind."""
    try:
        return probe.run_probe(identity).dm_ok
    except Exception:
        return None

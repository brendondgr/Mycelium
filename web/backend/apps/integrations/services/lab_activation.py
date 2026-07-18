"""Path C — lab activation code issue + redemption.

Issue (portal, manager-authenticated): generate a 10-digit numeric code, display it
once, persist only its sha256. Redeem (``/activate-lab code:`` in a guild Mylo is
already in): lockout-guarded, single-use, TTL-bound, and it binds *the guild the
command ran in* to *the lab that issued the code*.

Authority model: the manager check happens at **issue** time on the website
(``user_can_manage_lab``). Possession of the code is the authority in Discord, so the
redeemer needs no linked identity — unlike the Discord-native path we removed, this
is the website-driven flow. The Mylo-server add-on is re-checked at redemption
(defence in depth) and, crucially, *before* the code is consumed, so a valid code is
never burned when the lab can't yet use it.

Code policy: 10 numeric digits (~33 bits) shown grouped ``XXXXX-XXXXX``. Lower entropy
than the Path B identity code is acceptable here: a guessed code only binds a *guild*
(reversible, conflict-guarded, add-on-gated), not a user's account, and redemption is
lockout-guarded (shared with Path B, keyed on the redeemer's snowflake) over a short
TTL. Only the sha256 is stored; the plaintext is never persisted or logged.
"""

from __future__ import annotations

import enum
import hashlib
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from apps.billing.entitlements import Feature, lab_has_feature

from . import resolve, state
from .resolve import LabConsumeOutcome

_ALPHABET = "0123456789"
_LENGTH = 10


def generate_plaintext() -> str:
    """A fresh 10-digit code as raw chars. Display grouped; store the hash."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))


def format_for_display(plaintext: str) -> str:
    p = normalize(plaintext)
    return f"{p[:5]}-{p[5:]}" if len(p) == _LENGTH else p


def normalize(code_input: str) -> str:
    """Keep only digits; dashes/whitespace are cosmetic. Lookup is by hash."""
    return "".join(ch for ch in (code_input or "") if ch in _ALPHABET)


def hash_code(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def issue_code(user, lab) -> str:
    """Create a code for ``lab`` (superseding any prior live one); return plaintext.

    The caller is responsible for the ``user_can_manage_lab`` authority check.
    """
    plaintext = generate_plaintext()
    expires_at = timezone.now() + timezone.timedelta(
        seconds=settings.DISCORD_ACTIVATION_TTL_SECONDS
    )
    resolve.store_lab_activation_code(lab, user, hash_code(plaintext), expires_at)
    return format_for_display(plaintext)


class RedeemOutcome(enum.StrEnum):
    OK = "ok"
    LOCKED_OUT = "locked_out"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    ALREADY_USED = "already_used"
    CONFLICT = "conflict"
    BOT_SERVER_REQUIRED = "bot_server_required"


@dataclass
class RedeemResult:
    outcome: RedeemOutcome
    lab_name: str = ""


_CONSUME_MAP = {
    LabConsumeOutcome.NOT_FOUND: RedeemOutcome.NOT_FOUND,
    LabConsumeOutcome.EXPIRED: RedeemOutcome.EXPIRED,
    LabConsumeOutcome.ALREADY_USED: RedeemOutcome.ALREADY_USED,
    LabConsumeOutcome.CONFLICT: RedeemOutcome.CONFLICT,
}


def redeem(
    code_input: str, discord_user_id: str, guild_id: str, guild_name: str = ""
) -> RedeemResult:
    """Redeem a lab code for a guild. Lockout-guarded; add-on-gated before consume."""
    discord_user_id = str(discord_user_id)
    if state.is_locked_out(discord_user_id):
        return RedeemResult(RedeemOutcome.LOCKED_OUT)

    code_hash = hash_code(normalize(code_input))

    # Peek before consuming so the add-on gate can't burn a valid code.
    peek_outcome, lab = resolve.find_live_lab_code(code_hash)
    if peek_outcome is not LabConsumeOutcome.OK:
        state.record_failure(discord_user_id)  # bad/expired/used → counts to lockout
        return RedeemResult(_CONSUME_MAP[peek_outcome])

    if not lab_has_feature(lab, Feature.BOT_SERVER):
        # Not consumed: add the add-on, then reuse the same code.
        return RedeemResult(RedeemOutcome.BOT_SERVER_REQUIRED, lab_name=lab.name)

    result = resolve.consume_lab_activation_code(
        code_hash, discord_user_id, guild_id, guild_name
    )
    if result.outcome is LabConsumeOutcome.OK:
        state.clear_failures(discord_user_id)
        name = result.lab.name if result.lab else lab.name
        return RedeemResult(RedeemOutcome.OK, lab_name=name)

    if result.outcome is LabConsumeOutcome.CONFLICT:
        # A real code, wrong guild binding — not a brute-force attempt; don't lock out.
        name = result.lab.name if result.lab else lab.name
        return RedeemResult(RedeemOutcome.CONFLICT, lab_name=name)

    # Lost a race (consumed between peek and consume) — classify, count as a failure.
    state.record_failure(discord_user_id)
    return RedeemResult(_CONSUME_MAP[result.outcome])

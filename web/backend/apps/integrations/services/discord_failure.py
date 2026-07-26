"""One place decides whether a Discord failure is worth trying again.

Before this module the judgment was spread across the call sites that happened to
need it — ``probe.run_probe`` branched on 429/5xx/403+50007, ``reminders_discord``
special-cased a bare 403, and everything else treated "not 2xx" as one undifferentiated
failure. That is exactly the shape that lets a permanently-blocked DM burn retries
forever while a transient 503 quietly retires a reminder for good.

The split that matters:

**Temporary** — retry. Rate limiting (honour Discord's own ``retry_after`` rather than
guessing), server-side errors, and transport failures with no HTTP status at all.

**Permanent** — stop, and record *why*. The user blocked the bot or closed their DMs,
the channel is gone, the bot was removed from the guild, or an overwrite denies posting.
Retrying these burns rate limit and accomplishes nothing; each one is also a fact the
portal should surface (Workstream E), which is why ``reason`` is a stable vocabulary
rather than a log string.

Pure: no model import, no I/O, no Django. That keeps it inside the
``apps/integrations/services/*.py`` boundary the AST test guards, and makes every row
of the table below testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Discord JSON error codes. Only the ones whose meaning we act on.
# https://discord.com/developers/docs/topics/opcodes-and-status-codes
UNKNOWN_CHANNEL = 10003
UNKNOWN_GUILD = 10004
MISSING_ACCESS = 50001
MISSING_PERMISSIONS = 50013
CANNOT_SEND_TO_USER = 50007


class Verdict(StrEnum):
    OK = "ok"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class Reason(StrEnum):
    """Why a send settled the way it did. Stable enough to persist and display."""

    NONE = ""
    RATE_LIMITED = "rate_limited"
    UPSTREAM = "upstream"  # Discord 5xx
    NETWORK = "network"  # no HTTP status at all — DNS, timeout, connection
    DM_BLOCKED = "dm_blocked"  # user blocked the bot or closed DMs
    NO_PERMISSION = "no_permission"  # an overwrite denies posting here
    NO_ACCESS = "no_access"  # not in the guild, or cannot see the channel
    CHANNEL_GONE = "channel_gone"
    GUILD_GONE = "guild_gone"
    NOT_CONFIGURED = "not_configured"  # no bot token on the Mycelium side
    ATTACHMENT_GONE = "attachment_gone"  # the rendered file vanished before sending
    REJECTED = "rejected"  # some other 4xx — malformed payload, too large, …


@dataclass(frozen=True)
class Classification:
    verdict: Verdict
    reason: Reason = Reason.NONE
    retry_after: float | None = None
    error_code: int | None = None

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.OK

    @property
    def should_retry(self) -> bool:
        return self.verdict is Verdict.TRANSIENT


def classify(
    *,
    status: int,
    error_code: int | None = None,
    retry_after: float | None = None,
) -> Classification:
    """Judge one Discord response.

    ``status == 0`` is this codebase's marker for a transport failure that never got
    an HTTP status — ``discord_api._request`` raises ``DiscordHTTPError(0, …)`` on
    DNS/timeout/connection errors. It is **transient**: the message never reached
    Discord, so retrying is both safe and correct.
    """
    if status in (200, 201, 204):
        return Classification(Verdict.OK)

    if status == 0:
        return Classification(Verdict.TRANSIENT, Reason.NETWORK)

    if status == 429:
        return Classification(
            Verdict.TRANSIENT, Reason.RATE_LIMITED, retry_after=retry_after
        )

    if status >= 500:
        return Classification(
            Verdict.TRANSIENT, Reason.UPSTREAM, error_code=error_code
        )

    reason = _permanent_reason(status, error_code)
    return Classification(Verdict.PERMANENT, reason, error_code=error_code)


def _permanent_reason(status: int, error_code: int | None) -> Reason:
    """Map a 4xx onto the vocabulary the portal explains to a human.

    The JSON error code is far more informative than the status: a 403 alone cannot
    distinguish "this person closed their DMs" (their choice, tell them) from "an
    overwrite denies me Send Messages here" (the lab's channel config, tell the
    manager). Fall back to the status only when Discord sent no code.
    """
    by_code = {
        CANNOT_SEND_TO_USER: Reason.DM_BLOCKED,
        MISSING_PERMISSIONS: Reason.NO_PERMISSION,
        MISSING_ACCESS: Reason.NO_ACCESS,
        UNKNOWN_CHANNEL: Reason.CHANNEL_GONE,
        UNKNOWN_GUILD: Reason.GUILD_GONE,
    }
    if error_code in by_code:
        return by_code[error_code]

    if status == 404:
        return Reason.CHANNEL_GONE
    if status == 403:
        # A 403 with no code: we cannot tell blocked-DM from denied-channel apart,
        # so report the less accusatory of the two rather than guess at the user.
        return Reason.NO_ACCESS
    return Reason.REJECTED


def classify_exception(exc) -> Classification:
    """Classify a raised :class:`~.discord_api.DiscordHTTPError`.

    ``discord_api`` has two error surfaces on purpose: send calls return a
    ``RawResponse``, while token/identity calls raise. This keeps both reaching the
    same judgment. A missing bot token surfaces as ``status == 0`` with a body rather
    than a network error, and is **permanent** — no amount of retrying configures a
    token.
    """
    status = getattr(exc, "status", 0) or 0
    body = getattr(exc, "body", "") or ""
    if status == 0 and "token not configured" in body:
        return Classification(Verdict.PERMANENT, Reason.NOT_CONFIGURED)
    return classify(status=status, error_code=getattr(exc, "code", None))

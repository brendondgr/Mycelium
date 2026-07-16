"""DM reachability probe — link validation, not delivery.

It answers one question: "is this link real and usable?" It opens a DM channel to
the linked user and posts a single fixed sentence. It carries no product content.
Outcomes follow the plan §5 table:

    200        → dm_ok=True,  cache dm_channel_id
    403 / 50007→ dm_ok=False, state stays ACTIVE (the user can still be linked)
    429        → honour retry_after, requeue, do NOT flip state (transient)
    5xx / net  → backoff; after retries the caller sets dm_ok=None + alerts

Reachability is *measured*, never inferred. Uses the bot token, not the user bearer
(a bot cannot DM someone it shares no server with unless they user-installed the app
with applications.commands — which Path A grants and Path B does not; hence Path B's
higher expected block rate).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import discord_api, resolve

_PROBE_TEXT = "Linked to Mycelium. Nothing to see yet."


@dataclass
class ProbeResult:
    dm_ok: bool | None
    channel_id: str = ""
    error_code: int | None = None
    retry_after: float | None = None
    transient: bool = False  # True → the caller should retry, state unchanged


def run_probe(identity) -> ProbeResult:
    """Perform one probe attempt and persist terminal outcomes.

    Returns a ProbeResult. On a transient outcome (429/5xx/network) nothing is
    persisted and ``transient`` is True so the task layer can requeue.
    """
    try:
        opened = discord_api.open_dm_raw(identity.discord_user_id)
    except discord_api.DiscordHTTPError:
        return ProbeResult(dm_ok=None, transient=True)

    if opened.status == 429:
        return ProbeResult(dm_ok=None, retry_after=opened.retry_after, transient=True)
    if opened.status >= 500 or opened.status == 0:
        return ProbeResult(dm_ok=None, transient=True)
    if opened.status not in (200, 201):
        # e.g. 403 opening the channel — blocked/unreachable.
        code = discord_api._err_code(opened.json)
        resolve.set_identity_dm(identity, dm_ok=False, error_code=code)
        return ProbeResult(dm_ok=False, error_code=code)

    channel_id = str(opened.json.get("id") or "")
    try:
        sent = discord_api.create_message(channel_id, content=_PROBE_TEXT)
    except discord_api.DiscordHTTPError:
        return ProbeResult(dm_ok=None, channel_id=channel_id, transient=True)

    if sent.status in (200, 201):
        resolve.set_identity_dm(identity, dm_ok=True, dm_channel_id=channel_id)
        return ProbeResult(dm_ok=True, channel_id=channel_id)
    if sent.status == 429:
        return ProbeResult(dm_ok=None, retry_after=sent.retry_after, transient=True)
    if sent.status >= 500:
        return ProbeResult(dm_ok=None, transient=True)
    # 403 + 50007 ("cannot send messages to this user") or similar → blocked.
    code = discord_api._err_code(sent.json)
    resolve.set_identity_dm(
        identity, dm_ok=False, dm_channel_id=channel_id, error_code=code
    )
    return ProbeResult(dm_ok=False, channel_id=channel_id, error_code=code)


def mark_unknown(identity) -> None:
    """Give up after exhausting retries: reachability is unknown."""
    resolve.set_identity_dm(identity, dm_ok=None)

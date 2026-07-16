"""Discord delivery for reminders — the single shared send path (R3 personal DM).

Everything Discord-side goes through the integrations boundary: identity resolution
via :mod:`apps.integrations.services.resolve` (ACTIVE identities only), and the REST
call via :mod:`apps.integrations.services.discord_api` (which forces
``allowed_mentions.parse == []``). This module imports **no integration model**.

One place owns two safety rules so tests can assert them once:

* ``parse: []`` on every outbound message — a scraped title containing ``@everyone``
  can never ping the server (enforced in ``discord_api.create_message``).
* ``escape_mentions`` neutralizes any ``@`` in interpolated scraped text, so it can't
  even render as a mention token — defense in depth on top of ``parse: []``.

Personal reminders DM the person (no pings needed). Lab-channel delivery (R5) will
add ``send_channel`` here, reusing the same guarantees and building the explicit
``users`` mention list from resolved member ids.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.integrations.services import discord_api, resolve
from apps.integrations.services.discord_api import DiscordHTTPError

# Mycelium green, for the embed accent.
BRAND_COLOR = 0x3B7A57
_TITLE_MAX = 240
_ZWSP = "​"


@dataclass
class SendOutcome:
    """Result of one outbound send."""

    ok: bool
    message_id: str = ""
    error_code: int | None = None
    unreachable: bool = False


def escape_mentions(text: str) -> str:
    """Neutralize ``@`` so scraped text cannot form a mention token.

    Inserts a zero-width space after each ``@`` — ``@everyone`` renders literally and
    is not a ping. Applied only to scraped title/label text, never to the ``<@id>``
    markup this module builds itself.
    """
    return (text or "").replace("@", "@" + _ZWSP)


def reminder_embed(title: str, body: str, url: str = "") -> dict:
    """Build the embed for a reminder message. Title/body are escaped."""
    embed: dict = {
        "title": escape_mentions(title)[:_TITLE_MAX] or "Deadline reminder",
        "description": escape_mentions(body),
        "color": BRAND_COLOR,
    }
    if url:
        embed["url"] = url
    return embed


def _bot_configured() -> bool:
    return bool(getattr(settings, "DISCORD_BOT_TOKEN", ""))


def send_personal_dm(subscription, title: str, body: str) -> SendOutcome:
    """DM the subscription's target user; returns the outcome (never raises).

    Falls back to "unreachable" when the user has no ACTIVE identity, the DM is
    known-blocked, or the bot token is unconfigured — the caller still delivers
    in-app, so a failed DM only means the bell carries the reminder alone.
    """
    if not _bot_configured():
        return SendOutcome(ok=False, unreachable=True)

    identity = resolve.active_identity_for_user(subscription.target_user)
    if identity is None or identity.dm_ok is False:
        return SendOutcome(ok=False, unreachable=True)

    try:
        channel_id = identity.dm_channel_id or _open_dm(identity)
        if not channel_id:
            return SendOutcome(ok=False, unreachable=True)
        resp = discord_api.create_message(
            channel_id, embed=reminder_embed(title, body, subscription.url)
        )
    except DiscordHTTPError as exc:
        return SendOutcome(ok=False, error_code=exc.code)

    if resp.status in (200, 201):
        return SendOutcome(ok=True, message_id=str(resp.json.get("id") or ""))
    if resp.status == 403:
        # DM closed since we last checked — record it so we stop trying.
        resolve.set_identity_dm(identity, dm_ok=False, error_code=_code(resp))
        return SendOutcome(ok=False, error_code=_code(resp), unreachable=True)
    return SendOutcome(ok=False, error_code=_code(resp))


def _open_dm(identity) -> str:
    """Open (and cache) the DM channel for an identity; '' if it can't be opened."""
    opened = discord_api.open_dm_raw(identity.discord_user_id)
    if opened.status not in (200, 201):
        if opened.status == 403:
            resolve.set_identity_dm(identity, dm_ok=False, error_code=_code(opened))
        return ""
    channel_id = str(opened.json.get("id") or "")
    if channel_id:
        resolve.set_identity_dm(identity, dm_ok=True, dm_channel_id=channel_id)
    return channel_id


def _code(resp) -> int | None:
    code = resp.json.get("code") if isinstance(resp.json, dict) else None
    return int(code) if isinstance(code, int) else None

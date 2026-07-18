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
    has_unlinked: bool | None = None  # lab sends: any mention target with no ping


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


def send_lab_channel(subscription, title: str, body: str) -> SendOutcome:
    """Post a lab reminder to its channel with resolved member pings (R5).

    Channel = the per-reminder ``channel_id_override`` if set, else the lab's default
    ``announcement_channel_id``. Mention targets with an ACTIVE Discord identity are
    pinged via ``<@id>`` (with ``allowed_mentions.users`` so the ping resolves); those
    without are rendered as plain escaped names — **never dropped**, and the outcome
    flags that the subscription has unlinked targets so the portal can prompt them.
    ``parse: []`` still holds, so the scraped title can never ``@everyone``.
    """
    user_ids, plain_names = _resolve_mentions(subscription)
    has_unlinked = bool(plain_names)

    if not _bot_configured():
        return SendOutcome(ok=False, unreachable=True, has_unlinked=has_unlinked)
    channel_id = subscription.channel_id_override or _lab_default_channel(subscription)
    if not channel_id:
        return SendOutcome(ok=False, unreachable=True, has_unlinked=has_unlinked)

    content = _mention_line(user_ids, plain_names)
    try:
        resp = discord_api.create_message(
            channel_id,
            content=content,
            embed=reminder_embed(title, body, subscription.url),
            allowed_mentions={"users": user_ids},
        )
    except DiscordHTTPError as exc:
        return SendOutcome(
            ok=False, error_code=exc.code, has_unlinked=has_unlinked
        )

    if resp.status in (200, 201):
        return SendOutcome(
            ok=True,
            message_id=str(resp.json.get("id") or ""),
            has_unlinked=has_unlinked,
        )
    if resp.status == 403:
        return SendOutcome(
            ok=False,
            error_code=_code(resp),
            unreachable=True,
            has_unlinked=has_unlinked,
        )
    return SendOutcome(ok=False, error_code=_code(resp), has_unlinked=has_unlinked)


def _lab_default_channel(subscription) -> str:
    return resolve.get_announcement_channel_for_lab(subscription.target_lab)


def _resolve_mentions(subscription) -> tuple[list[str], list[str]]:
    """(active discord ids, plain display names) for the subscription's mentions."""
    members = [m.member for m in subscription.mentions.select_related("member").all()]
    active = resolve.active_discord_ids_for_users(members)
    user_ids: list[str] = []
    plain: list[str] = []
    for member in members:
        discord_id = active.get(member.id)
        if discord_id:
            user_ids.append(discord_id)
        else:
            plain.append(member.get_full_name() or member.get_username())
    return user_ids, plain


def _mention_line(user_ids: list[str], plain_names: list[str]) -> str:
    parts = [f"<@{uid}>" for uid in user_ids]
    parts += [escape_mentions(name) for name in plain_names]
    return " ".join(parts)


# Postable guild channel types: GUILD_TEXT (0) and GUILD_ANNOUNCEMENT (5).
_POSTABLE_CHANNEL_TYPES = (0, 5)


def list_postable_channels(guild_id: str) -> list[dict]:
    """Text/announcement channels in a guild, for the reminder channel picker.

    Filters by type only; the authoritative "can the bot actually post here" check is
    the post-a-confirmation preflight (``preflight_channel``), because the gateway
    architecture has no ``app_permissions`` payload to read channel overwrites from —
    so we prove postability by posting, per the plan's "fail in front of the admin".
    """
    channels = discord_api.get_guild_channels(guild_id)
    return [
        {"id": str(c.get("id")), "name": c.get("name") or "", "type": c.get("type")}
        for c in channels
        if c.get("type") in _POSTABLE_CHANNEL_TYPES
    ]


def preflight_channel(
    channel_id: str, *, purpose: str = "deadline reminders"
) -> SendOutcome:
    """Verify a channel by posting a visible confirmation (the real proof).

    2xx → the bot has VIEW + SEND + EMBED here (Discord computed the overwrites for
    us); 403 → an overwrite denies posting, so the bind must be refused with a
    specific error rather than failing silently at 09:00 on the day it mattered.

    ``purpose`` names what the channel is being bound for (e.g. "deadline reminders",
    "daily and weekly updates") so the confirmation reads correctly for each kind.
    """
    if not _bot_configured():
        return SendOutcome(ok=False, unreachable=True)
    embed = {
        "title": "Mylo is set up here ✅",
        "description": f"This channel will receive this lab's {purpose}.",
        "color": BRAND_COLOR,
    }
    try:
        resp = discord_api.create_message(channel_id, embed=embed)
    except DiscordHTTPError as exc:
        return SendOutcome(ok=False, error_code=exc.code)
    if resp.status in (200, 201):
        return SendOutcome(ok=True, message_id=str(resp.json.get("id") or ""))
    if resp.status == 403:
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

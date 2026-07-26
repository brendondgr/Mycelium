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

from apps.integrations.services import discord_api, outbox, resolve
from apps.integrations.services.discord_api import DiscordHTTPError

# Mycelium green, for the embed accent.
BRAND_COLOR = 0x3B7A57
_TITLE_MAX = 240
_ZWSP = "​"


@dataclass
class SendOutcome:
    """Result of one outbound send.

    Product messages are now *queued*, so ``ok`` means "accepted for delivery", not
    "Discord has it" — ``queued`` says which. ``message_id`` stays empty for queued
    sends; the delivery record lives on the outbox row named by ``outbox_key``.
    The diagnostic senders (``preflight_channel``) still fill ``ok``/``message_id``
    synchronously, because their whole point is an immediate verdict.
    """

    ok: bool
    message_id: str = ""
    error_code: int | None = None
    unreachable: bool = False
    not_configured: bool = False  # server-side: the bot token isn't set at all
    has_unlinked: bool | None = None  # lab sends: any mention target with no ping
    queued: bool = False
    outbox_key: str = ""


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


def send_personal_dm(
    subscription, title: str, body: str, *, dedupe_key: str = ""
) -> SendOutcome:
    """Queue a DM to the subscription's target user (never raises).

    Queued, not sent: the tick used to block on a live HTTP round-trip here and treat
    a thirty-second outage as a permanent loss. Reachability is now judged at delivery
    time by the outbox, so this only refuses the cases that are certain up front — no
    linked identity at all, or a DM we already know is blocked — where queueing would
    just manufacture a dead letter.

    The caller still delivers in-app unconditionally, so a refused DM means the bell
    carries the reminder alone.
    """
    if not _bot_configured():
        return SendOutcome(ok=False, unreachable=True, not_configured=True)

    identity = resolve.active_identity_for_user(subscription.target_user)
    if identity is None or identity.dm_ok is False:
        return SendOutcome(ok=False, unreachable=True)

    key = dedupe_key or f"reminder:{subscription.id}:{subscription.due_date:%Y-%m-%d}"
    outbox.enqueue_dm(
        dedupe_key=key,
        kind="reminder",
        user=subscription.target_user,
        embed=reminder_embed(title, body, subscription.url),
        subject_type="reminder_subscription",
        subject_id=str(subscription.id),
    )
    return SendOutcome(ok=True, queued=True, outbox_key=key)


def send_personal_report(
    user,
    *,
    title: str,
    body: str,
    filename: str,
    attachment_path: str,
    dedupe_key: str,
    url: str = "",
) -> SendOutcome:
    """Queue a user's daily "Mylo Report" PDF as a DM attachment (never raises).

    Takes a *path*, not bytes: the report is 0.2–2 MB, and the whole point of queueing
    is that delivery can happen minutes after the batch that rendered it. Whoever
    writes the file owns it until the outbox settles the row; the retention sweep
    removes it afterwards.

    "Unreachable" (no active identity, blocked DM, no bot token) is a soft outcome —
    the caller counts the skip rather than manufacturing a dead letter.
    """
    if not _bot_configured():
        return SendOutcome(ok=False, unreachable=True, not_configured=True)

    identity = resolve.active_identity_for_user(user)
    if identity is None or identity.dm_ok is False:
        return SendOutcome(ok=False, unreachable=True)

    outbox.enqueue_dm(
        dedupe_key=dedupe_key,
        kind="daily_report",
        user=user,
        embed=reminder_embed(title, body, url),
        attachment_path=attachment_path,
        attachment_filename=filename,
        subject_type="daily_report",
        subject_id=str(user.id),
    )
    return SendOutcome(ok=True, queued=True, outbox_key=dedupe_key)


def send_lab_channel(
    subscription, title: str, body: str, *, dedupe_key: str = ""
) -> SendOutcome:
    """Queue a lab reminder to its channel with resolved member pings (R5).

    Channel = the per-reminder ``channel_id_override`` if set, else the lab's default
    ``announcement_channel_id``. Mention targets with an ACTIVE Discord identity are
    pinged via ``<@id>`` (with ``allowed_mentions.users`` so the ping resolves); those
    without are rendered as plain escaped names — **never dropped**, and the outcome
    flags that the subscription has unlinked targets so the portal can prompt them.
    ``parse: []`` still holds, so the scraped title can never ``@everyone``.

    Mentions are resolved *now* rather than at delivery: who was meant to be tagged is
    part of what this reminder said, and should not silently change because someone
    linked their account in the twenty minutes a retry took.
    """
    user_ids, plain_names = _resolve_mentions(subscription)
    has_unlinked = bool(plain_names)

    if not _bot_configured():
        return SendOutcome(
            ok=False,
            unreachable=True,
            not_configured=True,
            has_unlinked=has_unlinked,
        )
    channel_id = subscription.channel_id_override or _lab_default_channel(subscription)
    if not channel_id:
        return SendOutcome(ok=False, unreachable=True, has_unlinked=has_unlinked)

    key = dedupe_key or f"reminder:{subscription.id}:{subscription.due_date:%Y-%m-%d}"
    outbox.enqueue_channel(
        dedupe_key=key,
        kind="reminder",
        channel_id=channel_id,
        lab=subscription.target_lab,
        content=_mention_line(user_ids, plain_names),
        embed=reminder_embed(title, body, subscription.url),
        allowed_mentions={"users": user_ids},
        subject_type="reminder_subscription",
        subject_id=str(subscription.id),
    )
    return SendOutcome(
        ok=True, queued=True, outbox_key=key, has_unlinked=has_unlinked
    )


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
        # No token: we never reach Discord at all. Flag it distinctly so the caller
        # doesn't misreport a server-side gap as the channel's own permissions.
        return SendOutcome(ok=False, unreachable=True, not_configured=True)
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

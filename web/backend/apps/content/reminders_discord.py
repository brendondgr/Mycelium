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

from dataclasses import dataclass, field

from django.conf import settings

from apps.content.reminder_access import (
    lab_plan_allows_reminders,
    user_plan_allows_reminders,
)
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
    not_entitled: bool = False  # the recipient's plan no longer covers reminders
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

    Entitlement is re-checked at *send* time, not trusted from create time: a plan
    can lapse or a seat be revoked in the weeks between subscribing and the first
    offset firing, and Discord delivery is the paid half of this feature. We never
    delete the subscription over a billing event — it simply stops being DMed.
    """
    if not _bot_configured():
        return SendOutcome(ok=False, unreachable=True, not_configured=True)

    if not user_plan_allows_reminders(subscription.target_user):
        return SendOutcome(ok=False, unreachable=True, not_entitled=True)

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
    embed: dict | None = None,
    kind: str = "daily_report",
    not_before=None,
) -> SendOutcome:
    """Queue a user's daily "Mylo Report" PDF as a DM attachment (never raises).

    Takes a *path*, not bytes: the report is 0.2–2 MB, and the whole point of queueing
    is that delivery can happen minutes after the batch that rendered it. Whoever
    writes the file owns it until the outbox settles the row; the retention sweep
    removes it afterwards.

    "Unreachable" (no active identity, blocked DM, no bot token) is a soft outcome —
    the caller counts the skip rather than manufacturing a dead letter.

    ``not_before`` holds the row until the recipient's local send hour; ``kind``
    separates a daily from a weekly in the outbox and the analytics; ``embed``
    passes a prebuilt embed through instead of the plain title/body one.
    """
    if not _bot_configured():
        return SendOutcome(ok=False, unreachable=True, not_configured=True)

    identity = resolve.active_identity_for_user(user)
    if identity is None or identity.dm_ok is False:
        return SendOutcome(ok=False, unreachable=True)

    outbox.enqueue_dm(
        dedupe_key=dedupe_key,
        kind=kind,
        user=user,
        # A prebuilt ``embed`` is the overview-and-statistics post (plan 1.3); the
        # title/body pair is the plain reminder shape, kept for callers that have
        # nothing richer to say and for the deterministic fallback.
        embed=embed if embed is not None else reminder_embed(title, body, url),
        attachment_path=attachment_path,
        attachment_filename=filename,
        subject_type=kind,
        subject_id=str(user.id),
        not_before=not_before,
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
    targets = _resolve_mentions(subscription)
    has_unlinked = bool(targets.plain_names)

    if not _bot_configured():
        return SendOutcome(
            ok=False,
            unreachable=True,
            not_configured=True,
            has_unlinked=has_unlinked,
        )
    # Same lapse guard as the personal path: a lab whose plan ended keeps its
    # reminders and its in-app notifications, but stops posting to Discord.
    if not lab_plan_allows_reminders(subscription.target_lab):
        return SendOutcome(
            ok=False,
            unreachable=True,
            not_entitled=True,
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
        content=targets.line(),
        embed=reminder_embed(title, body, subscription.url),
        allowed_mentions=targets.allowed_mentions(),
        subject_type="reminder_subscription",
        subject_id=str(subscription.id),
    )
    return SendOutcome(
        ok=True, queued=True, outbox_key=key, has_unlinked=has_unlinked
    )


def _lab_default_channel(subscription) -> str:
    return resolve.get_announcement_channel_for_lab(subscription.target_lab)


@dataclass
class MentionTargets:
    """Who one lab alert pings, resolved to what Discord actually needs.

    ``plain_names`` are targets that could not be turned into a ping — a
    Mycelium member who has not linked Discord. They are still *named* in the
    message rather than dropped: the person meant to be told is part of what the
    alert said, and silently omitting them would make the message quietly wrong.
    """

    user_ids: list[str] = field(default_factory=list)
    role_ids: list[str] = field(default_factory=list)
    everyone: bool = False
    plain_names: list[str] = field(default_factory=list)

    def allowed_mentions(self) -> dict:
        return {
            "users": self.user_ids,
            "roles": self.role_ids,
            "everyone": self.everyone,
        }

    def line(self) -> str:
        parts: list[str] = []
        if self.everyone:
            # Written by this module, never interpolated from scraped text, and
            # it only resolves because ``allowed_mentions`` says so above.
            parts.append("@everyone")
        parts += [f"<@&{rid}>" for rid in self.role_ids]
        parts += [f"<@{uid}>" for uid in self.user_ids]
        parts += [escape_mentions(name) for name in self.plain_names]
        return " ".join(parts)


def _resolve_mentions(subscription) -> MentionTargets:
    """Turn the subscription's mention rows into ping targets.

    Three kinds, resolved differently. A **role** or a raw-id **user** target is
    already a snowflake in the lab's own guild (validated when it was stored) and
    needs no lookup. A **Mycelium member** target needs their linked Discord
    identity, which may not exist — that is the ``plain_names`` case and the
    thing ``has_unlinked_targets`` reports to the portal. **@everyone** has no id
    by nature and is carried as a flag.
    """
    targets = MentionTargets()
    rows = list(subscription.mentions.select_related("member").all())
    members = [row.member for row in rows if row.member_id is not None]
    active = resolve.active_discord_ids_for_users(members) if members else {}

    for row in rows:
        # Compared as plain strings, not against ``ReminderMention.Kind``: this
        # module is on the Discord path, which the import-graph test holds to
        # reaching the ORM only through ``resolve.py``. The values are a stable
        # part of the model's public shape, so naming them here costs nothing
        # and importing the model to spell them would break a real boundary.
        if row.kind == "everyone":
            targets.everyone = True
        elif row.kind == "role":
            if row.discord_id:
                targets.role_ids.append(str(row.discord_id))
        elif row.member_id is not None:
            discord_id = active.get(row.member_id)
            if discord_id:
                targets.user_ids.append(str(discord_id))
            else:
                targets.plain_names.append(row.label)
        elif row.discord_id:
            targets.user_ids.append(str(row.discord_id))
    return targets


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


def list_guild_roles(guild_id: str) -> list[dict]:
    """Mentionable roles in a guild, for the alert mention picker.

    ``@everyone`` is excluded: Discord models it as a role whose id equals the
    guild id, but it is not pingable as a role mention — it is a parse category
    — and the picker offers it as its own explicit choice instead. Managed roles
    (the ones bots and integrations own, ``managed: true``) are excluded too:
    they cannot be assigned to people, so pinging one reaches nobody.
    """
    roles = discord_api.get_guild_roles(guild_id)
    return sorted(
        (
            {"id": str(r.get("id")), "name": r.get("name") or ""}
            for r in roles
            if str(r.get("id")) != str(guild_id) and not r.get("managed")
        ),
        key=lambda r: r["name"].lower(),
    )


def list_guild_members(guild_id: str) -> list[dict]:
    """Members of a guild, for the alert mention picker.

    Bots are excluded — pinging one does nothing a human would notice. The
    display name prefers the server nickname, because that is who the lab knows
    the person as, and falls back to the account's global or user name.
    """
    members = discord_api.get_guild_members(guild_id)
    out = []
    for entry in members:
        user = entry.get("user") or {}
        if user.get("bot"):
            continue
        name = (
            entry.get("nick")
            or user.get("global_name")
            or user.get("username")
            or ""
        )
        if user.get("id"):
            out.append({"id": str(user["id"]), "name": name})
    return sorted(out, key=lambda m: m["name"].lower())


def preflight_channel(
    channel_id: str, *, purpose: str = "deadline reminders", owner: str = "lab"
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
        "description": f"This channel will receive this {owner}'s {purpose}.",
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

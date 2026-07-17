"""Async linking operations the gateway cogs call.

Each public coroutine returns a plain ``(status, message)`` — the cog just relays
the (always ephemeral) message. All ORM access is via ``resolve`` inside a
``mycelium.db`` call; this module imports no Django model at import time.

``/activate`` is context-aware and does both linking jobs:

* ``code:`` → **Path B identity linking** (redeem a one-time code to bind the
  caller's own Discord account). Gated to the hub activation channel.
* ``lab:``  → **server activation** (bind *this guild* to a lab the caller
  administers), so Mylo can post that lab's reminders/announcements here.

``/mylo setup`` is the *after-link* step: it only chooses where reminders post,
and requires the server to already be activated (``/activate lab:`` first).
"""

from __future__ import annotations

from . import mycelium


async def status(discord_user_id: str) -> tuple[str, str]:
    return await mycelium.db(_status_sync, str(discord_user_id))


async def activate(
    discord_user_id: str,
    *,
    code: str | None = None,
    lab_slug: str | None = None,
    guild_id: str = "",
    guild_name: str = "",
    channel_id: str = "",
) -> tuple[str, str]:
    """Context-aware ``/activate`` dispatch.

    * ``code`` and ``lab`` together → rejected (one job at a time).
    * ``code`` → Path B identity redemption (activation-channel gated).
    * ``lab`` → bind this guild to that lab (manager-gated, add-on gated).
    * neither → context help (link first / pick a lab / confirm a pending install).
    """
    code = (code or "").strip()
    lab_slug = (lab_slug or "").strip()

    if code and lab_slug:
        return (
            "ambiguous",
            "Do one at a time: `/activate code:<code>` links your account, "
            "`/activate lab:<name>` connects this server.",
        )

    if code:
        # Channel gate first — no code lookup at all outside the activation channel.
        expected = await mycelium.db(_activation_channel)
        if expected and str(channel_id) != expected:
            return (
                "wrong_channel",
                f"Run `/activate code:` in <#{expected}>. Nothing was looked up.",
            )
        return await mycelium.db(_activate_code_sync, str(discord_user_id), code)

    if not guild_id:
        return ("no_guild", "Run `/activate` inside a server, not in a DM.")

    if lab_slug:
        return await mycelium.db(
            _activate_lab_sync,
            str(discord_user_id),
            str(guild_id),
            str(guild_name),
            lab_slug,
        )

    return await mycelium.db(
        _activate_help_sync, str(discord_user_id), str(guild_id), str(guild_name)
    )


async def setup_channel(
    discord_user_id: str, guild_id: str, *, channel_id: str = ""
) -> tuple[str, str]:
    """``/mylo setup`` — choose where this activated server's reminders post."""
    if not guild_id:
        return ("no_guild", "Run `/mylo setup` inside a server, not in a DM.")
    return await mycelium.db(
        _setup_channel_sync, str(discord_user_id), str(guild_id), str(channel_id)
    )


async def managed_lab_choices(
    discord_user_id: str, current: str
) -> list[tuple[str, str]]:
    """(name, slug) pairs for the `/activate lab:` autocomplete."""
    return await mycelium.db(
        _managed_lab_choices_sync, str(discord_user_id), current or ""
    )


# --------------------------------------------------------------------------- #
# Synchronous bodies (run in a worker thread with Django configured)
# --------------------------------------------------------------------------- #
def _activation_channel() -> str:
    return mycelium.activation_channel_id()


def _status_sync(discord_user_id: str) -> tuple[str, str]:
    from apps.integrations.services import resolve

    identity = resolve.resolve_identity(discord_user_id)
    if identity is None:
        return (
            "not_linked",
            "You're not linked to Mycelium yet. Connect your Discord from your "
            f"profile: {mycelium.portal_url()}",
        )
    reach = {True: "reachable", False: "blocked — enable DMs from server members",
             None: "not checked yet"}[identity.dm_ok]
    name = identity.username_cache or identity.discord_user_id
    return (
        "linked",
        f"✅ Linked as **{name}** (via {identity.link_method}). "
        f"DM reachability: {reach}.",
    )


def _activate_code_sync(discord_user_id: str, code: str) -> tuple[str, str]:
    from apps.integrations.services import activation

    result = activation.redeem(code, discord_user_id)
    outcome = result.outcome
    O = activation.RedeemOutcome
    if outcome is O.OK:
        reach = {True: " Your DMs are reachable.", False: " Note: I can't DM you — "
                 "enable DMs from server members.", None: ""}[result.dm_ok]
        return ("ok", f"✅ Your Discord is now linked to Mycelium.{reach}")
    messages = {
        O.LOCKED_OUT: "Too many attempts. Try again in about an hour.",
        O.NOT_FOUND: "That code isn't valid. Double-check it and try again.",
        O.EXPIRED: "That code has expired. Generate a fresh one in the portal.",
        O.ALREADY_USED: "That code has already been used.",
        O.REBIND_REJECTED: "This Discord account is already linked to a different "
        "Mycelium user.",
    }
    return (outcome.value, messages[outcome])


def _managed_lab_choices_sync(
    discord_user_id: str, current: str
) -> list[tuple[str, str]]:
    from apps.integrations.services import resolve

    cur = current.lower().strip()
    out: list[tuple[str, str]] = []
    for lab in resolve.labs_managed_by_discord_user(discord_user_id):
        if cur and cur not in lab.name.lower():
            continue
        out.append((lab.name[:100], lab.slug))
    return out[:25]


# --------------------------------------------------------------------------- #
# Server activation (`/activate lab:` and the no-arg helper)
# --------------------------------------------------------------------------- #
def _needs_bot_server(resolve, lab) -> tuple[str, str] | None:
    """BOT_SERVER is an add-on on the lab's subscription (A4), not a tier grant."""
    from apps.billing.entitlements import Feature, lab_has_feature

    if lab_has_feature(lab, Feature.BOT_SERVER):
        return None
    return (
        "bot_server_required",
        f"**{lab.name}** doesn't include Mylo for your server yet. Add the "
        f"Mylo-server add-on to this lab in Mycelium, then run `/activate lab:` "
        f"again: {mycelium.portal_url()}",
    )


def _require_linked(resolve, discord_user_id: str) -> tuple[str, str] | None:
    """Server activation needs the caller's own Discord to be linked first."""
    if resolve.resolve_identity(discord_user_id) is None:
        return (
            "link_required",
            "Link your own Discord to Mycelium first — `/activate code:<code>` "
            f"(get a code in your profile) or connect it there: {mycelium.portal_url()}",
        )
    return None


def _activation_done_message(lab_name: str) -> str:
    return (
        f"✅ This server is now connected to **{lab_name}**.\n"
        "Next: run `/mylo setup channel:#your-channel` to choose where lab "
        "deadline reminders post."
    )


def _activate_lab_sync(
    discord_user_id: str,
    guild_id: str,
    guild_name: str,
    lab_slug: str,
) -> tuple[str, str]:
    from apps.integrations.services import resolve

    blocked = _require_linked(resolve, discord_user_id)
    if blocked is not None:
        return blocked

    link = resolve.get_guild_link(guild_id)

    # Already fully connected — confirm (and note if it's a different lab).
    if link is not None and link.state == resolve.GUILD_ACTIVE:
        if link.lab.slug == lab_slug:
            return (
                "already",
                f"✅ This server is already connected to **{link.lab.name}**. "
                "Use `/mylo setup` to change the reminders channel.",
            )
        return (
            "conflict",
            f"This server is already connected to **{link.lab.name}**. Disconnect "
            "it in Mycelium before connecting a different lab.",
        )

    managed = resolve.labs_managed_by_discord_user(discord_user_id)
    chosen = next((lab for lab in managed if lab.slug == lab_slug), None)
    if chosen is None:
        return (
            "denied",
            "Pick one of the labs you administer — start typing after `lab:` to "
            "see the list. Only a lab's admin or PI can connect a server; guild "
            "ownership alone grants no authority.",
        )

    blocked = _needs_bot_server(resolve, chosen)
    if blocked is not None:
        return blocked

    # Installed via the website (PENDING, verified by code grant) — confirm it.
    if (
        link is not None
        and link.state != resolve.GUILD_KICKED
        and link.lab_id == chosen.id
        and link.verified_via_code_grant
    ):
        confirmer = resolve.resolve_user(discord_user_id)
        confirmed = resolve.confirm_guild(guild_id, confirmed_by=confirmer)
        if confirmed is not None:
            return ("ok", _activation_done_message(chosen.name))

    # Discord-native bind (or a pending link that can't be confirmed) — bind ACTIVE.
    try:
        resolve.bind_guild_via_command(discord_user_id, guild_id, guild_name, chosen)
    except resolve.GuildConflict:
        return ("conflict", "This server is already connected to a different lab.")
    return ("ok", _activation_done_message(chosen.name))


def _activate_help_sync(
    discord_user_id: str, guild_id: str, guild_name: str
) -> tuple[str, str]:
    from apps.integrations.services import resolve

    if resolve.resolve_identity(discord_user_id) is None:
        return (
            "link_required",
            "Link your Discord to Mycelium first — `/activate code:<code>` (get a "
            f"code in your profile) or connect it there: {mycelium.portal_url()}. "
            "Then run `/activate lab:<name>` to connect this server.",
        )

    link = resolve.get_guild_link(guild_id)
    if link is not None and link.state == resolve.GUILD_ACTIVE:
        return (
            "already",
            f"✅ This server is already connected to **{link.lab.name}**. "
            "Use `/mylo setup` to choose where reminders post.",
        )

    # A pending website install the caller manages — confirm it straight away.
    if (
        link is not None
        and link.state != resolve.GUILD_KICKED
        and resolve.can_manage_lab_via_discord(discord_user_id, link.lab)
    ):
        return _activate_lab_sync(
            discord_user_id, guild_id, guild_name, link.lab.slug
        )

    managed = resolve.labs_managed_by_discord_user(discord_user_id)
    if not managed:
        return (
            "no_labs",
            "You don't administer any labs in Mycelium yet. Ask a lab's PI or "
            "admin to connect this server, or set up your lab in Mycelium first.",
        )
    names = ", ".join(f"**{lab.name}**" for lab in managed[:10])
    return (
        "choose",
        f"Connect this server to a lab you administer: run `/activate lab:<name>` "
        f"({names}). You can also add Mylo from that lab's **Edit Setup** menu in "
        "Mycelium.",
    )


# --------------------------------------------------------------------------- #
# Post-link channel config (`/mylo setup`)
# --------------------------------------------------------------------------- #
def _setup_channel_sync(
    discord_user_id: str, guild_id: str, channel_id: str
) -> tuple[str, str]:
    from apps.integrations.services import resolve

    link = resolve.get_guild_link(guild_id)
    if link is None or link.state != resolve.GUILD_ACTIVE:
        return (
            "not_active",
            "This server isn't connected to a lab yet. Run `/activate lab:<name>` "
            "first (a lab admin/PI), then `/mylo setup` to choose the channel.",
        )

    if not resolve.can_manage_lab_via_discord(discord_user_id, link.lab):
        return (
            "denied",
            f"Only an admin or PI of **{link.lab.name}** can change its reminders "
            "channel.",
        )

    if not channel_id:
        current = resolve.get_announcement_channel_for_lab(link.lab)
        where = f"<#{current}>" if current else "not set yet"
        return (
            "status",
            f"This server is connected to **{link.lab.name}**. Reminders channel: "
            f"{where}.\nPass a **channel** to `/mylo setup` to change it "
            "(I verify I can post there first).",
        )

    return _bind_channel_sync(resolve, guild_id, link.lab, channel_id)


def _bind_channel_sync(resolve, guild_id: str, lab, channel_id: str):
    """Preflight (post a visible confirmation) then bind the announcement channel."""
    from django.utils import timezone

    from apps.content.reminders_discord import preflight_channel

    base = f"✅ **{lab.name}** reminders channel"
    outcome = preflight_channel(channel_id)
    if not outcome.ok:
        if outcome.unreachable:
            return (
                "channel_denied",
                f"⚠️ I can't post in <#{channel_id}> (an override denies me "
                "View/Send/Embed there). Pick a different channel, or fix my "
                "permissions and run `/mylo setup` again.",
            )
        return (
            "channel_error",
            f"⚠️ I couldn't verify <#{channel_id}> just now. Try again in a moment.",
        )
    resolve.set_announcement_channel(guild_id, channel_id, verified_at=timezone.now())
    return (
        "ok",
        f"{base}: <#{channel_id}> (I sent a confirmation there).",
    )

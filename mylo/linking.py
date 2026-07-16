"""Async linking operations the gateway cogs call.

Each public coroutine returns a plain ``(status, message)`` — the cog just relays
the (always ephemeral) message. All ORM access is via ``resolve`` inside a
``mycelium.db`` call; this module imports no Django model at import time.
"""

from __future__ import annotations

from . import mycelium


async def status(discord_user_id: str) -> tuple[str, str]:
    return await mycelium.db(_status_sync, str(discord_user_id))


async def activate(
    discord_user_id: str, code: str, *, channel_id: str
) -> tuple[str, str]:
    # Channel gate first — no code lookup at all outside the activation channel.
    expected = await mycelium.db(_activation_channel)
    if expected and str(channel_id) != expected:
        return (
            "wrong_channel",
            f"Run `/activate` in <#{expected}>. Nothing was looked up.",
        )
    return await mycelium.db(_activate_sync, str(discord_user_id), code)


async def setup_guild(
    discord_user_id: str,
    guild_id: str,
    *,
    guild_name: str = "",
    lab_slug: str | None = None,
    channel_id: str = "",
) -> tuple[str, str]:
    if not guild_id:
        return ("no_guild", "Run `/mylo setup` inside a server, not in a DM.")
    return await mycelium.db(
        _setup_sync,
        str(discord_user_id),
        str(guild_id),
        guild_name,
        lab_slug,
        str(channel_id),
    )


async def managed_lab_choices(
    discord_user_id: str, current: str
) -> list[tuple[str, str]]:
    """(name, slug) pairs for the `/mylo setup` lab autocomplete."""
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


def _activate_sync(discord_user_id: str, code: str) -> tuple[str, str]:
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


def _setup_sync(
    discord_user_id: str,
    guild_id: str,
    guild_name: str,
    lab_slug: str | None,
    channel_id: str = "",
) -> tuple[str, str]:
    from apps.billing.entitlements import Feature, lab_has_feature
    from apps.integrations.services import resolve

    def _needs_bot_server(lab) -> tuple[str, str] | None:
        # BOT_SERVER is an add-on on the lab's subscription (A4), not a tier grant.
        if lab_has_feature(lab, Feature.BOT_SERVER):
            return None
        return (
            "bot_server_required",
            f"**{lab.name}** doesn't include Mylo for your server yet. Add the "
            f"Mylo-server add-on to this lab in Mycelium, then run `/mylo setup` "
            f"again: {mycelium.portal_url()}",
        )

    # Auth: the caller must have linked their own Discord (identity = who you are).
    if resolve.resolve_identity(discord_user_id) is None:
        return (
            "link_required",
            "Link your own Discord to Mycelium first, then run `/mylo setup` again: "
            f"{mycelium.portal_url()}",
        )

    link = resolve.get_guild_link(guild_id)

    # Already fully connected — bind a channel if one was passed, else confirm.
    if link is not None and link.state == resolve.GUILD_ACTIVE:
        base = f"✅ This server is already connected to **{link.lab.name}**."
        return _finish(resolve, guild_id, base, channel_id, already=True)

    # Installed via the website (PENDING) — confirm it, if the caller manages it.
    if link is not None and link.state != resolve.GUILD_KICKED:
        lab = link.lab
        if not resolve.can_manage_lab_via_discord(discord_user_id, lab):
            return (
                "denied",
                f"This server is being connected to **{lab.name}**, but you're not "
                "a manager of that lab. Guild ownership alone grants no authority.",
            )
        blocked = _needs_bot_server(lab)
        if blocked is not None:
            return blocked
        confirmer = resolve.resolve_user(discord_user_id)
        confirmed = resolve.confirm_guild(guild_id, confirmed_by=confirmer)
        if confirmed is None:
            return (
                "unusable",
                "This pending link can't be confirmed. Run "
                "`/mylo setup lab:<name>` to connect a lab you manage instead.",
            )
        base = f"✅ This server is now connected to **{lab.name}**."
        return _finish(resolve, guild_id, base, channel_id)

    # Not bound yet (or previously kicked) — connect it to a lab the caller manages.
    managed = resolve.labs_managed_by_discord_user(discord_user_id)
    if not managed:
        return (
            "no_labs",
            "You don't manage any labs in Mycelium yet. Ask a lab's PI or admin to "
            "connect this server, or set up your lab in Mycelium first.",
        )

    if lab_slug:
        chosen = next((lab for lab in managed if lab.slug == lab_slug), None)
        if chosen is None:
            return (
                "bad_lab",
                "Pick one of the labs you manage — start typing after `lab:` to "
                "see the list.",
            )
        blocked = _needs_bot_server(chosen)
        if blocked is not None:
            return blocked
        try:
            resolve.bind_guild_via_command(
                discord_user_id, guild_id, guild_name, chosen
            )
        except resolve.GuildConflict:
            return (
                "conflict",
                "This server is already connected to a different lab.",
            )
        base = f"✅ This server is now connected to **{chosen.name}**."
        return _finish(resolve, guild_id, base, channel_id)

    # No lab chosen — show how to pick one (Discord) or point at the website.
    names = ", ".join(f"**{lab.name}**" for lab in managed[:10])
    return (
        "choose",
        f"Connect this server to a lab you manage: run `/mylo setup lab:<name>` "
        f"({names}). You can also add Mylo from that lab's **Edit Setup** menu in "
        "Mycelium.",
    )


def _finish(resolve, guild_id: str, base: str, channel_id: str, *, already=False):
    """After a successful connect/confirm, bind the reminder channel if one was
    passed (preflighting it first); otherwise nudge the manager to pick one."""
    if not channel_id:
        status = "already" if already else "ok"
        return (
            status,
            f"{base}\nTip: pass a **channel** to `/mylo setup` to choose where lab "
            "deadline reminders post.",
        )
    return _bind_channel_sync(resolve, guild_id, channel_id, base)


def _bind_channel_sync(resolve, guild_id: str, channel_id: str, base: str):
    """Preflight (post a visible confirmation) then bind the announcement channel."""
    from django.utils import timezone

    from apps.content.reminders_discord import preflight_channel

    outcome = preflight_channel(channel_id)
    if not outcome.ok:
        if outcome.unreachable:
            return (
                "channel_denied",
                f"{base}\n⚠️ I can't post in <#{channel_id}> (an override denies me "
                "View/Send/Embed there). Pick a different channel, or fix my "
                "permissions and run `/mylo setup` again.",
            )
        return (
            "channel_error",
            f"{base}\n⚠️ I couldn't verify <#{channel_id}> just now. Try again in a "
            "moment.",
        )
    resolve.set_announcement_channel(
        guild_id, channel_id, verified_at=timezone.now()
    )
    return (
        "ok",
        f"{base}\n📢 Lab deadline reminders will post to <#{channel_id}> "
        "(I sent a confirmation there).",
    )

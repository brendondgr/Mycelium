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
    discord_user_id: str, guild_id: str, *, channel_id: str = ""
) -> tuple[str, str]:
    if not guild_id:
        return ("no_guild", "Run `/mylo setup` inside a server, not in a DM.")
    return await mycelium.db(
        _setup_sync, str(discord_user_id), str(guild_id), str(channel_id)
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


def _setup_sync(
    discord_user_id: str, guild_id: str, channel_id: str = ""
) -> tuple[str, str]:
    from apps.integrations.services import resolve

    lab = resolve.resolve_lab_for_guild(guild_id)
    if lab is None:
        return (
            "no_link",
            "This server isn't linked to a Mycelium lab yet. A lab manager can add "
            f"Mylo from {mycelium.portal_url()}.",
        )
    if resolve.resolve_identity(discord_user_id) is None:
        return (
            "link_required",
            "Link your own Discord to Mycelium first, then run `/mylo setup` again: "
            f"{mycelium.portal_url()}",
        )
    if not resolve.can_manage_lab_via_discord(discord_user_id, lab):
        return (
            "denied",
            f"You're not a manager of **{lab.name}**, so you can't confirm this "
            "server. Guild ownership alone doesn't grant lab authority.",
        )
    confirmer = resolve.resolve_user(discord_user_id)
    link = resolve.confirm_guild(guild_id, confirmed_by=confirmer)
    if link is None:
        return (
            "unusable",
            "This link can't be confirmed (it wasn't verified via the code grant). "
            "Re-add Mylo from the portal.",
        )

    base = f"✅ This server is now connected to **{lab.name}**."
    if not channel_id:
        return (
            "ok",
            f"{base}\nNow choose where reminders post: run `/mylo setup` again and "
            "pick a channel in the **channel** option.",
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

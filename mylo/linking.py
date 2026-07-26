"""Async linking operations the gateway cogs call.

Each public coroutine returns a plain ``(status, message)`` or ``(status, payload)``
— the cog relays it (always ephemerally). All ORM access is via ``resolve`` inside a
``mycelium.db`` call; this module imports no Django model at import time.

Three jobs, three commands:

* ``/activate code:``     → **Path B identity linking** (redeem a one-time code to
  bind the caller's own Discord account). Gated to the hub activation channel.
* ``/activate-lab code:`` → **Path C server activation** (redeem a lab's 10-digit
  code, issued on the website, to bind *this guild* to that lab). No linked identity
  required — the manager-issued code carries the authority.
* ``/setup``              → the *after-activation* interactive step: choose (or turn
  off) the deadline-announcements channel and the daily/weekly-updates channel —
  both optional. Requires the server to be activated AND the caller to be a linked
  lab manager (config actions still terminate in ``user_can_manage_lab``).
"""

from __future__ import annotations

from . import mycelium


async def status(discord_user_id: str) -> tuple[str, str]:
    return await mycelium.db(_status_sync, str(discord_user_id))


async def activate(
    discord_user_id: str, *, code: str | None = None, channel_id: str = ""
) -> tuple[str, str]:
    """``/activate code:`` — Path B identity linking (the caller's own account)."""
    code = (code or "").strip()
    if not code:
        return (
            "no_code",
            "Add your code: `/activate code:<XXXX-XXXX>` (get one from your Mycelium "
            "profile). To connect a *server* to a lab, use `/activate-lab` instead.",
        )
    # Channel gate first — no code lookup at all outside the activation channel.
    expected = await mycelium.db(_activation_channel)
    if expected and str(channel_id) != expected:
        return (
            "wrong_channel",
            f"Run `/activate code:` in <#{expected}>. Nothing was looked up.",
        )
    return await mycelium.db(_activate_code_sync, str(discord_user_id), code)


async def activate_lab(
    discord_user_id: str,
    *,
    code: str | None = None,
    guild_id: str = "",
    guild_name: str = "",
) -> tuple[str, str]:
    """``/activate-lab code:`` — bind *this guild* to the lab that issued the code."""
    code = (code or "").strip()
    if not guild_id:
        return ("no_guild", "Run `/activate-lab` inside your Discord server, not in a DM.")
    if not code:
        return (
            "no_code",
            "Add the lab's 10-digit code: `/activate-lab code:<XXXXX-XXXXX>`. Generate "
            "it from the lab's settings in Mycelium (the **Activate Lab** button).",
        )
    return await mycelium.db(
        _activate_lab_code_sync,
        str(discord_user_id),
        str(guild_id),
        str(guild_name),
        code,
    )


async def setup_state(discord_user_id: str, guild_id: str) -> tuple[str, dict]:
    """Auth + current channel bindings for rendering the `/setup` menu."""
    if not guild_id:
        return ("no_guild", {"message": "Run `/setup` inside your Discord server, not in a DM."})
    return await mycelium.db(_setup_state_sync, str(discord_user_id), str(guild_id))


async def bind_setup_channel(
    discord_user_id: str, guild_id: str, *, kind: str, channel_id: str
) -> tuple[str, dict]:
    """Bind (or, with an empty ``channel_id``, clear) one of the two `/setup` channels.

    ``kind`` is ``"deadlines"`` or ``"updates"``. Binding preflights by posting a
    real confirmation (the only postability proof the gateway has).
    """
    return await mycelium.db(
        _bind_setup_channel_sync,
        str(discord_user_id),
        str(guild_id),
        str(kind),
        str(channel_id),
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


# --------------------------------------------------------------------------- #
# Server activation (`/activate-lab code:`)
# --------------------------------------------------------------------------- #
def _activate_lab_code_sync(
    discord_user_id: str, guild_id: str, guild_name: str, code: str
) -> tuple[str, str]:
    from apps.integrations.services import lab_activation

    result = lab_activation.redeem(code, discord_user_id, guild_id, guild_name)
    O = lab_activation.RedeemOutcome
    if result.outcome is O.OK:
        return (
            "ok",
            f"✅ This server is now connected to **{result.lab_name}**.\n"
            "Next, run `/setup` to choose where deadline reminders and daily/weekly "
            "updates post — both optional.",
        )
    portal = mycelium.portal_url()
    lab = result.lab_name or "this lab"
    messages = {
        O.LOCKED_OUT: "Too many attempts. Try again in about an hour.",
        O.NOT_FOUND: "That lab code isn't valid. Double-check it, or generate a fresh "
        f"one from the lab's settings in Mycelium: {portal}",
        O.EXPIRED: "That lab code has expired. Generate a fresh one from the lab's "
        f"settings in Mycelium: {portal}",
        O.ALREADY_USED: "That lab code has already been used. Generate a fresh one "
        f"from the lab's settings in Mycelium: {portal}",
        O.CONFLICT: (
            f"Either this server is already connected to a different lab, or **{lab}** "
            "is already connected to another server. Disconnect the existing link in "
            "Mycelium first, then run `/activate-lab` again."
        ),
    }
    return (result.outcome.value, messages[result.outcome])


# --------------------------------------------------------------------------- #
# Post-activation channel config (`/setup`)
# --------------------------------------------------------------------------- #
_CHANNEL_LABELS = {"deadlines": "Deadline announcements", "updates": "Daily/weekly updates"}
_CHANNEL_PURPOSE = {"deadlines": "deadline reminders", "updates": "daily and weekly updates"}


def _setup_gate(resolve, link, discord_user_id: str) -> tuple[str, dict] | None:
    """Common `/setup` guard: server must be ACTIVE and the caller a linked manager.

    The activation state is checked here because it is a *Discord* fact — this guild
    is not yet bound to any lab — and saying so plainly is the whole point of the
    message. Everything after that (is this person linked, may they manage this lab,
    does the lab's plan cover Mylo, is anyone hammering the command) goes through the
    single authorization gate, so `/setup` cannot drift from what the slash commands
    enforce.
    """
    if link is None or link.state != resolve.GUILD_ACTIVE:
        return (
            "not_active",
            {"message": "This server isn't connected to a lab yet. A lab admin or PI "
             "runs `/activate-lab code:<code>` first — generate the code from the "
             "lab's settings in Mycelium."},
        )

    from apps.integrations.services import gate

    verdict = gate.authorize(
        discord_user_id=discord_user_id,
        action="setup",
        guild_id=link.guild_id,
    )
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    return None


def _state_payload(link) -> dict:
    return {
        "lab_name": link.lab.name,
        "deadlines_channel_id": link.announcement_channel_id or "",
        "updates_channel_id": link.updates_channel_id or "",
    }


def _setup_state_sync(discord_user_id: str, guild_id: str) -> tuple[str, dict]:
    from apps.integrations.services import resolve

    link = resolve.get_guild_link(guild_id)
    gate = _setup_gate(resolve, link, discord_user_id)
    if gate is not None:
        return gate
    return ("ok", _state_payload(link))


def _bind_setup_channel_sync(
    discord_user_id: str, guild_id: str, kind: str, channel_id: str
) -> tuple[str, dict]:
    from apps.integrations.services import resolve

    link = resolve.get_guild_link(guild_id)
    gate = _setup_gate(resolve, link, discord_user_id)
    if gate is not None:
        return gate
    lab_name = link.lab.name
    label = _CHANNEL_LABELS.get(kind, kind)

    # Opt-out: an empty channel clears the binding.
    if not channel_id:
        (resolve.clear_announcement_channel if kind == "deadlines"
         else resolve.clear_updates_channel)(guild_id)
        payload = _state_payload(resolve.get_guild_link(guild_id))
        payload["message"] = f"🔕 {label} turned off for **{lab_name}**."
        return ("cleared", payload)

    # Bind: prove postability by posting a real confirmation first.
    from django.utils import timezone

    from apps.content.reminders_discord import preflight_channel

    outcome = preflight_channel(channel_id, purpose=_CHANNEL_PURPOSE.get(kind, "updates"))
    if not outcome.ok:
        payload = _state_payload(link)
        if outcome.not_configured:
            # Not the channel's fault, and not this server's fault: Mylo has no bot
            # token configured on the Mycelium side, so it can't post *anywhere*.
            payload["message"] = (
                "⚠️ Mylo isn't fully set up on the Mycelium side yet — my bot token "
                "isn't configured, so I can't post in any channel (this is not about "
                f"<#{channel_id}>'s permissions). A Mycelium admin needs to set "
                "`DISCORD_API_KEY`, then try `/setup` again."
            )
            return ("not_configured", payload)
        if outcome.unreachable:
            # A real 403 from Discord for *this* channel in *this* server. 50001
            # (Missing Access) means I'm not in the server or can't even see the
            # channel; 50013 (Missing Permissions) means an overwrite blocks posting.
            if outcome.error_code == 50001:
                payload["message"] = (
                    f"⚠️ I can't see <#{channel_id}> in this server — either I'm not a "
                    "member here or I lack **View Channel**. Add me to the server (or "
                    "grant View Channel), then try again."
                )
            else:
                payload["message"] = (
                    f"⚠️ I can't post in <#{channel_id}> (a permission overwrite denies "
                    "me View/Send/Embed there). Pick another channel, or fix my "
                    "permissions and try again."
                )
            return ("channel_denied", payload)
        payload["message"] = (
            f"⚠️ I couldn't verify <#{channel_id}> just now. Try again in a moment."
        )
        return ("channel_error", payload)

    now = timezone.now()
    if kind == "deadlines":
        resolve.set_announcement_channel(guild_id, channel_id, verified_at=now)
    else:
        resolve.set_updates_channel(guild_id, channel_id, verified_at=now)
    payload = _state_payload(resolve.get_guild_link(guild_id))
    payload["message"] = (
        f"✅ {label} for **{lab_name}** → <#{channel_id}> (I sent a confirmation there)."
    )
    return ("ok", payload)

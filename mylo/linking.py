"""Async linking operations the gateway cogs call.

Each public coroutine returns a plain ``(status, message)`` or ``(status, payload)``
— the cog relays it (always ephemerally). All ORM access is via ``resolve`` inside a
``mycelium.db`` call; this module imports no Django model at import time.

Three jobs, three commands:

* ``/activate code:``     → **Path B identity linking** (redeem a one-time code to
  bind the caller's own Discord account). Runnable from any server Mylo is in; the
  hub's activation channel is enforced only inside the hub.
* ``/activate-lab code:`` → **Path C server activation** (redeem a lab's 10-digit
  code, issued on the website, to bind *this guild* to that lab). No linked identity
  required — the manager-issued code carries the authority.
* ``/activate-department code:`` → the same for a department. A server can hold a
  department and several labs; each is its own *binding*, set up and switched off
  on its own.
* ``/setup``              → the *after-activation* interactive step for one binding:
  choose (or turn off) the deadline-announcements channel and the daily/weekly-
  updates channel — both optional. In a server with several bindings the caller
  first picks which lab or department to configure. Requires the binding to be
  active AND the caller to be a linked manager *of that binding's target*.
"""

from __future__ import annotations

from . import mycelium


async def status(discord_user_id: str) -> tuple[str, str]:
    return await mycelium.db(_status_sync, str(discord_user_id))


async def activate(
    discord_user_id: str,
    *,
    code: str | None = None,
    channel_id: str = "",
    guild_id: str = "",
    mylo_present: bool = True,
) -> tuple[str, str]:
    """``/activate code:`` — Path B identity linking (the caller's own account).

    Runnable from **any** server Mylo is already in: a guild slash command proves
    both facts at once (Mylo is installed there, and the caller is a member), so
    joining the Mycelium hub is not a prerequisite for linking an account. The hub's
    ``#activation`` channel keeps its gate only *inside the hub itself*, so that
    server stays tidy; everywhere else any channel works.
    """
    code = (code or "").strip()
    if not code:
        return (
            "no_code",
            "Add your code: `/activate code:<XXXX-XXXX>` (get one from your Mycelium "
            "profile). To connect a *server* to a lab, use `/activate-lab` instead.",
        )
    if not guild_id:
        return (
            "no_guild",
            "Run `/activate code:` in a Discord server I'm in, not in a DM. "
            "Nothing was looked up.",
        )
    if not mylo_present:
        # Only reachable via a user-install invocation in a server Mylo isn't in.
        return (
            "not_present",
            "I'm not in this server, so I can't link you from here. Run "
            "`/activate code:` in any server I'm already in. Nothing was looked up.",
        )
    # Channel gate — the hub keeps its dedicated activation channel; other servers
    # accept the command anywhere. No code lookup at all in a gated-off channel.
    hub_guild, expected = await mycelium.db(_activation_gate)
    in_hub = bool(hub_guild) and str(guild_id) == hub_guild
    if in_hub and expected and str(channel_id) != expected:
        return (
            "wrong_channel",
            f"In this server, run `/activate code:` in <#{expected}> — or run it in "
            "any other server I'm in. Nothing was looked up.",
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


async def activate_department(
    discord_user_id: str,
    *,
    code: str | None = None,
    guild_id: str = "",
    guild_name: str = "",
) -> tuple[str, str]:
    """``/activate-department code:`` — bind the issuing department in *this guild*."""
    code = (code or "").strip()
    if not guild_id:
        return (
            "no_guild",
            "Run `/activate-department` inside your Discord server, not in a DM.",
        )
    if not code:
        return (
            "no_code",
            "Add the department's 10-digit code: `/activate-department "
            "code:<XXXXX-XXXXX>`. Generate it from the department's settings in "
            "Mycelium.",
        )
    return await mycelium.db(
        _activate_department_code_sync,
        str(discord_user_id),
        str(guild_id),
        str(guild_name),
        code,
    )


async def setup_state(
    discord_user_id: str, guild_id: str, binding_id: int | None = None
) -> tuple[str, dict]:
    """Auth + current channel bindings for rendering the `/setup` menu.

    Returns ``("choose", {"bindings": [...]})`` when the server holds several
    bindings and none was named, so the cog can ask which one to configure.
    """
    if not guild_id:
        return ("no_guild", {"message": "Run `/setup` inside your Discord server, not in a DM."})
    return await mycelium.db(
        _setup_state_sync, str(discord_user_id), str(guild_id), binding_id
    )


async def bind_setup_channel(
    discord_user_id: str,
    guild_id: str,
    *,
    kind: str,
    channel_id: str,
    binding_id: int | None = None,
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
        binding_id,
    )


# --------------------------------------------------------------------------- #
# Synchronous bodies (run in a worker thread with Django configured)
# --------------------------------------------------------------------------- #
def _activation_gate() -> tuple[str, str]:
    """``(hub_guild_id, activation_channel_id)`` — one hop, both halves of the gate."""
    return (mycelium.hub_guild_id(), mycelium.activation_channel_id())


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
            "Next, run `/setup` to choose where its deadline reminders and "
            "daily/weekly updates post — both optional. A server can hold several "
            "labs and a department; each is set up on its own.",
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
            f"I couldn't tell which server to connect **{lab}** to. Run "
            "`/activate-lab` inside the server itself."
        ),
    }
    return (result.outcome.value, messages[result.outcome])


def _activate_department_code_sync(
    discord_user_id: str, guild_id: str, guild_name: str, code: str
) -> tuple[str, str]:
    from apps.integrations.services import lab_activation

    result = lab_activation.redeem_department(
        code, discord_user_id, guild_id, guild_name
    )
    O = lab_activation.RedeemOutcome
    if result.outcome is O.OK:
        return (
            "ok",
            "✅ This server is now connected to the department "
            f"**{result.lab_name}**.\nRun `/setup` and pick the department to choose "
            "its channels. Labs in this server are connected and configured "
            "separately, with their own codes.",
        )
    portal = mycelium.portal_url()
    messages = {
        O.LOCKED_OUT: "Too many attempts. Try again in about an hour.",
        O.NOT_FOUND: "That department code isn't valid. Generate a fresh one from the "
        f"department's settings in Mycelium: {portal}",
        O.EXPIRED: "That department code has expired. Generate a fresh one from the "
        f"department's settings in Mycelium: {portal}",
        O.ALREADY_USED: "That department code has already been used. Generate a fresh "
        f"one from the department's settings in Mycelium: {portal}",
        O.CONFLICT: "Run `/activate-department` inside the server itself.",
    }
    return (result.outcome.value, messages[result.outcome])


# --------------------------------------------------------------------------- #
# Post-activation channel config (`/setup`)
# --------------------------------------------------------------------------- #
_CHANNEL_LABELS = {"deadlines": "Deadline announcements", "updates": "Daily/weekly updates"}
_CHANNEL_PURPOSE = {"deadlines": "deadline reminders", "updates": "daily and weekly updates"}


_NOT_ACTIVE = {
    "message": "This server isn't connected to a lab or department yet. A lab admin "
    "or PI runs `/activate-lab code:<code>` (or a department admin "
    "`/activate-department code:<code>`) first — generate the code from the lab's or "
    "department's settings in Mycelium."
}


def _binding_summary(resolve, binding) -> dict:
    return {
        "binding_id": binding.id,
        "kind": binding.target_kind,
        "name": resolve.binding_name(binding),
    }


def _pick_binding(resolve, guild_id: str, binding_id):
    """``(binding, None)``, or ``(None, (status, payload))`` explaining why not.

    With one binding in the server it is the answer, exactly as before bindings
    existed; with several the caller must name one.
    """
    bindings = resolve.bindings_for_guild(guild_id)
    if not bindings:
        return None, ("not_active", dict(_NOT_ACTIVE))
    if binding_id in (None, ""):
        if len(bindings) == 1:
            return bindings[0], None
        return None, (
            "choose",
            {
                "message": "This server holds more than one lab or department. "
                "Which one are you setting up?",
                "bindings": [_binding_summary(resolve, b) for b in bindings],
            },
        )
    for binding in bindings:
        if str(binding.id) == str(binding_id):
            return binding, None
    return None, ("not_active", dict(_NOT_ACTIVE))


def _setup_gate(resolve, guild_id: str, binding_id, discord_user_id: str):
    """Common `/setup` guard: an active binding, and the caller a linked manager of
    *that binding's* target.

    Activation is checked here because it is a *Discord* fact — this guild holds no
    binding yet — and saying so plainly is the whole point of the message.
    Everything after that (is this person linked, may they manage this lab or
    department, does its plan cover Mylo, is anyone hammering the command) goes
    through the single authorization gate, so `/setup` cannot drift from what the
    slash commands enforce.
    """
    binding, refusal = _pick_binding(resolve, guild_id, binding_id)
    if refusal is not None:
        return None, refusal

    from apps.integrations.services import gate

    verdict = gate.authorize(
        discord_user_id=discord_user_id,
        action="setup",
        guild_id=guild_id,
        binding_id=binding.id,
    )
    if not verdict.ok:
        return None, (str(verdict.denial), {"message": verdict.message})
    return binding, None


def _state_payload(resolve, binding) -> dict:
    return {
        "binding_id": binding.id,
        "target_kind": binding.target_kind,
        "lab_name": resolve.binding_name(binding),
        "deadlines_channel_id": resolve.route_channel(binding, "deadlines"),
        "updates_channel_id": resolve.route_channel(binding, "updates"),
    }


def _setup_state_sync(
    discord_user_id: str, guild_id: str, binding_id=None
) -> tuple[str, dict]:
    from apps.integrations.services import resolve

    binding, refusal = _setup_gate(resolve, guild_id, binding_id, discord_user_id)
    if refusal is not None:
        return refusal
    return ("ok", _state_payload(resolve, binding))


def _bind_setup_channel_sync(
    discord_user_id: str, guild_id: str, kind: str, channel_id: str, binding_id=None
) -> tuple[str, dict]:
    from apps.integrations.services import resolve

    binding, refusal = _setup_gate(resolve, guild_id, binding_id, discord_user_id)
    if refusal is not None:
        return refusal
    lab_name = resolve.binding_name(binding)
    label = _CHANNEL_LABELS.get(kind, kind)
    actor = resolve.resolve_user(discord_user_id)

    # Opt-out: an empty channel clears the binding.
    if not channel_id:
        resolve.clear_route(binding, kind, actor=actor)
        payload = _state_payload(resolve, binding)
        payload["message"] = f"🔕 {label} turned off for **{lab_name}**."
        return ("cleared", payload)

    # Bind: prove postability by posting a real confirmation first.
    from django.utils import timezone

    from tools.delivery.reminders_discord import preflight_channel

    outcome = preflight_channel(
        channel_id,
        purpose=_CHANNEL_PURPOSE.get(kind, "updates"),
        owner=binding.target_kind,
    )
    if not outcome.ok:
        payload = _state_payload(resolve, binding)
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

    resolve.set_route(
        binding, kind, channel_id, verified_at=timezone.now(), actor=actor
    )
    payload = _state_payload(resolve, binding)
    payload["message"] = (
        f"✅ {label} for **{lab_name}** → <#{channel_id}> (I sent a confirmation there)."
    )
    return ("ok", payload)


# --------------------------------------------------------------------------- #
# The `/mylo` research + reminder commands (Phase C)
# --------------------------------------------------------------------------- #
# Each is a thin async wrapper: the decision and the data live in
# `tools.delivery.discord_commands`, which starts every call at the authorization gate.
# Nothing here branches on permission — that would be a second place for the policy
# to live, and the two would eventually disagree.
async def search(
    discord_user_id: str, query: str, guild_id: str = ""
) -> tuple[str, dict]:
    return await mycelium.db(
        _search_sync, str(discord_user_id), query or "", str(guild_id or "")
    )


async def digest(discord_user_id: str, lab_slug: str = "") -> tuple[str, dict]:
    return await mycelium.db(_digest_sync, str(discord_user_id), lab_slug or "")


async def saves(discord_user_id: str, page: int = 0) -> tuple[str, dict]:
    return await mycelium.db(_saves_sync, str(discord_user_id), int(page or 0))


async def snooze(
    discord_user_id: str, *, reminder_id: str, amount: int, unit: str
) -> tuple[str, dict]:
    return await mycelium.db(
        _snooze_sync, str(discord_user_id), str(reminder_id), int(amount), str(unit)
    )


async def cancel(discord_user_id: str, *, reminder_id: str) -> tuple[str, dict]:
    return await mycelium.db(_cancel_sync, str(discord_user_id), str(reminder_id))


async def manageable_reminders(
    discord_user_id: str, prefix: str = ""
) -> tuple[str, dict]:
    return await mycelium.db(
        _manageable_sync, str(discord_user_id), str(prefix or "")
    )


def _search_sync(discord_user_id: str, query: str, guild_id: str) -> tuple[str, dict]:
    from tools.delivery import discord_commands

    return discord_commands.search(discord_user_id, query, guild_id)


def _digest_sync(discord_user_id: str, lab_slug: str) -> tuple[str, dict]:
    from tools.delivery import discord_commands

    return discord_commands.digest(discord_user_id, lab_slug)


def _saves_sync(discord_user_id: str, page: int) -> tuple[str, dict]:
    from tools.delivery import discord_commands

    return discord_commands.saves(discord_user_id, page)


def _snooze_sync(
    discord_user_id: str, reminder_id: str, amount: int, unit: str
) -> tuple[str, dict]:
    from tools.delivery import discord_commands

    return discord_commands.snooze(
        discord_user_id, reminder_id=reminder_id, amount=amount, unit=unit
    )


def _cancel_sync(discord_user_id: str, reminder_id: str) -> tuple[str, dict]:
    from tools.delivery import discord_commands

    return discord_commands.cancel(discord_user_id, reminder_id=reminder_id)


def _manageable_sync(discord_user_id: str, prefix: str) -> tuple[str, dict]:
    from tools.delivery import discord_commands

    return discord_commands.list_manageable(discord_user_id, prefix)


def user_labs(discord_user_id: str):
    """Labs the caller can pick for a lab-scoped command. Empty when unlinked."""
    return mycelium.db(_user_labs_sync, str(discord_user_id))


def _user_labs_sync(discord_user_id: str) -> list[dict]:
    from apps.accounts.models import LabMembership
    from apps.integrations.services import resolve

    user = resolve.resolve_user(discord_user_id)
    if user is None:
        return []
    rows = LabMembership.objects.filter(user=user).select_related("lab")
    return [{"slug": m.lab.slug, "name": m.lab.name} for m in rows]


# --------------------------------------------------------------------------- #
# Live drift events (Phase E)
# --------------------------------------------------------------------------- #
async def guild_removed(guild_id: str) -> str:
    """Mylo was removed from a server — mark the link kicked."""
    return await mycelium.db(_guild_removed_sync, str(guild_id))


async def channel_deleted(guild_id: str, channel_id: str) -> str:
    """A channel vanished — unbind it if Mylo was posting there."""
    return await mycelium.db(
        _channel_deleted_sync, str(guild_id), str(channel_id)
    )


def _guild_removed_sync(guild_id: str) -> str:
    from apps.integrations.services import resolve

    if resolve.get_guild_link(guild_id) is None:
        return "unknown_guild"
    resolve.mark_guild_kicked(guild_id)
    return "kicked"


def _channel_deleted_sync(guild_id: str, channel_id: str) -> str:
    from apps.integrations.services import resolve

    # Returns which routes held it ("deadlines", "updates,grants", …), or "" for the
    # common case of a channel Mylo never used.
    return resolve.clear_channel_by_id(guild_id, channel_id) or "not_bound"


# --------------------------------------------------------------------------- #
# Opportunity announcements: the thread buttons and the `/setup` step
# --------------------------------------------------------------------------- #
# The decisions live in `tools.delivery.announcement_actions` and
# `tools.delivery.announcement_setup`; both start at the authorization gate.
async def announcement_action(
    discord_user_id: str,
    post_id: str,
    action: str,
    *,
    guild_id: str = "",
    offsets: list[str] | None = None,
    where: str = "dm",
    reason: str = "",
) -> tuple[str, dict]:
    return await mycelium.db(
        _announcement_action_sync,
        str(discord_user_id),
        str(post_id),
        str(action),
        str(guild_id or ""),
        list(offsets or []),
        str(where or "dm"),
        str(reason or ""),
    )


def _announcement_action_sync(
    discord_user_id, post_id, action, guild_id, offsets, where, reason
) -> tuple[str, dict]:
    from tools.delivery import announcement_actions as actions

    if action == "interested":
        return actions.interested(discord_user_id, post_id, guild_id)
    if action == "remind":
        return actions.remind_options(discord_user_id, post_id, guild_id)
    if action == "remind_set":
        return actions.remind_set(discord_user_id, post_id, offsets, where, guild_id)
    if action == "notforus":
        return actions.not_for_us(discord_user_id, post_id, reason, guild_id)
    if action == "unfollow":
        return actions.unfollow(discord_user_id, post_id, guild_id)
    if action == "unremind":
        return actions.unremind(discord_user_id, post_id, guild_id)
    return ("unknown", {"message": "That button is no longer used."})


async def announcement_setup(
    discord_user_id: str,
    guild_id: str,
    binding_id,
    op: str,
    *,
    purpose: str = "",
    channel_id: str = "",
    policy: str = "",
    role_ids: list[str] | None = None,
    bot_user_id: str = "",
) -> tuple[str, dict]:
    """One operation of the announcements step for one binding."""
    return await mycelium.db(
        _announcement_setup_sync,
        str(discord_user_id),
        str(guild_id),
        binding_id,
        str(op),
        str(purpose),
        str(channel_id),
        str(policy),
        list(role_ids or []),
        str(bot_user_id),
    )


def _announcement_setup_sync(
    discord_user_id, guild_id, binding_id, op, purpose, channel_id, policy, role_ids,
    bot_user_id,
) -> tuple[str, dict]:
    from tools.delivery import announcement_setup as setup
    from apps.integrations.services import gate, resolve

    binding, refusal = _pick_binding(resolve, guild_id, binding_id)
    if refusal is not None:
        return refusal
    verdict = gate.authorize(
        discord_user_id=discord_user_id,
        action="ann_setup",
        guild_id=guild_id,
        binding_id=binding.id,
    )
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    actor = verdict.user
    ok, message = True, ""
    if op == "create":
        ok, message = setup.create_forums(binding, actor=actor)
    elif op == "use":
        if channel_id:
            ok, message = setup.use_forum(binding, purpose, channel_id, actor=actor)
        else:
            message = setup.clear_forum(binding, purpose, actor=actor)
    elif op == "policy":
        ok, message = setup.set_poster_policy(
            binding,
            policy,
            role_ids=role_ids,
            manager_discord_ids=setup.manager_discord_ids(binding),
            bot_user_id=bot_user_id,
        )
    elif op in ("on", "off"):
        if op == "on" and not setup.state(binding)["routes"]:
            ok, message = False, "Choose or create the forums first."
        else:
            _row, first = setup.switch(binding, on=(op == "on"), actor=actor)
            message = (
                "Announcements are **on**. Mylo is posting the six most relevant open "
                "items and the closing-soon list now; after that, only new ones. "
                "Want more in each forum? Run `/mylo populate`."
                if first
                else ("Announcements are **on**." if op == "on" else
                      "Announcements are **off**. Existing threads stay.")
            )
            payload = {**setup.state(binding), "message": message, "activate": first}
            return ("ok", payload)
    elif op != "state":
        return ("unknown", {"message": "Unknown setup step."})
    payload = {**setup.state(binding), "message": message}
    return ("ok" if ok else "refused", payload)


async def activate_announcements(guild_id: str, binding_id) -> dict:
    """Run the activation seed for one binding (called after switching on)."""
    return await mycelium.db(_activate_announcements_sync, str(guild_id), binding_id)


def _activate_announcements_sync(guild_id, binding_id) -> dict:
    from tools.delivery import announce
    from tools.delivery import announcement_setup as setup
    from apps.integrations.services import resolve

    if not announce.enabled():
        return {"posted": 0, "reason": "switched_off"}
    binding, refusal = _pick_binding(resolve, guild_id, binding_id)
    if refusal is not None:
        return {"posted": 0, "reason": "no_binding"}
    return setup.activate_now(binding)


async def populate_forums(
    discord_user_id: str, guild_id: str, binding_id, count: int
) -> tuple[str, dict]:
    """``/mylo populate``: fill this server's opportunity forums (it calls the model
    per item, so it runs on a thread of its own)."""
    return await mycelium.db_long(
        _populate_forums_sync, str(discord_user_id), str(guild_id), binding_id,
        int(count),
    )


def _populate_forums_sync(discord_user_id, guild_id, binding_id, count):
    from apps.integrations.services import gate, resolve

    from tools.delivery import announcement_setup as setup

    binding, refusal = _pick_binding(resolve, guild_id, binding_id)
    if refusal is not None:
        return refusal
    verdict = gate.authorize(
        discord_user_id=discord_user_id,
        action="ann_populate",
        guild_id=guild_id,
        binding_id=binding.id,
    )
    if not verdict.ok:
        return (str(verdict.denial), {"message": verdict.message})
    return setup.populate(binding, count, actor=verdict.user)


async def guild_bindings(guild_id: str) -> list[dict]:
    """The labs and departments bound in a server, for a command's picker."""
    return await mycelium.db(_guild_bindings_sync, str(guild_id))


def _guild_bindings_sync(guild_id: str) -> list[dict]:
    from apps.integrations.services import resolve

    return [
        _binding_summary(resolve, b) for b in resolve.bindings_for_guild(guild_id)
    ]


async def announcement_manual(
    discord_user_id: str, guild_id: str, binding_id: str, content_id: str
) -> tuple[str, dict]:
    """"Announce to #…" from a search result."""
    return await mycelium.db(
        _announcement_manual_sync,
        str(discord_user_id),
        str(guild_id),
        str(binding_id),
        str(content_id),
    )


def _announcement_manual_sync(discord_user_id, guild_id, binding_id, content_id):
    from tools.delivery import announcement_links

    return announcement_links.manual_announce(
        discord_user_id, guild_id, binding_id, content_id
    )


async def thread_deleted(thread_id: str) -> int:
    """A thread was deleted in Discord; if Mylo posted it, never link it again."""
    return await mycelium.db(_thread_deleted_sync, str(thread_id))


def _thread_deleted_sync(thread_id: str) -> int:
    from tools.delivery.discord_announcements import mark_thread_deleted

    return mark_thread_deleted(thread_id)

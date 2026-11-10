"""Bridge from the gateway to Mylo chat (plan D), like ``linking.py``.

The cogs import no Django; every call here runs the agent's Discord surface
(``tools/agent/surfaces/discord.py``) off the event loop through
``mycelium.db`` / ``db_long``. The surface is reached through
``tools._framework.services.get("agent")``, so the bot keeps running, and says
so politely, when the agent tool is off.

``route`` is pure: it decides from the gateway event alone whether a message
is a question for Mylo. Identity is always the event's author id, never text.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from . import mycelium

AGENT_OFF = "Mylo chat isn't enabled on this Mycelium."
#: Sent (at most once an hour per person) for a reply to Mylo without the
#: ping: Discord delivers such a reply with no text (S-4).
REPLY_HINT = "I can only read replies that ping me."


# --------------------------------------------------------------------------- #
# Routing (pure)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Route:
    """``chat`` (a question), ``reply_hint`` (a reply to Mylo without the
    ping: no text arrives), or ``none``."""

    kind: str
    text: str = ""


NONE = Route("none")


def _bot_role_ids(message, bot_id) -> list[int]:
    """The bot's own managed role(s) named in the message."""
    out = []
    for role in getattr(message, "role_mentions", None) or []:
        tags = getattr(role, "tags", None)
        if getattr(tags, "bot_id", None) == bot_id:
            out.append(role.id)
    return out


def _replies_to_bot(message, bot_id) -> bool:
    ref = getattr(message, "reference", None)
    resolved = getattr(ref, "resolved", None)
    author = getattr(resolved, "author", None)
    return getattr(author, "id", None) == bot_id


def route(message, bot_user) -> Route:
    """Whether ``message`` is addressed to Mylo (S-4): a DM, a mention of the
    bot or its role, or a reply to Mylo (which pings it by default)."""
    from .bot.chat_render import strip_mention

    if bot_user is None:
        return NONE
    author = message.author
    if getattr(author, "bot", False) or getattr(message, "webhook_id", None):
        return NONE
    bot_id = bot_user.id
    if message.guild is None:
        return Route("chat", (message.content or "").strip())
    roles = _bot_role_ids(message, bot_id)
    mentioned = any(getattr(u, "id", None) == bot_id for u in message.mentions)
    if mentioned or roles:
        return Route(
            "chat", strip_mention(message.content or "", bot_id=bot_id, role_ids=roles)
        )
    if _replies_to_bot(message, bot_id):
        return Route("reply_hint")
    return NONE


def place_ids(message) -> dict:
    """``guild_id, channel_id, thread_id, parent_id`` from the event."""
    import discord

    channel = message.channel
    guild_id = str(message.guild.id) if message.guild else ""
    if isinstance(channel, discord.Thread):
        return {
            "guild_id": guild_id,
            "channel_id": str(channel.id),
            "thread_id": str(channel.id),
            "parent_id": str(channel.parent_id or ""),
        }
    return {
        "guild_id": guild_id,
        "channel_id": str(channel.id),
        "thread_id": "",
        "parent_id": "",
    }


# --------------------------------------------------------------------------- #
# Calls into the agent
# --------------------------------------------------------------------------- #


def _surface():
    from tools._framework import services

    agent = services.get("agent")
    return agent.discord_surface() if agent is not None else None


def _uploads(files):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return [
        SimpleUploadedFile(name, data, content_type=ctype or "application/octet-stream")
        for name, data, ctype in files
    ]


def _ask_sync(facts: dict, files):
    surface = _surface()
    if surface is None:
        return {"refusal": AGENT_OFF}
    out = surface.ask(**facts, attachments=_uploads(files) if files else ())
    if isinstance(out, surface.Refusal):
        return {"refusal": out.message, "code": out.code}
    return {"handle": out}


async def ask(
    *,
    discord_user_id: str,
    name: str,
    guild_id: str,
    channel_id: str,
    thread_id: str,
    parent_id: str,
    message_id: str,
    text: str,
    files=(),
    reply_to_id: str = "",
) -> dict:
    """``{"handle": Handle}`` or ``{"refusal": sentence}``. ``reply_to_id`` is
    the message this one replies to: a reply to Mylo's answer continues that
    conversation."""
    return await mycelium.db(
        _ask_sync,
        {
            "discord_user_id": str(discord_user_id),
            "name": name,
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "thread_id": str(thread_id),
            "parent_id": str(parent_id),
            "message_id": str(message_id),
            "text": text,
            "reply_to_id": str(reply_to_id or ""),
        },
        list(files),
    )


async def watch(handle) -> AsyncIterator[dict]:
    """The turn's activity view, streamed from a worker thread."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    done = object()

    def pump():
        try:
            for message in _surface().follow(handle):
                loop.call_soon_threadsafe(queue.put_nowait, message)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, done)

    task = asyncio.ensure_future(mycelium.db_long(pump))
    try:
        while True:
            item = await queue.get()
            if item is done:
                break
            yield item
    finally:
        await asyncio.gather(task, return_exceptions=True)


def _call(name, *args, **kwargs):
    surface = _surface()
    if surface is None:
        return None
    return getattr(surface, name)(*args, **kwargs)


async def result(handle) -> dict:
    return await mycelium.db(_call, "result", handle) or {"state": "failed"}


async def set_status(handle, message_id):
    return await mycelium.db(_call, "set_status_message", handle, str(message_id))


async def finish(handle, state: str, message_ids=()) -> None:
    await mycelium.db(
        _call, "finish", handle, state, [str(m) for m in message_ids or ()]
    )


async def ping_due(handle) -> bool:
    return bool(await mycelium.db(_call, "ping_due", handle))


async def timed_out(handle) -> bool:
    return bool(await mycelium.db(_call, "timed_out", handle))


async def stop(handle, discord_user_id: str) -> str:
    """``""`` when stopped, else the refusal sentence."""
    out = await mycelium.db(_call, "stop", handle, discord_user_id=str(discord_user_id))
    return getattr(out, "message", "") if out else ""


async def handle_for(turn_id: int):
    def run():
        surface = _surface()
        if surface is None:
            return None
        for h in surface.reconcile():
            if h.turn_id == int(turn_id):
                return h
        return None

    return await mycelium.db(run)


async def forget(discord_user_id: str, guild_id: str, place_id: str) -> int:
    return int(
        await mycelium.db(
            _call,
            "forget",
            discord_user_id=str(discord_user_id),
            guild_id=str(guild_id),
            place_id=str(place_id),
        )
        or 0
    )


async def new_command(discord_user_id: str, guild_id: str, place_id: str) -> str:
    """``/mylo new``: start a fresh conversation here."""
    return (
        await mycelium.db(
            _call,
            "new_command",
            discord_user_id=str(discord_user_id),
            guild_id=str(guild_id),
            place_id=str(place_id),
        )
        or AGENT_OFF
    )


async def forget_command(discord_user_id: str, guild_id: str, place_id: str) -> str:
    return (
        await mycelium.db(
            _call,
            "forget_command",
            discord_user_id=str(discord_user_id),
            guild_id=str(guild_id),
            place_id=str(place_id),
        )
        or AGENT_OFF
    )


async def set_chat(discord_user_id: str, *, on: bool) -> str:
    return (
        await mycelium.db(_call, "set_chat", discord_user_id=str(discord_user_id), on=on)
        or AGENT_OFF
    )


async def set_channel(discord_user_id: str, ids: dict, *, on: bool) -> str:
    return (
        await mycelium.db(
            _call, "set_channel", discord_user_id=str(discord_user_id), on=on, **ids
        )
        or AGENT_OFF
    )


async def set_guests(discord_user_id: str, ids: dict, *, level: str) -> str:
    return (
        await mycelium.db(
            _call,
            "set_guests",
            discord_user_id=str(discord_user_id),
            level=level,
            **ids,
        )
        or AGENT_OFF
    )


def interaction_ids(interaction) -> dict:
    """``guild_id, channel_id, thread_id, parent_id`` of a slash command."""
    import discord

    channel = interaction.channel
    guild_id = str(interaction.guild_id or "")
    if isinstance(channel, discord.Thread):
        return {
            "guild_id": guild_id,
            "channel_id": str(channel.id),
            "thread_id": str(channel.id),
            "parent_id": str(channel.parent_id or ""),
        }
    return {
        "guild_id": guild_id,
        "channel_id": str(interaction.channel_id or ""),
        "thread_id": "",
        "parent_id": "",
    }


async def question_deleted(message_id: str) -> bool:
    return bool(await mycelium.db(_call, "question_deleted", str(message_id)))


async def place_deleted(place_id: str) -> int:
    return int(await mycelium.db(_call, "place_deleted", str(place_id)) or 0)


async def guild_left(guild_id: str) -> int:
    return int(await mycelium.db(_call, "close_links", guild_id=str(guild_id)) or 0)


async def reconcile() -> list:
    return list(await mycelium.db(_call, "reconcile") or [])


def _health_sync() -> dict:
    surface = _surface()
    if surface is None:
        return {"enabled": False, "model": None, "bus": False}
    from tools._framework import services

    service = services.get("agent")
    model = service.status().get("model")
    return {"enabled": True, "model": model, "bus": bool(surface.bus_ok())}


async def health() -> dict:
    """``{enabled, model, bus}`` for ``/mylo health``."""
    return await mycelium.db(_health_sync)

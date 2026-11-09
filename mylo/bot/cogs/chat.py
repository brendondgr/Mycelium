"""Mylo chat in Discord (plan D): delivery, recovery and the Stop button.

There is no second ``on_message`` here: ``cogs/listen.py`` holds the only one
and hands a question over with :meth:`ChatCog.ask`. Access is never decided
here either: the bridge (``mylo/chat.py``) runs the gate and the agent.

What a person sees (S-9, S-12):

1. Mylo replies to the question with a status line from the activity view.
2. The line is edited as Mylo works, at most every 1.5 seconds, with a
   **Stop** button the asker (or a manager of the lab) can press.
3. The status message becomes the answer; further chunks follow as plain
   messages. An edit notifies nobody.
4. An answer slower than the configured minutes is a new reply that pings the
   asker and nobody else; the status message then says "Answered below."

Every send and edit carries ``AllowedMentions.none()``, except that one ping.
A listener never kills the gateway: every handler is wrapped.
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord.ext import commands

from ... import chat
from .. import chat_render as render

log = logging.getLogger(__name__)

STOP_PREFIX = "mylo-chat:stop:"
ANSWER_PREFIX = "mylo-chat:answer:"
HOURGLASS = "\N{HOURGLASS WITH FLOWING SAND}"
#: One "I can only read replies that ping me" per person per hour.
HINT_EVERY = 3600.0
#: Files read from a DM before they reach the files tool's own limits.
MAX_FILE_BYTES = 25 * 1024 * 1024


def _none() -> discord.AllowedMentions:
    return discord.AllowedMentions.none()


def _only(discord_user_id: str) -> discord.AllowedMentions:
    """The asker, and nobody else: no roles, no @everyone, no replied user."""
    return discord.AllowedMentions(
        everyone=False,
        roles=False,
        users=[discord.Object(id=int(discord_user_id))],
        replied_user=False,
    )


def stop_view(turn_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="Stop",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{STOP_PREFIX}{turn_id}",
        )
    )
    return view


def question_view(turn_id: int, options) -> discord.ui.View | None:
    """``ask_user`` options as buttons, in a DM only."""
    view = discord.ui.View(timeout=None)
    for index, option in enumerate(list(options or [])[:5]):
        view.add_item(
            discord.ui.Button(
                label=str(option)[:80],
                style=discord.ButtonStyle.secondary,
                custom_id=f"{ANSWER_PREFIX}{turn_id}:{index}",
            )
        )
    return view if view.children else None


class ChatCog(commands.Cog, name="Chat"):
    def __init__(self, bot: commands.Bot, *, bridge=None, clock=time.monotonic):
        self.bot = bot
        self.bridge = bridge or chat
        self.clock = clock
        self._hinted: dict[str, float] = {}
        self._active: set[int] = set()
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------ asking
    async def ask(self, message: discord.Message, text: str) -> None:
        """A question addressed to Mylo. Called by the listen cog."""
        try:
            await self._ask(message, text)
        except Exception:  # noqa: BLE001 — a listener never kills the gateway
            log.exception("could not answer a chat question")

    async def _files(self, message) -> list:
        if message.guild is not None:
            return []  # files are off where others read (the files group)
        out = []
        for attachment in getattr(message, "attachments", None) or []:
            if (attachment.size or 0) > MAX_FILE_BYTES:
                continue
            try:
                data = await attachment.read()
            except discord.HTTPException:
                continue
            out.append((attachment.filename, data, attachment.content_type))
        return out

    async def _ask(self, message, text: str) -> None:
        ids = chat.place_ids(message)
        author = message.author
        out = await self.bridge.ask(
            discord_user_id=str(author.id),
            name=getattr(author, "display_name", None) or author.name,
            message_id=str(message.id),
            text=text,
            files=await self._files(message),
            **ids,
        )
        if "refusal" in out:
            await self._reply(message, out["refusal"])
            return
        handle = out["handle"]
        if handle.queued:
            try:
                await message.add_reaction(HOURGLASS)
            except discord.HTTPException:
                pass
        status = await self._reply(
            message,
            render.QUEUED if handle.queued else render.STARTING,
            view=stop_view(handle.turn_id),
        )
        if status is None:
            return
        handle = await self.bridge.set_status(handle, status.id) or handle
        await self.deliver(handle, status, message.channel, live=True)

    async def ask_slash(self, interaction, question: str, *, private: bool) -> None:
        """``/mylo ask``: the same as a mention. ``private`` asks in the
        person's own DM conversation and answers only them (ephemeral)."""
        try:
            await interaction.response.defer(ephemeral=private, thinking=True)
            if private and interaction.guild_id is not None:
                dm = interaction.user.dm_channel or await interaction.user.create_dm()
                ids = {
                    "guild_id": "",
                    "channel_id": str(dm.id),
                    "thread_id": "",
                    "parent_id": "",
                }
            else:
                ids = chat.interaction_ids(interaction)
            out = await self.bridge.ask(
                discord_user_id=str(interaction.user.id),
                name=getattr(interaction.user, "display_name", "")
                or interaction.user.name,
                message_id=str(interaction.id),
                text=question,
                **ids,
            )
            if "refusal" in out:
                await interaction.followup.send(
                    out["refusal"], ephemeral=True, allowed_mentions=_none()
                )
                return
            handle = out["handle"]
            status = await interaction.followup.send(
                render.QUEUED if handle.queued else render.STARTING,
                ephemeral=private,
                wait=True,
                allowed_mentions=_none(),
                view=stop_view(handle.turn_id),
            )
            handle = await self.bridge.set_status(handle, status.id) or handle
            await self.deliver(handle, status, interaction.channel, live=True)
        except Exception:  # noqa: BLE001
            log.exception("could not answer /mylo ask")

    async def _reply(self, message, content: str, *, view=None):
        """Reply to the question without pinging anyone; ``None`` when Mylo
        cannot post here (nothing is sent, and it is logged)."""
        kwargs = {"allowed_mentions": _none(), "mention_author": False}
        if view is not None:
            kwargs["view"] = view
        try:
            return await message.reply(content, **kwargs)
        except discord.Forbidden:
            log.warning(
                "chat: cannot post in channel %s", getattr(message.channel, "id", "?")
            )
            return None
        except discord.HTTPException:
            log.exception("chat: could not reply")
            return None

    async def hint(self, message: discord.Message) -> None:
        """A reply to Mylo with the ping turned off arrives without text."""
        try:
            key = str(message.author.id)
            now = self.clock()
            last = self._hinted.get(key)
            if last is not None and now - last < HINT_EVERY:
                return
            self._hinted[key] = now
            await self._reply(message, chat.REPLY_HINT)
        except Exception:  # noqa: BLE001
            log.exception("could not send the reply hint")

    # ---------------------------------------------------------- delivering
    async def deliver(self, handle, status, channel, *, live: bool) -> None:
        """Watch the turn (when ``live``), then turn the status into the answer."""
        if handle.turn_id in self._active:
            return
        self._active.add(handle.turn_id)
        try:
            if live:
                throttle = render.Throttle(clock=self.clock)
                shown = ""
                async for message in self.bridge.watch(handle):
                    line = render.status_line(message)
                    if line and line != shown and throttle.ready():
                        shown = line
                        await self._edit(status, line)
            res = await self.bridge.result(handle)
            await self._finish(handle, status, channel, res)
        except Exception:  # noqa: BLE001
            log.exception("could not deliver chat turn %s", handle.turn_id)
        finally:
            self._active.discard(handle.turn_id)

    async def _edit(self, status, content: str, *, view=discord.utils.MISSING):
        kwargs = {"content": content, "allowed_mentions": _none()}
        if view is not discord.utils.MISSING:
            kwargs["view"] = view
        try:
            await status.edit(**kwargs)
            return True
        except discord.HTTPException:
            return False

    async def _send(self, channel, content: str, *, allowed=None, reference=None):
        kwargs = {"allowed_mentions": allowed or _none()}
        if reference is not None:
            kwargs["reference"] = reference
        try:
            return await channel.send(content, **kwargs)
        except discord.HTTPException:
            log.exception("chat: could not send a chunk")
            return None

    async def _finish(self, handle, status, channel, res: dict) -> None:
        state = res.get("state")
        if state == "answered":
            chunks = render.answer_chunks(
                res.get("text") or "",
                res.get("sources") or [],
                res.get("model"),
                first=bool(getattr(handle, "first", False)),
            )
            if await self.bridge.ping_due(handle):
                await self._edit(status, render.ANSWERED_BELOW, view=None)
                reference = discord.MessageReference(
                    message_id=int(handle.trigger_message_id),
                    channel_id=int(handle.channel_id),
                    fail_if_not_exists=False,
                )
                await self._send(
                    channel,
                    render.slow_answer_prefix(handle.discord_user_id) + chunks[0],
                    allowed=_only(handle.discord_user_id),
                    reference=reference,
                )
            else:
                await self._edit(status, chunks[0], view=None)
            for chunk in chunks[1:]:
                await self._send(channel, chunk)
            await self.bridge.finish(handle, "answered")
        elif state == "waiting":
            question = res.get("question") or {}
            await self._edit(
                status,
                render.question_text(question),
                view=question_view(handle.turn_id, question.get("options")),
            )
            await self.bridge.finish(handle, "answered")
        elif state == "cancelled":
            await self._edit(status, render.STOPPED, view=None)
            await self.bridge.finish(handle, "cancelled")
        elif state == "failed":
            detail = render.neutralise(res.get("error") or "")
            text = f"{render.FAILED}\n-# {detail}" if detail else render.FAILED
            await self._edit(status, text[: render.LIMIT], view=None)
            await self.bridge.finish(handle, "failed")
        elif await self.bridge.timed_out(handle):
            await self._edit(status, render.LOST, view=None)
            await self.bridge.finish(handle, "failed")

    # ------------------------------------------------------------ recovery
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.recover()

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        await self.recover()

    async def recover(self) -> int:
        """Deliver what a restart left behind: finished turns are answered
        once (with the ping, if late by then), errors and old rows become "I
        lost track of this one", and running turns are watched again."""
        try:
            handles = await self.bridge.reconcile()
        except Exception:  # noqa: BLE001
            log.exception("chat recovery failed")
            return 0
        resumed = 0
        for handle in handles:
            if handle.turn_id in self._active:
                continue
            try:
                channel = await self._channel(handle.channel_id)
                if channel is None:
                    await self.bridge.finish(handle, "failed")
                    continue
                status = (
                    channel.get_partial_message(int(handle.status_message_id))
                    if handle.status_message_id
                    else None
                )
                if status is None:
                    status = await self._send(channel, render.STARTING)
                    if status is None:
                        continue
                    handle = await self.bridge.set_status(handle, status.id) or handle
                res = await self.bridge.result(handle)
                if res.get("state") == "running" and not await self.bridge.timed_out(
                    handle
                ):
                    task = asyncio.ensure_future(
                        self.deliver(handle, status, channel, live=True)
                    )
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                else:
                    await self._finish_once(handle, status, channel, res)
                resumed += 1
            except Exception:  # noqa: BLE001
                log.exception("could not recover chat turn %s", handle.turn_id)
        return resumed

    async def _finish_once(self, handle, status, channel, res) -> None:
        if handle.turn_id in self._active:
            return
        self._active.add(handle.turn_id)
        try:
            if res.get("state") == "running":
                await self._edit(status, render.LOST, view=None)
                await self.bridge.finish(handle, "failed")
                return
            await self._finish(handle, status, channel, res)
        finally:
            self._active.discard(handle.turn_id)

    async def _channel(self, channel_id: str):
        channel = self.bot.get_channel(int(channel_id))
        if channel is not None:
            return channel
        try:
            return await self.bot.fetch_channel(int(channel_id))
        except discord.HTTPException:
            return None

    # ------------------------------------------------------------- buttons
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        try:
            if interaction.type != discord.InteractionType.component:
                return
            custom_id = str((interaction.data or {}).get("custom_id") or "")
            if custom_id.startswith(STOP_PREFIX):
                await self._stop(interaction, custom_id.removeprefix(STOP_PREFIX))
            elif custom_id.startswith(ANSWER_PREFIX):
                await self._answer(interaction, custom_id.removeprefix(ANSWER_PREFIX))
        except Exception:  # noqa: BLE001
            log.exception("could not handle a chat button")

    async def _stop(self, interaction, turn_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        handle = await self.bridge.handle_for(int(turn_id))
        if handle is None:
            await interaction.followup.send("That answer has already finished.", ephemeral=True)
            return
        refused = await self.bridge.stop(handle, str(interaction.user.id))
        await interaction.followup.send(refused or "Stopping.", ephemeral=True)

    async def _answer(self, interaction, rest: str) -> None:
        """A DM button on one of Mylo's own questions: answered like a message."""
        await interaction.response.defer()
        turn_id, _, index = rest.partition(":")
        label = ""
        for row in getattr(interaction.message, "components", None) or []:
            for item in getattr(row, "children", None) or []:
                if getattr(item, "custom_id", "") == f"{ANSWER_PREFIX}{rest}":
                    label = getattr(item, "label", "") or ""
        if not label:
            return
        try:
            if interaction.message is not None:
                await interaction.message.edit(view=None, allowed_mentions=_none())
        except discord.HTTPException:
            pass
        out = await self.bridge.ask(
            discord_user_id=str(interaction.user.id),
            name=getattr(interaction.user, "display_name", "") or "",
            message_id=f"{interaction.id}",
            text=label,
            guild_id="",
            channel_id=str(interaction.channel_id),
            thread_id="",
            parent_id="",
        )
        channel = interaction.channel
        if "refusal" in out:
            await self._send(channel, out["refusal"])
            return
        handle = out["handle"]
        status = await self._send(channel, render.STARTING)
        if status is None:
            return
        handle = await self.bridge.set_status(handle, status.id) or handle
        await self.deliver(handle, status, channel, live=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatCog(bot))

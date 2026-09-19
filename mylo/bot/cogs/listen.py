"""Listening: the cog that hears a conversation and hands it to the ledger.

People talk normally. Nobody types a command to be understood. This cog carries
what is said to the backend and does nothing else with it — no analysis, no
judgement, no reply beyond a short acknowledgement in a DM.

**Two stages, and only one of them is live.**

*Stage A* needs no privileged intent and is what ships on: direct messages to
Mylo, messages that @mention it, and reactions on its own posts. Discord
delivers the content of all three to any bot, always.

*Stage B* is server-wide listening, which needs the **Message Content**
privileged intent. The code for it is here and tested, and it is off:
``MYLO_LISTEN_ENABLED`` must be set *and* the intent granted in the Developer
Portal. Shipping it dark is deliberate — the intent is easier to justify with a
feature that has already been measured on Stage A data (Plan 02, OD-02a).

**A listener must never take the gateway down.** Every handler is wrapped;
losing one message is a much smaller failure than losing the connection that
would have carried the next thousand.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from ... import listening

log = logging.getLogger(__name__)

#: What Mylo says when somebody tells it something in a DM. Deliberately almost
#: nothing: what Mylo asks, and when, is Plan 06's, and a provisional second
#: voice here would be one to unpick later.
_DM_ACK = "Got it — I'll take that into account. You can say *shut off* any time."

#: Sent once, by DM, to somebody in a listening server who has not opted in.
_NOTICE = (
    "Hello — **{server}** has turned on Mylo's listening, which means I can read "
    "what is said in its channels.\n\n"
    "**You are not opted in, so your messages are being dropped.** Nothing about "
    "you is being recorded.\n\n"
    "If you would like me to keep up with your work from the conversation you are "
    "already having, run `/mylo listening on`. I do not keep your messages — I "
    "keep short summaries of interests and project changes, with the dates and "
    "the kind of place they came up, and only after you confirm them do they "
    "affect anything. You can turn this off again at any time."
)


def _reply_to(message: discord.Message) -> str:
    """The id of the message this one answers, or "" — so the backend can tell
    a reply to Mylo (engagement) from something said unprompted (evidence)."""
    reference = getattr(message, "reference", None)
    return str(getattr(reference, "message_id", "") or "")


def _mention_ids(message: discord.Message) -> list[str]:
    """The people a message names, as snowflakes. Bots — Mylo included — are not
    people being talked about. The backend decides what, if anything, to keep."""
    return [
        str(user.id)
        for user in getattr(message, "mentions", [])
        if not getattr(user, "bot", False)
    ][:20]


def _attachment_urls(message: discord.Message) -> list[str]:
    """A pasted file contributes its URL and never its content (OD-01a)."""
    return [attachment.url for attachment in message.attachments][:10]


class ListenCog(commands.Cog, name="Listening"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -- the switch -------------------------------------------------------- #

    @property
    def stage_b(self) -> bool:
        """Whether server-wide listening is on.

        Both halves must be true: the config flag, and the intent actually
        granted. Reading the second from the client rather than assuming it
        means a portal toggle that was never flipped shows up as "off" instead
        of as a silently empty ledger.
        """
        return bool(
            getattr(self.bot.config, "listen_enabled", False)
            and self.bot.intents.message_content
        )

    # -- events ------------------------------------------------------------- #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        try:
            await self._handle(message)
        except Exception:  # noqa: BLE001 — a listener never kills the gateway
            log.exception("could not handle a message")

    async def _handle(self, message: discord.Message) -> None:
        if self.bot.user is not None and message.author.id == self.bot.user.id:
            # Mylo's own line. Carried so a window reads coherently — a question
            # Mylo asked is what makes the next line an answer — never evidence.
            await self._forward(message, from_mylo=True, explicit=False)
            return

        is_dm = message.guild is None
        if is_dm:
            await self._handle_dm(message)
            return

        mentioned = self.bot.user is not None and self.bot.user in message.mentions
        if not mentioned and not self.stage_b:
            # Stage A: without the Message Content intent the body is empty
            # anyway, so there is nothing to carry and nothing to drop.
            return
        await self._forward(message, explicit=mentioned)

    async def _handle_dm(self, message: discord.Message) -> None:
        """A DM is a conversation, not a command. No syntax, no parsing."""
        if message.author.bot:
            return
        outcome = await listening.heard(
            guild_id="",
            message_id=str(message.id),
            text=message.content or "",
            sent_at=message.created_at,
            author_id=str(message.author.id),
            attachment_urls=_attachment_urls(message),
            is_dm=True,
            explicit=True,
            reply_to_id=_reply_to(message),
        )
        if outcome.get("stored"):
            try:
                await message.channel.send(_DM_ACK)
            except discord.HTTPException:
                pass

    async def _forward(
        self, message: discord.Message, *, from_mylo: bool = False, explicit=False
    ) -> None:
        channel = message.channel
        outcome = await listening.heard(
            guild_id=str(message.guild.id) if message.guild else "",
            message_id=str(message.id),
            text=message.content or "",
            sent_at=message.created_at,
            author_id=str(message.author.id),
            place_kind=_place_kind(channel),
            place_id=str(getattr(channel, "id", "")),
            place_label=getattr(channel, "name", "") or "",
            attachment_urls=_attachment_urls(message),
            is_bot=bool(message.author.bot),
            from_mylo=from_mylo,
            explicit=explicit,
            mention_ids=_mention_ids(message),
            reply_to_id=_reply_to(message),
        )
        if outcome.get("notify_member"):
            await self._notify(message)

    async def _notify(self, message: discord.Message) -> None:
        """Tell somebody once, by DM, that a server they are in is listening.

        The backend decides *whether* — it holds the record of who has been told
        — and the gateway does the telling, because only it holds the
        connection. A blocked DM is recorded as undelivered rather than as done,
        so a notice nobody received never reads as one that was.
        """
        server = message.guild.name if message.guild else "this server"
        delivered = True
        try:
            await message.author.send(_NOTICE.format(server=server))
        except discord.HTTPException:
            delivered = False
        await listening.record_notice(
            str(message.guild.id) if message.guild else "",
            str(message.author.id),
            delivered=delivered,
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """A reaction on Mylo's own post — the shortest possible answer.

        Discord delivers these without any privileged intent, which is what
        makes a 👍 on Mylo's question usable in Stage A. What a given emoji
        *means* is Plan 06's; all that happens here is that the reaction is
        carried, marked explicit, so the conversation reads coherently when
        somebody answers without typing.

        Only reactions on Mylo's own messages. A reaction on somebody else's
        post is between them.
        """
        try:
            if self.bot.user is None or payload.user_id == self.bot.user.id:
                return
            if payload.message_author_id != self.bot.user.id:
                return
            await listening.heard(
                guild_id=str(payload.guild_id or ""),
                message_id=f"reaction:{payload.message_id}:{payload.user_id}",
                text=f"reacted {payload.emoji} to what Mylo said",
                sent_at=discord.utils.utcnow(),
                author_id=str(payload.user_id),
                place_kind="dm" if payload.guild_id is None else "channel",
                place_id=str(payload.channel_id),
                explicit=True,
                is_dm=payload.guild_id is None,
            )
        except Exception:  # noqa: BLE001
            log.exception("could not forward a reaction")

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """An edit invalidates the reading, not the record (Plan 01, step 8)."""
        try:
            data = payload.data or {}
            if "content" not in data:
                # An embed resolving, a pin, a flag change — not an edit to what
                # was said.
                return
            await listening.message_edited(
                str(payload.guild_id or payload.channel_id),
                str(payload.message_id),
                data.get("content") or "",
                is_dm=payload.guild_id is None,
            )
        except Exception:  # noqa: BLE001
            log.exception("could not forward an edit")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """A deletion removes the evidence. Not hidden — removed."""
        try:
            await listening.message_deleted(
                str(payload.guild_id or payload.channel_id),
                str(payload.message_id),
                is_dm=payload.guild_id is None,
            )
        except Exception:  # noqa: BLE001
            log.exception("could not forward a deletion")

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(
        self, payload: discord.RawBulkMessageDeleteEvent
    ):
        """A moderator clearing a channel is a deletion of every message in it."""
        try:
            for message_id in payload.message_ids:
                await listening.message_deleted(
                    str(payload.guild_id or payload.channel_id),
                    str(message_id),
                    is_dm=payload.guild_id is None,
                )
        except Exception:  # noqa: BLE001
            log.exception("could not forward a bulk deletion")


def _place_kind(channel) -> str:
    """Which kind of place a message came up in, in the ledger's vocabulary.

    A thread carries its parent so Plan 03 can treat the whole thread as one
    conversation; a forum post's title is an attribution hint. Neither needs a
    binding of any kind.
    """
    if isinstance(channel, discord.Thread):
        parent = getattr(channel, "parent", None)
        if getattr(parent, "type", None) == discord.ChannelType.forum:
            return "forum"
        return "thread"
    if isinstance(channel, discord.DMChannel):
        return "dm"
    return "channel"


#: Refusals for the message action, in the words a person should read.
_ACTION_REFUSALS = {
    "person_not_opted_in": "You haven't turned listening on, so I didn't keep "
    "that. Run `/mylo listening on` first.",
    "speaker_unlinked": "Your Discord isn't connected to Mycelium yet, so I "
    "didn't keep that. Run `/activate` with a code from your profile.",
    "tier_free": "This is part of a paid plan. Nothing was saved.",
    "ambient_disabled": "I'm not set up to remember things yet. Nothing was saved.",
}


async def tell_mylo_about_this(
    interaction: discord.Interaction, message: discord.Message
) -> None:
    """The *Tell Mylo about this* message action.

    **Your own messages, or Mylo's.** The plan allows the action on "any
    message"; that would let one person feed a colleague's words into the
    ledger under their own name, and the colleague may well be somebody who
    never opted in — the exact thing the consent model exists to prevent. So
    the action refuses anybody else's message and says why. Somebody who wants
    to tell Mylo about a colleague's idea can still do so in their own words,
    which is also the honest way to record it: Plan 01's ``subject`` field is
    there precisely because discussing a colleague's idea is not stating your
    own interest.
    """
    await interaction.response.defer(ephemeral=True)
    own = message.author.id == interaction.user.id
    mine = interaction.client.user is not None and (
        message.author.id == interaction.client.user.id
    )
    if not own and not mine:
        await interaction.followup.send(
            "I can only keep your own messages, or mine. Somebody else's words "
            "are theirs — tell me about it in your own words instead, with "
            "`/mylo note`.",
            ephemeral=True,
        )
        return

    outcome = await listening.note(
        str(interaction.user.id),
        message.content or "",
        guild_id=str(interaction.guild_id or ""),
    )
    if outcome.get("stored"):
        await interaction.followup.send(
            "Got it — I'll take that into account.", ephemeral=True
        )
        return
    await interaction.followup.send(
        _ACTION_REFUSALS.get(
            outcome.get("reason", ""),
            "I couldn't record that just now. Nothing was saved.",
        ),
        ephemeral=True,
    )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ListenCog(bot))
    # A context menu cannot live inside an app_commands.Group, so it is
    # registered on the tree directly rather than under /mylo.
    bot.tree.add_command(
        discord.app_commands.ContextMenu(
            name="Tell Mylo about this", callback=tell_mylo_about_this
        )
    )

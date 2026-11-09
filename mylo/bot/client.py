"""Bot bootstrap: intents, extension loading, and the deliberate sync strategy.

Adapted from the ``discord-bot`` skill's reference ``bot.py``. Mylo requests
**no privileged intents** by default; the single exception is Message Content,
asked for only when Stage B listening is configured (``MYLO_LISTEN_ENABLED``),
which ships off. Everything else — DMs, @mentions, the message action — Discord
delivers to any bot without a privileged grant. Command syncing is deliberate:
guild sync (instant) when a dev guild is configured, and never a global sync on
startup — that would burn the rate limit on every reconnect.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from ..config import MyloConfig
from .errors import MyloCommandTree

log = logging.getLogger(__name__)

#: Every cog is an extension exposing ``async def setup(bot)``.
INITIAL_EXTENSIONS: tuple[str, ...] = (
    "mylo.bot.cogs.admin",
    "mylo.bot.cogs.mylo_commands",
    "mylo.bot.cogs.link",
    "mylo.bot.cogs.setup",
    "mylo.bot.cogs.drift",
    "mylo.bot.cogs.listen",
    "mylo.bot.cogs.chat",
    "mylo.bot.cogs.announcements",
)


def _intents(config: MyloConfig) -> discord.Intents:
    """The intents Mylo asks Discord for.

    Default and nothing more, unless Stage B listening is configured. Message
    Content is **privileged**: it is a Developer-Portal toggle until the app
    reaches 10,000 total users, then a review with annual renewal. Requesting
    it without the grant makes the gateway refuse the connection outright, so
    it is asked for only when somebody has said they want server-wide
    listening — and even then Discord, not this flag, decides.
    """
    intents = discord.Intents.default()
    if getattr(config, "listen_enabled", False):
        intents.message_content = True
    return intents


class MyloBot(commands.Bot):
    def __init__(self, config: MyloConfig) -> None:
        self.config = config
        super().__init__(
            # A prefix nobody types keeps the owner-only ``@Mylo sync`` escape
            # hatch usable without exposing a prefix-command surface.
            command_prefix=commands.when_mentioned,
            intents=_intents(config),  # privileged only for Stage B listening
            tree_cls=MyloCommandTree,
            help_command=None,
            allowed_mentions=discord.AllowedMentions.none(),
            owner_ids=set(config.owner_ids) or None,
        )

    async def setup_hook(self) -> None:
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
            except commands.ExtensionError:
                log.exception("failed to load extension %s", extension)
            else:
                log.info("loaded extension %s", extension)

        if self.config.is_dev:
            guild = discord.Object(id=self.config.dev_guild_id)  # type: ignore[arg-type]
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("synced %d command(s) to dev guild %s", len(synced), guild.id)
        else:
            log.info("production mode: skipping automatic sync (use `@Mylo sync global`)")

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info(
            "connected as %s (id=%s) in %d guild(s)",
            self.user,
            self.user.id,
            len(self.guilds),
        )

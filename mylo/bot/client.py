"""Bot bootstrap: intents, extension loading, and the deliberate sync strategy.

Adapted from the ``discord-bot`` skill's reference ``bot.py``. Mylo is a
slash-command bot, so it requests **no privileged intents**. Command syncing is
deliberate: guild sync (instant) when a dev guild is configured, and never a
global sync on startup — that would burn the rate limit on every reconnect.
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
    "mylo.bot.cogs.status",
    "mylo.bot.cogs.link",
)


class MyloBot(commands.Bot):
    def __init__(self, config: MyloConfig) -> None:
        self.config = config
        super().__init__(
            # A prefix nobody types keeps the owner-only ``@Mylo sync`` escape
            # hatch usable without exposing a prefix-command surface.
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),  # no privileged intents
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

"""Bot bootstrap: intents, setup_hook, extension loading, sync strategy, shutdown.

Reference for the `discord-bot` skill. discord.py 2.7.1.

Run with:  python -m bot        (this file being bot/__main__.py + bot/client.py)

The two things people get wrong here:

1. INTENTS. Only request what you use. `message_content`, `members`, and
   `presences` are PRIVILEGED: they must also be toggled on in the Developer
   Portal, and past 100 servers they require review. A slash-command bot needs
   NONE of them. Requesting an intent that is not enabled in the portal makes
   the bot fail to connect with PrivilegedIntentsRequired.

2. SYNCING. Registering a command in Python does not register it with Discord.
   The tree must be synced. Global sync is rate limited and can take up to an
   hour to propagate; guild sync is instant. So: sync to a dev guild while
   developing, and sync globally only on a deliberate action -- NEVER on every
   startup, and never in on_ready (which fires again on every reconnect).
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from .config import Settings, load_settings
from .errors import MyceliumCommandTree

log = logging.getLogger(__name__)

# Every cog is an extension: a module exposing `async def setup(bot)`.
INITIAL_EXTENSIONS: tuple[str, ...] = (
    "bot.cogs.admin",
    "bot.cogs.example",
)


def build_intents() -> discord.Intents:
    """Least-privilege intents.

    `Intents.default()` = everything non-privileged. That is enough for slash
    commands, buttons, modals, and sending messages.
    """
    intents = discord.Intents.default()

    # Turn these on ONLY if a feature needs them, and enable them in the portal too.
    # intents.message_content = True  # to read message text you weren't mentioned in
    # intents.members = True          # to receive member join/leave + full member lists
    # intents.presences = True        # to see online status (rarely worth it)

    return intents


class MyceliumBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        super().__init__(
            # Required by commands.Bot even for a slash-only bot. A prefix that
            # nobody will type keeps the owner-only `!sync` escape hatch usable
            # without exposing a prefix command surface.
            command_prefix=commands.when_mentioned,
            intents=build_intents(),
            # Our CommandTree subclass funnels every app-command error into one handler.
            tree_cls=MyceliumCommandTree,
            help_command=None,
            # Deny-by-default mentions: a bot should never be able to @everyone
            # just because a string it rendered happened to contain it.
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def setup_hook(self) -> None:
        """Runs once, after login but before the gateway connects.

        This -- not on_ready -- is where startup work goes. on_ready fires again
        on every reconnect; setup_hook does not.
        """
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
            except commands.ExtensionError:
                log.exception("failed to load extension %s", extension)
            else:
                log.info("loaded extension %s", extension)

        # Persistent views must be re-registered every boot, or buttons on
        # messages sent before the last restart will silently stop working.
        # from .ui.views import ConfirmDeleteView
        # self.add_view(ConfirmDeleteView())

        if self.settings.is_dev:
            # Dev: mirror the global commands into the test guild and sync there.
            # Instant, and it keeps the real global command set untouched.
            guild = discord.Object(id=self.settings.dev_guild_id)  # type: ignore[arg-type]
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("synced %d command(s) to dev guild %s", len(synced), guild.id)
        else:
            # Prod: do NOT sync here. Command definitions change on deploys, not
            # on restarts. Sync globally from the owner-only `!sync` command (see
            # cogs/admin.py) or a one-shot deploy step.
            log.info("production mode: skipping automatic sync")

    async def on_ready(self) -> None:
        # Informational only. Never put startup logic here -- it re-runs on reconnect.
        assert self.user is not None
        log.info("connected as %s (id=%s) in %d guild(s)", self.user, self.user.id, len(self.guilds))

    async def close(self) -> None:
        """Release your own resources here, then hand off to discord.py."""
        # await self.http_session.close()
        # await self.db_pool.close()
        await super().close()


async def main() -> None:
    settings = load_settings()  # raises ConfigError before we touch the network

    # Sets up sensible colored logging for the `discord` logger hierarchy.
    discord.utils.setup_logging(level=logging.INFO)

    bot = MyceliumBot(settings)

    # `async with` guarantees close() runs on any exit path.
    async with bot:
        await bot.start(settings.token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Ctrl-C is a normal shutdown, not a crash.

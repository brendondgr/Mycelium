"""Owner-only maintenance: sync the command tree and hot-reload cogs.

Adapted from the ``discord-bot`` skill's reference admin cog. ``sync`` lives here,
not in ``setup_hook``, on purpose: a global sync is rate limited and slow to
propagate, so it must be a deliberate act — ``!mylo sync global`` — not something
that fires on every restart. These are prefix commands because you need a way to
register slash commands that does not itself depend on slash commands existing.

The prefix is ``!mylo``, not an @mention: a mention is a question for Mylo chat.
Discord only delivers a server message's text to Mylo when it mentions Mylo
(no Message Content intent), so in a server write ``@Mylo !mylo sync guild``;
in a DM to Mylo plain ``!mylo sync global`` works.

Every ``!mylo`` message gets an answer: a sync says it has started before the
slow call to Discord, then edits in the result; a mistyped command, a person
who is not the owner, or a failed sync is told so instead of being dropped
into the log.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

USAGE = (
    "Owner commands: `!mylo sync global` (or `!mylo global sync`), "
    "`!mylo sync guild`, `!mylo sync clear`, `!mylo reload <extension>`."
)
NOT_OWNER = "Only Mylo's owner can run `!mylo` commands."
_SCOPES = ("global", "guild", "clear")


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context, scope: str = "") -> None:
        """``!mylo sync guild`` (instant, this server) | ``sync global`` | ``sync clear``.
        With no scope: ``global`` in a DM, ``guild`` in a server."""
        scope = scope.lower() or ("guild" if ctx.guild else "global")
        if scope not in _SCOPES:
            await ctx.reply(f"Unknown sync scope `{scope}`. {USAGE}")
            return
        await self._sync(ctx, scope)

    @commands.command(name="global")
    async def global_sync(self, ctx: commands.Context, action: str = "sync") -> None:
        """``!mylo global sync``: the same as ``!mylo sync global``."""
        if action.lower() != "sync":
            await ctx.reply("Did you mean `!mylo global sync`?")
            return
        await self._sync(ctx, "global")

    async def _sync(self, ctx: commands.Context, scope: str) -> None:
        if scope != "global" and ctx.guild is None:
            await ctx.reply("`guild` and `clear` only work inside a server.")
            return
        where = "globally" if scope == "global" else "to this server"
        status = await ctx.reply(
            "Clearing this server's commands…"
            if scope == "clear"
            else f"Syncing commands {where}…"
        )
        try:
            line = await self._run_sync(ctx, scope)
        except discord.HTTPException as exc:
            log.exception("command sync (%s) failed", scope)
            line = f"Sync failed: {exc.status} {exc.text or exc}"
        await status.edit(content=line)

    async def _run_sync(self, ctx: commands.Context, scope: str) -> str:
        tree = self.bot.tree
        if scope == "global":
            synced = await tree.sync()
            names = ", ".join(sorted(f"/{c.name}" for c in synced))
            return (
                f"Synced {len(synced)} command(s) globally: {names}. Discord can "
                "take up to an hour to show them everywhere."
            )
        if scope == "clear":
            tree.clear_commands(guild=ctx.guild)
            await tree.sync(guild=ctx.guild)
            return "Cleared this server's commands."
        tree.copy_global_to(guild=ctx.guild)
        synced = await tree.sync(guild=ctx.guild)
        return f"Synced {len(synced)} command(s) to this server. They show up now."

    @commands.command(name="reload")
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """``!mylo reload mylo.bot.cogs.status`` — hot-reload a cog."""
        try:
            await self.bot.reload_extension(extension)
        except commands.ExtensionError as exc:
            await ctx.reply(f"Failed: `{exc}`")
            return
        await ctx.reply(f"Reloaded `{extension}`.")

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Answer every ``!mylo`` message that did not run, instead of only
        logging it (this listener replaces discord.py's default printer)."""
        if isinstance(error, commands.CommandNotFound):
            line = USAGE
        elif isinstance(error, commands.CheckFailure):
            line = NOT_OWNER
        elif isinstance(error, commands.UserInputError):
            line = f"{error} {USAGE}"
        else:
            log.error("!mylo command failed", exc_info=error)
            line = "That command failed; the bot log has the details."
        try:
            await ctx.reply(line)
        except discord.HTTPException:
            log.warning("could not answer a !mylo command")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))

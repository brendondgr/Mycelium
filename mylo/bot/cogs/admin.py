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
"""

from __future__ import annotations

from discord.ext import commands


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context, scope: str = "guild") -> None:
        """``!mylo sync guild`` (instant, this server) | ``sync global`` | ``sync clear``."""
        await self._sync(ctx, scope.lower())

    @commands.command(name="global")
    async def global_sync(self, ctx: commands.Context, action: str = "sync") -> None:
        """``!mylo global sync``: the same as ``!mylo sync global``."""
        if action.lower() != "sync":
            await ctx.reply("Did you mean `!mylo global sync`?")
            return
        await self._sync(ctx, "global")

    async def _sync(self, ctx: commands.Context, scope: str) -> None:
        tree = self.bot.tree
        if scope == "global":
            synced = await tree.sync()
            await ctx.reply(
                f"Synced {len(synced)} command(s) globally. Propagation can take up "
                "to an hour."
            )
            return
        if ctx.guild is None:
            await ctx.reply("Guild scopes only work inside a server.")
            return
        if scope == "clear":
            tree.clear_commands(guild=ctx.guild)
            await tree.sync(guild=ctx.guild)
            await ctx.reply("Cleared this guild's commands.")
            return
        tree.copy_global_to(guild=ctx.guild)
        synced = await tree.sync(guild=ctx.guild)
        await ctx.reply(f"Synced {len(synced)} command(s) to this guild.")

    @commands.command(name="reload")
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """``!mylo reload mylo.bot.cogs.status`` — hot-reload a cog."""
        try:
            await self.bot.reload_extension(extension)
        except commands.ExtensionError as exc:
            await ctx.reply(f"Failed: `{exc}`")
            return
        await ctx.reply(f"Reloaded `{extension}`.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))

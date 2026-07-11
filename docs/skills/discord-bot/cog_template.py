"""Cog template: copy this to start a new feature area. Plus the admin/sync cog.

Reference for the `discord-bot` skill. discord.py 2.7.1.

A cog is a class of related commands, listeners, and state. An *extension* is the
module that holds it and exposes `async def setup(bot)`. Extensions can be
loaded, unloaded, and reloaded at runtime -- which is why every command belongs
in one, and why you never register commands directly on the bot object.

Structure:
    bot/cogs/<feature>.py   <- one cog per feature area
    bot/services/<feature>.py <- the actual logic; imports NO discord
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from .errors import safe_respond

log = logging.getLogger(__name__)


# ==========================================================================
# TEMPLATE — copy this
# ==========================================================================
class FeatureCog(commands.Cog, name="Feature"):
    """One sentence describing what this feature area does."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Async setup when the cog loads. Open pools, warm caches, start loops."""
        log.info("%s loaded", self.__class__.__name__)

    async def cog_unload(self) -> None:
        """Tear down anything cog_load or __init__ created. Reloads depend on this."""

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Optional: handle this cog's errors before the global tree handler."""
        raise error  # nothing special here — let the tree handle it

    # --- commands ---------------------------------------------------------
    @app_commands.command(name="example", description="Do the thing.")
    @app_commands.describe(thing="Which thing to do.")
    async def example(self, interaction: discord.Interaction, thing: str) -> None:
        await interaction.response.send_message(f"Did {thing}.", ephemeral=True)

    # --- listeners --------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("joined guild %s (%s), %d members", guild.name, guild.id, guild.member_count)


# ==========================================================================
# ADMIN COG — owner-only maintenance. Every bot should have one.
#
# `sync` lives here rather than in setup_hook on purpose: syncing globally is
# rate limited and can take up to an hour to propagate, so it must be a
# DELIBERATE act, not something that fires on every restart/reconnect.
#
# These are prefix commands (`@bot sync`), not slash commands -- deliberately.
# You need a way to register slash commands that does not itself depend on slash
# commands being registered.
# ==========================================================================
class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context, scope: str = "guild") -> None:
        """`@bot sync guild` — instant, this server only. Use while developing.

        `@bot sync global` — every server. Slow to propagate. Run once, on deploy,
        only when the command definitions actually changed.

        `@bot sync clear` — remove this guild's command copies.
        """
        tree = self.bot.tree

        if scope == "global":
            synced = await tree.sync()
            await ctx.reply(f"Synced {len(synced)} command(s) globally. Propagation can take up to an hour.")
            return

        if ctx.guild is None:
            await ctx.reply("Guild scopes only work inside a server.")
            return

        if scope == "clear":
            tree.clear_commands(guild=ctx.guild)
            await tree.sync(guild=ctx.guild)
            await ctx.reply("Cleared this guild's commands.")
            return

        # Default: mirror the global set into this guild and sync. Instant.
        tree.copy_global_to(guild=ctx.guild)
        synced = await tree.sync(guild=ctx.guild)
        await ctx.reply(f"Synced {len(synced)} command(s) to this guild.")

    @commands.command(name="reload")
    async def reload(self, ctx: commands.Context, extension: str) -> None:
        """`@bot reload bot.cogs.feature` — hot-reload a cog without restarting."""
        try:
            await self.bot.reload_extension(extension)
        except commands.ExtensionError as exc:
            await ctx.reply(f"Failed: `{exc}`")
            return
        await ctx.reply(f"Reloaded `{extension}`.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FeatureCog(bot))
    await bot.add_cog(AdminCog(bot))


__all__ = ["AdminCog", "FeatureCog", "safe_respond", "setup"]

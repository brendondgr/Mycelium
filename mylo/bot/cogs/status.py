"""The ``/mylo`` command group.

* ``health`` / ``lastrun`` — is Mylo up, and how did the last daily run go? These
  read the shared run-state file (:mod:`mylo.runstate`) — a plain file read, so they
  answer within the 3-second window without deferring.
* ``status`` / ``setup`` — the Discord-link commands. These touch Mycelium's ORM
  (via :mod:`mylo.linking` → ``apps.integrations.services.resolve``), so they defer
  first and follow up.

Everything is ephemeral: status is for the person asking, not channel noise.
"""

from __future__ import annotations

import socket

import discord
from discord import app_commands
from discord.ext import commands

from ... import linking
from ...runstate import read_run_state


class StatusCog(commands.Cog, name="Status"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    mylo = app_commands.Group(name="mylo", description="Mylo status and controls.")

    @mylo.command(name="health", description="Is Mylo online, and how did the last run go?")
    async def health(self, interaction: discord.Interaction) -> None:
        config = getattr(self.bot, "config", None)
        channel_set = bool(getattr(config, "error_channel_id", None))
        state = read_run_state()

        lines = [f"\U0001F7E2 Mylo is online on **{socket.gethostname()}**."]
        lines.append(
            f"Error channel: {'configured' if channel_set else '**not set**'}."
        )
        if state is None:
            lines.append("Last daily run: none recorded yet.")
        elif state.get("ok"):
            lines.append(f"Last daily run: ✅ ok ({state.get('finished_at', '?')}).")
        else:
            lines.append(
                f"Last daily run: ❌ failed at "
                f"`{state.get('failed_stage', '?')}` ({state.get('finished_at', '?')})."
            )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @mylo.command(name="lastrun", description="Details of the most recent daily run.")
    async def lastrun(self, interaction: discord.Interaction) -> None:
        state = read_run_state()
        if state is None:
            await interaction.response.send_message(
                "No daily run has been recorded yet.", ephemeral=True
            )
            return

        ok = bool(state.get("ok"))
        embed = discord.Embed(
            title="Last daily run",
            colour=discord.Colour.green() if ok else discord.Colour.red(),
        )
        embed.add_field(name="Outcome", value="ok" if ok else "failed", inline=True)
        embed.add_field(name="Finished", value=str(state.get("finished_at", "?")), inline=True)
        embed.add_field(name="Host", value=str(state.get("host", "?")), inline=True)
        embed.add_field(
            name="Scrape ran", value="yes" if state.get("scrape_ran") else "no", inline=True
        )
        stages = ", ".join(state.get("stages_run") or []) or "—"
        embed.add_field(name="Stages completed", value=stages, inline=False)
        if state.get("failed_stage"):
            embed.add_field(
                name="Failed stage",
                value=f"{state['failed_stage']} (exit {state.get('exit_code', '?')})",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @mylo.command(
        name="status", description="Am I linked to Mycelium, and is my link healthy?"
    )
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        _, message = await linking.status(str(interaction.user.id))
        await interaction.followup.send(message, ephemeral=True)

    @mylo.command(
        name="setup",
        description="Confirm this server's link to your Mycelium lab (managers).",
    )
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id else ""
        _, message = await linking.setup_guild(str(interaction.user.id), guild_id)
        await interaction.followup.send(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatusCog(bot))

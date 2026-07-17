"""``/activate`` — the context-aware linking command.

Two jobs, one command:

* ``/activate code:<XXXX-XXXX>`` → **Path B identity linking** (bind the caller's
  own Discord account to their Mycelium profile).
* ``/activate lab:<lab>`` → **server activation** (connect *this server* to a lab
  the caller administers) so Mylo can post that lab's reminders/announcements here.

Every branch replies **ephemerally** (success, expiry, bad code, wrong channel,
lockout, denial): the invocation is visible only to the invoker, so a code is never
shoulder-surfable and an error never echoes it into the channel. Policy (channel
gate, lockout, lab-manager authority, the Mylo-server add-on) lives in
:mod:`mylo.linking` → ``apps.integrations``; the bot holds none of its own.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ... import linking


class LinkCog(commands.Cog, name="Link"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="activate",
        description="Link your account (code:) or connect this server to a lab (lab:).",
    )
    @app_commands.describe(
        code="The XXXX-XXXX code from your Mycelium profile (links your account).",
        lab="A lab you administer — connects this server to it (leave blank to see options).",
    )
    @app_commands.guild_only()
    async def activate(
        self,
        interaction: discord.Interaction,
        code: str | None = None,
        lab: str | None = None,
    ) -> None:
        # Ephemeral from the very first response, in every branch.
        await interaction.response.defer(ephemeral=True)
        _, message = await linking.activate(
            str(interaction.user.id),
            code=code,
            lab_slug=lab,
            guild_id=str(interaction.guild_id) if interaction.guild_id else "",
            guild_name=interaction.guild.name if interaction.guild else "",
            channel_id=str(interaction.channel_id) if interaction.channel_id else "",
        )
        await interaction.followup.send(message, ephemeral=True)

    @activate.autocomplete("lab")
    async def _activate_lab_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices = await linking.managed_lab_choices(
            str(interaction.user.id), current or ""
        )
        return [app_commands.Choice(name=name, value=slug) for name, slug in choices]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LinkCog(bot))

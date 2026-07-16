"""``/activate`` — Path B code redemption from the hub server.

Every branch replies **ephemerally** (success, expiry, bad code, wrong channel,
lockout): with an ephemeral reply the invocation text is visible only to the
invoker, so the code isn't shoulder-surfable, and an error reply never echoes the
code into the channel. The channel gate and lockout live in
:mod:`mylo.linking` → ``apps.integrations`` so the bot holds no policy of its own.
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
        name="activate", description="Redeem a Mycelium activation code."
    )
    @app_commands.describe(code="The XXXX-XXXX code from your Mycelium profile.")
    @app_commands.guild_only()
    async def activate(self, interaction: discord.Interaction, code: str) -> None:
        # Ephemeral from the very first response, in every branch.
        await interaction.response.defer(ephemeral=True)
        _, message = await linking.activate(
            str(interaction.user.id),
            code,
            channel_id=str(interaction.channel_id) if interaction.channel_id else "",
        )
        await interaction.followup.send(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LinkCog(bot))

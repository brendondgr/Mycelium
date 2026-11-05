"""``/activate``, ``/activate-lab`` and ``/activate-department`` — the linking commands.

* ``/activate code:<XXXX-XXXX>`` → **Path B identity linking** (bind the caller's
  own Discord account to their Mycelium profile). Usable in **any** server Mylo is
  already in — nobody has to join the Mycelium hub to link an account. Only the hub
  itself still funnels the command into its ``#activation`` channel.
* ``/activate-lab code:<XXXXX-XXXXX>`` → **Path C server activation** (connect *this
  server* to the lab that issued the 10-digit code on the website) so Mylo can post
  that lab's reminders/announcements here. No linked identity required — the
  manager-issued code carries the authority.
* ``/activate-department code:<XXXXX-XXXXX>`` → the same for a department. A server
  can hold a department and several labs, each its own binding.

Every branch replies **ephemerally** (success, expiry, bad code, wrong channel,
lockout, conflict): the invocation is visible only to the invoker, so a code is never
shoulder-surfable and an error never echoes it into the channel. Policy (channel
gate, lockout, bindings) lives in :mod:`mylo.linking`
→ ``apps.integrations``; the bot holds none of its own.
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
        description="Link your own Discord account to Mycelium with a code.",
    )
    @app_commands.describe(
        code="The XXXX-XXXX code from your Mycelium profile.",
    )
    @app_commands.guild_only()
    async def activate(
        self,
        interaction: discord.Interaction,
        code: str,
    ) -> None:
        # Ephemeral from the very first response, in every branch.
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        # Presence, not membership lists: the cache is populated by the `guilds`
        # intent, so a hit means Mylo is installed in the server the command came
        # from — and a guild command means the caller is in it too.
        mylo_present = bool(guild_id) and self.bot.get_guild(guild_id) is not None
        _, message = await linking.activate(
            str(interaction.user.id),
            code=code,
            channel_id=str(interaction.channel_id) if interaction.channel_id else "",
            guild_id=str(guild_id) if guild_id else "",
            mylo_present=mylo_present,
        )
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(
        name="activate-lab",
        description="Connect this server to a lab using its 10-digit code.",
    )
    @app_commands.describe(
        code="The XXXXX-XXXXX code from the lab's settings in Mycelium (Activate Lab).",
    )
    @app_commands.guild_only()
    async def activate_lab(
        self,
        interaction: discord.Interaction,
        code: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        _, message = await linking.activate_lab(
            str(interaction.user.id),
            code=code,
            guild_id=str(interaction.guild_id) if interaction.guild_id else "",
            guild_name=interaction.guild.name if interaction.guild else "",
        )
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(
        name="activate-department",
        description="Connect this server to a department using its 10-digit code.",
    )
    @app_commands.describe(
        code="The XXXXX-XXXXX code from the department's settings in Mycelium.",
    )
    @app_commands.guild_only()
    async def activate_department(
        self,
        interaction: discord.Interaction,
        code: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        _, message = await linking.activate_department(
            str(interaction.user.id),
            code=code,
            guild_id=str(interaction.guild_id) if interaction.guild_id else "",
            guild_name=interaction.guild.name if interaction.guild else "",
        )
        await interaction.followup.send(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LinkCog(bot))

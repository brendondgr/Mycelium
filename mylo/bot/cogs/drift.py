"""Notice, immediately, when Discord changes underneath us.

Two events, both available on the ``guilds`` intent the bot already requests:

* ``on_guild_remove`` — the bot was kicked or the server was deleted.
* ``on_guild_channel_delete`` — a channel vanished, possibly one Mylo posts to.

Neither replaces the nightly reconcile sweep, and the sweep does not make these
redundant. Events are lost across restarts, deploys and gateway disconnects; the
sweep is up to a day stale. Together they cover each other, which is why the brief
asks for both.

**Not listening for members leaving.** ``on_member_remove`` requires the privileged
Server Members intent — a Developer-Portal toggle plus, past 100 guilds, Discord's
verification review. That is an external approval dependency, not a code change, so
member departure is detected REST-side in the reconcile sweep instead. Real-time
detection there would be nice; it is not worth blocking this on a review queue.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from ... import linking

log = logging.getLogger(__name__)


class DriftCog(commands.Cog, name="Drift"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Mylo left or was removed. Stop delivering; keep everything else."""
        try:
            await linking.guild_removed(str(guild.id))
        except Exception:  # noqa: BLE001 — a listener must never kill the gateway
            log.exception("could not record guild removal for %s", guild.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        """A channel is gone. Unbind it if it was one of ours.

        Most deletions are of channels Mylo never used, so this is a cheap lookup
        that usually finds nothing — which is exactly why it is safe to run on every
        deletion rather than polling.
        """
        try:
            await linking.channel_deleted(
                str(channel.guild.id), str(channel.id)
            )
        except Exception:  # noqa: BLE001
            log.exception("could not record channel deletion for %s", channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DriftCog(bot))

"""Background work: discord.ext.tasks, and knowing when NOT to use it.

Reference for the `discord-bot` skill. discord.py 2.7.1.

`tasks` is an in-process scheduler. It is the right tool for lightweight,
best-effort, recurring work inside the bot: a daily digest post, a cache refresh,
a heartbeat.

It is NOT a job queue. It does not survive a restart, does not retry, does not
persist, and does not fan out across workers. Anything durable belongs in a real
worker (Celery/RQ), with the bot acting only as the delivery surface -- or, even
better, with the worker posting via a WEBHOOK so it needs no bot process at all.

Two mandatory habits:
  * @loop.before_loop -> await bot.wait_until_ready(), or the first tick fires
    against a half-connected client and blows up.
  * @loop.error, or the first unhandled exception silently kills the loop
    forever and nobody notices for a week.
"""

from __future__ import annotations

import datetime
import logging

import discord
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

# Wall-clock schedules must be timezone-aware, or the loop drifts with the host.
NINE_AM_UTC = datetime.time(hour=9, minute=0, tzinfo=datetime.timezone.utc)


class DigestCog(commands.Cog):
    def __init__(self, bot: commands.Bot, channel_id: int) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self.post_digest.start()  # start the loop when the cog loads

    async def cog_unload(self) -> None:
        # Extensions get reloaded. Cancel the loop or you'll end up with two.
        self.post_digest.cancel()

    # `time=` -> runs at a wall-clock time. `hours=`/`minutes=`/`seconds=` ->
    # runs on an interval from start. Use one or the other, not both.
    @tasks.loop(time=NINE_AM_UTC)
    async def post_digest(self) -> None:
        channel = self.bot.get_channel(self.channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            log.warning("digest channel %s is missing or not messageable", self.channel_id)
            return

        items = await fetch_new_items()
        if not items:
            return  # silence is better than "nothing new today" every day

        embed = discord.Embed(
            title="Today's digest",
            description="\n".join(f"• {item}" for item in items[:10]),
            colour=discord.Colour.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        await channel.send(embed=embed)

    @post_digest.before_loop
    async def before_post_digest(self) -> None:
        # REQUIRED. Without this the first tick can run before the cache is
        # populated and before the gateway is connected.
        await self.bot.wait_until_ready()

    @post_digest.error
    async def on_post_digest_error(self, error: BaseException) -> None:
        # REQUIRED. An unhandled exception in a loop cancels it permanently.
        log.exception("digest loop failed; it will not run again until restart", exc_info=error)


# --------------------------------------------------------------------------
# Delivering from OUTSIDE the bot process.
#
# When a Celery worker (or a cron job, or a deploy script) needs to announce
# something in Discord, it does NOT need to talk to the bot, hold a gateway
# connection, or share the token. It posts to a WEBHOOK: one HTTP call, no
# gateway, no bot process required.
#
# Create the webhook once (Channel Settings -> Integrations -> Webhooks) and
# store the URL as a secret alongside the token.
# --------------------------------------------------------------------------
async def post_via_webhook(webhook_url: str, message: str) -> None:
    import aiohttp

    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        await webhook.send(
            content=message,
            username="Mycelium",
            # A webhook posting arbitrary text must not be able to ping the server.
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def fetch_new_items() -> list[str]:
    return []


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DigestCog(bot, channel_id=0))

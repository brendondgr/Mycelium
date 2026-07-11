"""The interaction response lifecycle. The single most important file here.

Reference for the `discord-bot` skill. discord.py 2.7.1.

    interaction arrives
            |
            +-- fast (< 3s)?
            |     `-- await interaction.response.send_message(...)    <- THE one response
            |
            `-- slow (> 3s)?
                  +-- await interaction.response.defer(thinking=True) <- THE one response
                  |        (shows "thinking..."; buys you 15 minutes)
                  +-- ... do the work ...
                  `-- await interaction.followup.send(...)            <- as many as you like

Three numbers govern everything:

  3 SECONDS   to acknowledge. Miss it and the user gets a permanent red
              "The application did not respond". The interaction is dead; you
              cannot recover it. There is no retry.

  1 RESPONSE  `interaction.response.*` may be called exactly once. A second call
              raises InteractionResponded. Everything after goes through
              `interaction.followup`.

  15 MINUTES  the interaction token's lifetime. After that, followups and edits
              fail. Work that can exceed 15 minutes must not report back through
              the interaction -- hand it to a job queue and deliver the result
              as a channel message, a DM, or a webhook.
"""

from __future__ import annotations

import asyncio
import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class ResponsesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ----------------------------------------------------------------------
    # FAST: answer directly. No defer needed.
    # ----------------------------------------------------------------------
    @app_commands.command(name="fast", description="Something that returns immediately.")
    async def fast(self, interaction: discord.Interaction) -> None:
        # ephemeral=True -> only the invoking user sees it. Default to this for
        # errors, confirmations, personal data, and admin actions.
        await interaction.response.send_message("Done.", ephemeral=True)

    # ----------------------------------------------------------------------
    # SLOW: defer FIRST, then work, then follow up.
    # ----------------------------------------------------------------------
    @app_commands.command(name="slow", description="Something that takes a while.")
    async def slow(self, interaction: discord.Interaction) -> None:
        # thinking=True shows the animated "Bot is thinking..." state.
        # NOTE: ephemerality is decided HERE, at defer time -- not at followup
        # time. You cannot defer publicly and then answer privately.
        await interaction.response.defer(thinking=True, ephemeral=True)

        result = await do_slow_work()  # anything up to ~15 minutes

        await interaction.followup.send(f"Finished: {result}")

    # ----------------------------------------------------------------------
    # PROGRESS: edit the deferred message as the work advances.
    # ----------------------------------------------------------------------
    @app_commands.command(name="scan", description="Long job with progress updates.")
    async def scan(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        sources = ["arXiv", "PubMed", "bioRxiv"]
        for index, source in enumerate(sources, start=1):
            await interaction.edit_original_response(
                content=f"Scanning **{source}** ({index}/{len(sources)})…"
            )
            await asyncio.sleep(1)  # stand-in for real work

        await interaction.edit_original_response(content="Scan complete — 12 new items.")

    # ----------------------------------------------------------------------
    # TOO SLOW: > 15 minutes. Do NOT try to answer through the interaction.
    # ----------------------------------------------------------------------
    @app_commands.command(name="rebuild", description="Kick off a long background job.")
    async def rebuild(self, interaction: discord.Interaction) -> None:
        # Acknowledge immediately and get out. The interaction's job is done.
        await interaction.response.send_message(
            "Started. I'll post here when it's finished — this usually takes ~40 minutes.",
            ephemeral=True,
        )

        channel = interaction.channel
        user_id = interaction.user.id

        # Hand off. In production this is a Celery/RQ task, not a bare
        # create_task -- a bare task dies with the process. Capture the CHANNEL
        # (which is durable), not the interaction (which expires).
        async def _run() -> None:
            try:
                await do_very_slow_work()
            except Exception:
                log.exception("rebuild job failed")
                return
            if isinstance(channel, discord.abc.Messageable):
                await channel.send(f"<@{user_id}> your rebuild finished.")

        asyncio.create_task(_run())  # illustrative only

    # ----------------------------------------------------------------------
    # BLOCKING WORK: never run it on the event loop.
    # ----------------------------------------------------------------------
    @app_commands.command(name="crunch", description="CPU-bound or sync-IO work.")
    async def crunch(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        # A blocking call here -- requests.get, time.sleep, a sync DB driver, a
        # tight CPU loop -- freezes the WHOLE bot: heartbeats stop, the gateway
        # disconnects, every user's command fails. Push it off the loop.
        result = await asyncio.to_thread(blocking_computation, 10_000_000)

        await interaction.followup.send(f"Result: {result}")

    # ----------------------------------------------------------------------
    # OVERSIZED OUTPUT: respect the limits or Discord rejects the message.
    #   content: 2000 chars   |   embed: 6000 chars total, 4096 description
    # ----------------------------------------------------------------------
    @app_commands.command(name="report", description="Send a possibly-large report.")
    async def report(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        body = await build_report()

        # Embed description caps at 4096 chars (and 6000 across the whole embed).
        if len(body) <= 4000:
            await interaction.followup.send(embed=discord.Embed(description=body))
            return

        # Too big to render: send it as a file rather than truncating away meaning.
        payload = body.encode("utf-8")

        # filesize_limit reflects THIS guild's actual ceiling (it rises with
        # boost tier). Check it instead of hardcoding 8 MB.
        if len(payload) > interaction.filesize_limit:
            await interaction.followup.send("The report is too large to upload here.")
            return

        await interaction.followup.send(
            "The report is too long to display — attached instead.",
            file=discord.File(io.BytesIO(payload), filename="report.md"),
        )


# --------------------------------------------------------------------------
# stand-ins
# --------------------------------------------------------------------------
async def do_slow_work() -> str:
    await asyncio.sleep(5)
    return "ok"


async def do_very_slow_work() -> None:
    await asyncio.sleep(60)


async def build_report() -> str:
    return "…"


def blocking_computation(n: int) -> int:
    return sum(range(n))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ResponsesCog(bot))

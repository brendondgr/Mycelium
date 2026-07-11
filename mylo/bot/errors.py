"""One funnel for every app-command error — a sentence for the user, a trace for the log.

Adapted from the ``discord-bot`` skill's reference ``errors.py``. Two rules:

1. The user gets a sentence. The logs get the traceback.
2. An error handler never knows whether the command deferred before it failed, so
   it must check ``interaction.response.is_done()`` — ``safe_respond`` does that.

Do NOT write retry loops around 429s; discord.py's HTTP layer already respects
``Retry-After`` per bucket.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands

log = logging.getLogger(__name__)


class UserFacingError(app_commands.AppCommandError):
    """An error whose message is safe and useful to show the user verbatim."""


async def safe_respond(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
) -> None:
    """Reply whether or not the interaction was already responded to."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
    except discord.HTTPException:
        log.warning(
            "could not deliver error message for interaction %s",
            interaction.id,
            exc_info=True,
        )


def humanize(error: app_commands.AppCommandError) -> str:
    if isinstance(error, UserFacingError):
        return str(error)
    if isinstance(error, app_commands.CommandOnCooldown):
        return f"Slow down — try again in {error.retry_after:.0f}s."
    if isinstance(error, app_commands.MissingPermissions):
        return "You don't have permission to do that."
    if isinstance(error, app_commands.CheckFailure):
        return "You can't use that command here."
    # Unknown = a bug. Say so honestly; log the real thing.
    return "Something went wrong on my end. It's been logged and I'll look into it."


class MyloCommandTree(app_commands.CommandTree):
    """The single funnel for every app-command failure in the bot."""

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original = (
            error.original
            if isinstance(error, app_commands.CommandInvokeError)
            else error
        )
        command = interaction.command.qualified_name if interaction.command else "<unknown>"
        if isinstance(original, UserFacingError | app_commands.CheckFailure):
            log.info("command %s rejected for %s: %s", command, interaction.user.id, original)
        else:
            log.exception(
                "unhandled error in command %s (user=%s)",
                command,
                interaction.user.id,
                exc_info=original,
            )
        await safe_respond(interaction, humanize(error))

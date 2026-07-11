"""Error handling: one funnel, no tracebacks in chat.

Reference for the `discord-bot` skill. discord.py 2.7.1.

Two rules:

1. The user gets a sentence. The logs get the traceback.
2. An error handler NEVER knows whether the command deferred before it blew up.
   So it must check `interaction.response.is_done()` and pick response vs
   followup accordingly. `safe_respond` below does that; use it everywhere.

Do NOT write retry loops around 429 (rate limit) errors. discord.py's HTTP layer
already respects Retry-After and queues per bucket. Hand-rolled retries are how
bots hit the 10,000-invalid-requests-per-10-minutes limit and earn a 24h IP ban.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Expected, user-facing failures. Raise these from service code.
# --------------------------------------------------------------------------
class UserFacingError(app_commands.AppCommandError):
    """An error whose message is safe and useful to show the user verbatim."""


class NotFoundError(UserFacingError):
    def __init__(self, what: str) -> None:
        super().__init__(f"I couldn't find {what}.")


# --------------------------------------------------------------------------
# The safe responder
# --------------------------------------------------------------------------
async def safe_respond(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
) -> None:
    """Reply regardless of whether the interaction was already responded to.

    Swallows the failure if the interaction is dead (expired token, already
    consumed) -- there is nothing useful to do at that point, and raising from
    an error handler just produces a second, noisier error.
    """
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
    except discord.HTTPException:
        log.warning("could not deliver error message for interaction %s", interaction.id, exc_info=True)


# --------------------------------------------------------------------------
# Map a raised error to a human sentence
# --------------------------------------------------------------------------
def humanize(error: app_commands.AppCommandError) -> str:
    if isinstance(error, UserFacingError):
        return str(error)

    if isinstance(error, app_commands.CommandOnCooldown):
        return f"Slow down — try again in {error.retry_after:.0f}s."

    if isinstance(error, app_commands.MissingPermissions):
        missing = ", ".join(error.missing_permissions)
        return f"You need the following permission(s) to do that: {missing}."

    if isinstance(error, app_commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions)
        return f"I'm missing the following permission(s) in this server: {missing}."

    if isinstance(error, app_commands.MissingRole | app_commands.MissingAnyRole):
        return "You don't have the role required to use this command."

    if isinstance(error, app_commands.NoPrivateMessage):
        return "That command only works inside a server."

    if isinstance(error, app_commands.TransformerError):
        return f"`{error.value}` isn't a valid value for that option."

    if isinstance(error, app_commands.CheckFailure):
        return "You can't use that command here."

    # Unknown = a bug. Say so honestly, and log the real thing.
    return "Something went wrong on my end. It's been logged and I'll look into it."


# --------------------------------------------------------------------------
# The tree: a single funnel for every app-command error in the bot
# --------------------------------------------------------------------------
class MyceliumCommandTree(app_commands.CommandTree):
    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        # Unwrap: an exception raised inside a command body arrives wrapped.
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error

        command = interaction.command.qualified_name if interaction.command else "<unknown>"

        if isinstance(original, UserFacingError | app_commands.CheckFailure):
            # Expected. Not worth a traceback.
            log.info("command %s rejected for user %s: %s", command, interaction.user.id, original)
        else:
            log.exception(
                "unhandled error in command %s (user=%s guild=%s)",
                command,
                interaction.user.id,
                interaction.guild_id,
                exc_info=original,
            )

        await safe_respond(interaction, humanize(error))


# --------------------------------------------------------------------------
# Per-cog handling (optional). Runs before the tree handler for that cog's
# commands. Useful when one feature area needs bespoke messaging.
# --------------------------------------------------------------------------
#
#   class MyCog(commands.Cog):
#       async def cog_app_command_error(
#           self,
#           interaction: discord.Interaction,
#           error: app_commands.AppCommandError,
#       ) -> None:
#           if isinstance(error, SomeCogSpecificError):
#               await safe_respond(interaction, "...")
#               return
#           raise error  # let the tree handler deal with it

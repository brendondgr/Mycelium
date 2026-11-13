"""Entry point: ``python -m mylo.bot``.

Loads and validates config (raises before touching the network), sets up
discord.py's logging, and runs the gateway client until interrupted. With no
bot token it says so and exits cleanly, so a service manager with
``Restart=always`` does not restart it in a loop.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import discord

from ..config import load_config
from .client import MyloBot

log = logging.getLogger("mylo.bot")

NO_TOKEN = "no DISCORD_API_KEY in .env-mylo; Mylo stays out of Discord."


async def _run() -> None:
    config = load_config().require_bot()  # ConfigError before we connect
    discord.utils.setup_logging(level=logging.INFO)
    bot = MyloBot(config)
    async with bot:  # guarantees close() on any exit path
        await bot.start(config.token)


def main() -> None:
    if not load_config().token:
        print(f"mylo: {NO_TOKEN}", flush=True)
        sys.exit(0)
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass  # Ctrl-C / SIGINT is a normal shutdown, not a crash.


if __name__ == "__main__":
    main()

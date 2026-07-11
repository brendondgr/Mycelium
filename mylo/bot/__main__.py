"""Entry point: ``python -m mylo.bot``.

Loads and validates config (raises before touching the network), sets up
discord.py's logging, and runs the gateway client until interrupted.
"""

from __future__ import annotations

import asyncio
import logging

import discord

from ..config import load_config
from .client import MyloBot

log = logging.getLogger("mylo.bot")


async def _run() -> None:
    config = load_config().require_bot()  # ConfigError before we connect
    discord.utils.setup_logging(level=logging.INFO)
    bot = MyloBot(config)
    async with bot:  # guarantees close() on any exit path
        await bot.start(config.token)


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass  # Ctrl-C / SIGINT is a normal shutdown, not a crash.


if __name__ == "__main__":
    main()

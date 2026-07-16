"""The Mylo bot: constructs offline, and its cogs register the expected commands.

No gateway connection is made — we only build the client and load the extensions,
which is enough to catch import errors, a bad ``tree_cls``, or a missing command.
"""

from __future__ import annotations

import unittest

from mylo.bot.client import INITIAL_EXTENSIONS, MyloBot
from mylo.bot.cogs.status import StatusCog
from mylo.bot.errors import MyloCommandTree
from mylo.config import MyloConfig


def _config() -> MyloConfig:
    return MyloConfig(token="x", error_channel_id=1)


class BotConstructionTests(unittest.TestCase):
    def test_bot_builds_without_network_and_uses_our_tree(self) -> None:
        bot = MyloBot(_config())
        self.assertIsInstance(bot.tree, MyloCommandTree)
        self.assertEqual(bot.config.error_channel_id, 1)

    def test_status_group_exposes_expected_subcommands(self) -> None:
        names = {command.name for command in StatusCog.mylo.commands}
        # health/lastrun (observability) + status/setup (Discord linking).
        self.assertEqual(names, {"health", "lastrun", "status", "setup"})


class BotExtensionLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_extensions_load_and_register_the_mylo_group(self) -> None:
        bot = MyloBot(_config())
        try:
            for extension in INITIAL_EXTENSIONS:
                await bot.load_extension(extension)
            top_level = {command.name for command in bot.tree.get_commands()}
            self.assertIn("mylo", top_level)
            self.assertIn("activate", top_level)  # Path B redemption
        finally:
            await bot.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

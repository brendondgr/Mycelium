"""The Mylo bot: constructs offline, and its cogs register the expected commands.

No gateway connection is made — we only build the client and load the extensions,
which is enough to catch import errors, a bad ``tree_cls``, or a missing command.
"""

from __future__ import annotations

import unittest

from mylo.bot.client import INITIAL_EXTENSIONS, MyloBot
from mylo.bot.cogs.mylo_commands import MyloCog
from mylo.bot.errors import MyloCommandTree
from mylo.config import MyloConfig


def _config() -> MyloConfig:
    return MyloConfig(token="x", error_channel_id=1)


class BotConstructionTests(unittest.TestCase):
    def test_bot_builds_without_network_and_uses_our_tree(self) -> None:
        bot = MyloBot(_config())
        self.assertIsInstance(bot.tree, MyloCommandTree)
        self.assertEqual(bot.config.error_channel_id, 1)

    def test_mylo_group_exposes_every_subcommand(self) -> None:
        names = {command.name for command in MyloCog.mylo.commands}
        # Observability (health/lastrun), link health (status), research
        # (search/digest/saves), reminder control (snooze/cancel), listening
        # (listening/note) and filling the opportunity forums (populate). All in one cog because discord.py cannot share an
        # app_commands.Group across cogs. Channel setup stays the top-level
        # /setup command, and listening's *server* switch lives there too —
        # `/mylo listening` is personal, and nobody should have to ask a manager
        # for permission to opt out.
        self.assertEqual(
            names,
            {
                "health",
                "lastrun",
                "status",
                "search",
                "digest",
                "saves",
                "snooze",
                "cancel",
                "listening",
                "note",
                "populate",
            },
        )


class BotExtensionLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_extensions_load_and_register_the_commands(self) -> None:
        bot = MyloBot(_config())
        try:
            for extension in INITIAL_EXTENSIONS:
                await bot.load_extension(extension)
            commands = {command.name: command for command in bot.tree.get_commands()}
            self.assertIn("mylo", commands)
            # /activate links your own account (code only); /activate-lab connects
            # this server (code only); /setup configures the channels.
            self.assertEqual({p.name for p in commands["activate"].parameters}, {"code"})
            self.assertEqual(
                {p.name for p in commands["activate-lab"].parameters}, {"code"}
            )
            self.assertIn("setup", commands)
            # Every /mylo subcommand reaches the tree, not just the group itself.
            group = commands["mylo"]
            self.assertIn("search", {c.name for c in group.commands})
            # /mylo populate: a bounded count, and a target only for servers that
            # hold more than one lab or department.
            populate = next(c for c in group.commands if c.name == "populate")
            params = {p.name: p for p in populate.parameters}
            self.assertEqual(set(params), {"count", "target"})
            self.assertEqual((params["count"].min_value, params["count"].max_value),
                             (1, 10))
            self.assertFalse(params["target"].required)
            self.assertTrue(params["target"].autocomplete)
        finally:
            await bot.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

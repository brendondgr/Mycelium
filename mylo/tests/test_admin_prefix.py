"""``!mylo …`` is an owner command and never a question for Mylo chat."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from mylo import chat
from mylo.bot.client import INITIAL_EXTENSIONS, MyloBot, _command_prefix
from mylo.config import MyloConfig

BOT = SimpleNamespace(id=42)


def _message(content: str, *, guild=True, mentions=()):
    return SimpleNamespace(
        content=content,
        author=SimpleNamespace(id=7, bot=False),
        webhook_id=None,
        guild=SimpleNamespace(id=1) if guild else None,
        mentions=list(mentions),
        role_mentions=[],
        reference=None,
    )


class AdminPrefixTests(unittest.TestCase):
    def test_the_prefix_matches_plain_and_after_a_mention(self) -> None:
        self.assertEqual(chat.admin_prefix("!mylo sync global"), "!mylo ")
        self.assertEqual(chat.admin_prefix("!Mylo global sync"), "!Mylo ")
        self.assertEqual(chat.admin_prefix("<@42> !mylo sync"), "<@42> !mylo ")
        self.assertEqual(chat.admin_prefix("<@&9>  !MYLO reload x"), "<@&9>  !MYLO ")

    def test_ordinary_text_is_not_a_command(self) -> None:
        for text in ("sync global", "<@42> sync global", "!mylosync", "hi !mylo", ""):
            self.assertEqual(chat.admin_prefix(text), "", text)

    def test_a_command_is_never_a_chat_question(self) -> None:
        dm = _message("!mylo sync global", guild=False)
        self.assertEqual(chat.route(dm, BOT).kind, "none")
        mentioned = _message("<@42> !mylo sync guild", mentions=[BOT])
        self.assertEqual(chat.route(mentioned, BOT).kind, "none")
        question = _message("<@42> sync global?", mentions=[BOT])
        self.assertEqual(chat.route(question, BOT).kind, "chat")

    def test_the_bot_uses_the_same_prefix(self) -> None:
        self.assertEqual(_command_prefix(None, _message("!mylo sync")), ["!mylo "])
        self.assertEqual(_command_prefix(None, _message("<@42> sync")), [])


class AdminCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_and_global_are_registered(self) -> None:
        bot = MyloBot(MyloConfig(token="x", error_channel_id=1))
        for extension in INITIAL_EXTENSIONS:
            await bot.load_extension(extension)
        self.assertIsNotNone(bot.get_command("sync"))
        self.assertIsNotNone(bot.get_command("global"))
        self.assertIsNotNone(bot.get_command("reload"))


if __name__ == "__main__":
    unittest.main()

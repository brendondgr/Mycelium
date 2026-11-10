"""``!mylo …`` is an owner command and never a question for Mylo chat."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import discord
from discord.ext import commands

from mylo import chat
from mylo.bot.client import INITIAL_EXTENSIONS, MyloBot, _command_prefix
from mylo.bot.cogs.admin import NOT_OWNER, USAGE, AdminCog
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



class FakeStatus:
    def __init__(self, content):
        self.content = content

    async def edit(self, *, content):
        self.content = content


class FakeCtx:
    def __init__(self, *, guild=None):
        self.guild = guild
        self.replies: list[FakeStatus] = []

    async def reply(self, content):
        status = FakeStatus(content)
        self.replies.append(status)
        return status


class FakeTree:
    def __init__(self, *, fails=False):
        self.fails = fails
        self.calls: list = []

    async def sync(self, guild=None):
        self.calls.append(guild)
        if self.fails:
            raise discord.HTTPException(mock.Mock(status=429, reason="x"), "slow down")
        return [SimpleNamespace(name="mylo"), SimpleNamespace(name="activate")]

    def copy_global_to(self, guild):
        pass

    def clear_commands(self, guild):
        pass


def _admin(tree):
    return AdminCog(SimpleNamespace(tree=tree))  # type: ignore[arg-type]


class AdminReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_global_sync_says_it_started_then_what_it_synced(self) -> None:
        ctx, tree = FakeCtx(), FakeTree()
        await AdminCog.sync.callback(_admin(tree), ctx, "global")
        self.assertEqual(len(ctx.replies), 1)  # one message, edited in place
        self.assertIn("2 command(s) globally: /activate, /mylo", ctx.replies[0].content)
        self.assertEqual(tree.calls, [None])

    async def test_sync_in_a_dm_defaults_to_global(self) -> None:
        ctx, tree = FakeCtx(), FakeTree()
        await AdminCog.sync.callback(_admin(tree), ctx)
        self.assertEqual(tree.calls, [None])

    async def test_global_sync_alias(self) -> None:
        ctx, tree = FakeCtx(), FakeTree()
        await AdminCog.global_sync.callback(_admin(tree), ctx, "sync")
        self.assertIn("globally", ctx.replies[0].content)

    async def test_an_unknown_scope_is_explained_not_synced(self) -> None:
        ctx, tree = FakeCtx(), FakeTree()
        await AdminCog.sync.callback(_admin(tree), ctx, "everywhere")
        self.assertIn("Unknown sync scope", ctx.replies[0].content)
        self.assertEqual(tree.calls, [])

    async def test_a_failed_sync_is_reported(self) -> None:
        ctx, tree = FakeCtx(), FakeTree(fails=True)
        await AdminCog.sync.callback(_admin(tree), ctx, "global")
        self.assertIn("Sync failed: 429", ctx.replies[0].content)

    async def test_errors_are_answered(self) -> None:
        cog = _admin(FakeTree())
        cases = [
            (commands.CommandNotFound("x"), USAGE),
            (commands.NotOwner(), NOT_OWNER),
        ]
        for error, line in cases:
            ctx = FakeCtx()
            await cog.on_command_error(ctx, error)
            self.assertEqual(ctx.replies[0].content, line)


if __name__ == "__main__":
    unittest.main()

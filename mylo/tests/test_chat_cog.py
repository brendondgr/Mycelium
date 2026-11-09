"""The chat cog against a fake transport (plan D, D3).

No Discord and no database: the bridge is a fake that hands out a scripted
turn, and the messages record every send and edit with its kwargs, so the
mention rules are asserted on what would have gone out.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

from mylo import chat as chat_module
from mylo.bot import chat_render as render
from mylo.bot.cogs import chat as cog_module
from mylo.bot.cogs.chat import ChatCog


def _run(coro):
    return asyncio.run(coro)


class Sent:
    """A message Mylo posted: records its edits."""

    _ids = iter(range(70_000, 79_999))

    def __init__(self, content, kwargs):
        self.id = next(self._ids)
        self.content = content
        self.kwargs = kwargs
        self.edits: list[dict] = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        self.content = kwargs.get("content", self.content)


class Channel:
    def __init__(self, channel_id=500):
        self.id = channel_id
        self.sent: list[Sent] = []
        self.partials: dict[int, Sent] = {}

    async def send(self, content, **kwargs):
        msg = Sent(content, kwargs)
        self.sent.append(msg)
        return msg

    def get_partial_message(self, message_id):
        return self.partials.setdefault(message_id, Sent("", {}))


class Question:
    def __init__(self, channel, *, guild=True, author_id=111, attachments=()):
        self.id = 4242
        self.channel = channel
        self.guild = SimpleNamespace(id=900) if guild else None
        self.author = SimpleNamespace(id=author_id, name="ana", display_name="Ana")
        self.attachments = list(attachments)
        self.replies: list[Sent] = []
        self.reactions: list[str] = []

    async def reply(self, content, **kwargs):
        msg = Sent(content, kwargs)
        self.replies.append(msg)
        return msg

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)


def handle(**kw):
    base = dict(
        turn_id=1,
        thread_id="t",
        link_id=1,
        discord_user_id="111",
        channel_id="500",
        trigger_message_id="4242",
        status_message_id="",
        user_event_seq=1,
        queued=False,
        guest=False,
        first=True,
        asked_at=0.0,
        shared=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class FakeBridge:
    def __init__(self, *, activity=(), result=None, slow=False, refusal="",
                 queued=False, pending=()):
        self.activity = list(activity)
        self._result = result or {
            "state": "answered",
            "text": "It is due Friday (#1).",
            "sources": [{"n": 1, "title": "Ocean call", "url": "https://x.org/c"}],
            "model": {"label": "Qwen", "location": "local"},
        }
        self.slow = slow
        self.refusal = refusal
        self.queued = queued
        self.pending = list(pending)
        self.asked: list[dict] = []
        self.finished: list[tuple] = []
        self.status_ids: list = []
        #: (clock, step): the fake clock the cog reads, moved per activity
        self.clock = None

    async def ask(self, **facts):
        self.asked.append(facts)
        if self.refusal:
            return {"refusal": self.refusal}
        return {"handle": handle(queued=self.queued)}

    async def set_status(self, h, message_id):
        self.status_ids.append(message_id)
        h.status_message_id = str(message_id)
        return h

    async def watch(self, h):
        for message in self.activity:
            if self.clock is not None:
                self.clock[0][0] += self.clock[1]
            yield message

    async def result(self, h):
        return dict(self._result)

    async def ping_due(self, h):
        return self.slow

    async def timed_out(self, h):
        return False

    async def finish(self, h, state):
        self.finished.append((h.turn_id, state))
        self.pending = [p for p in self.pending if p.turn_id != h.turn_id]

    async def reconcile(self):
        return list(self.pending)

    async def handle_for(self, turn_id):
        return next((p for p in self.pending if p.turn_id == turn_id), None)

    async def stop(self, h, discord_user_id):
        return ""


def _cog(bridge, *, now=None):
    clock = (lambda: now[0]) if now is not None else (lambda: 0.0)
    bot = SimpleNamespace(user=SimpleNamespace(id=999))
    return ChatCog(bot, bridge=bridge, clock=clock)  # type: ignore[arg-type]


ACTIVITY = [
    {"type": "activity", "payload": {"state": "thinking"}},
    {"type": "activity", "payload": {"state": "running", "label": "Reading the call"}},
    {"type": "assistant", "payload": {"text": "x", "final": True}},
]


def _all_kwargs(question: Question, channel: Channel) -> list[dict]:
    out = []
    for msg in question.replies + channel.sent:
        out.append(msg.kwargs)
        out.extend(msg.edits)
    return out


class DeliveryTests(unittest.TestCase):
    def _ask(self, bridge, question, *, ids=None, now=None):
        cog = _cog(bridge, now=now)
        ids = ids or {
            "guild_id": "900" if question.guild else "",
            "channel_id": str(question.channel.id),
            "thread_id": "",
            "parent_id": "",
        }
        with mock.patch.object(cog_module.chat, "place_ids", lambda m: ids):
            _run(cog.ask(question, "when is it due?"))
        return cog

    def _assert_status_then_answer(self, question, channel, bridge):
        self.assertEqual(len(question.replies), 1)
        status = question.replies[0]
        self.assertEqual(status.content.split("\n")[0], "It is due Friday (#1).")
        self.assertIn("view", status.kwargs)  # the Stop button
        self.assertEqual(status.kwargs["mention_author"], False)
        texts = [e.get("content") for e in status.edits]
        self.assertIn(render.THINKING, texts)
        self.assertIn("*Reading the call…*", texts)
        self.assertIsNone(status.edits[-1]["view"])  # Stop removed with the answer
        self.assertIn("**Sources**", status.content)
        self.assertEqual(bridge.finished, [(1, "answered")])
        for kwargs in _all_kwargs(question, channel):
            self.assertEqual(
                kwargs["allowed_mentions"].to_dict(),
                discord.AllowedMentions.none().to_dict(),
            )

    def test_a_dm(self) -> None:
        bridge = FakeBridge(activity=ACTIVITY)
        channel = Channel()
        question = Question(channel, guild=False)
        now = [100.0]
        bridge.clock = (now, 2.0)
        self._ask(bridge, question, now=now)
        self._assert_status_then_answer(question, channel, bridge)
        self.assertEqual(bridge.asked[0]["guild_id"], "")

    def test_a_forum_thread(self) -> None:
        bridge = FakeBridge(activity=ACTIVITY)
        channel = Channel(777)
        question = Question(channel)
        ids = {
            "guild_id": "900",
            "channel_id": "777",
            "thread_id": "777",
            "parent_id": "forum-1",
        }
        clock = [0.0]
        bridge.clock = (clock, 2.0)
        self._ask(bridge, question, ids=ids, now=clock)
        self._assert_status_then_answer(question, channel, bridge)
        self.assertEqual(bridge.asked[0]["thread_id"], "777")

    def test_a_channel(self) -> None:
        bridge = FakeBridge(activity=ACTIVITY)
        channel = Channel()
        question = Question(channel)
        self._ask(bridge, question, now=[0.0])
        # one throttled edit at most per 1.5 s: the clock never moved, so only
        # the first status change was drawn before the answer
        status = question.replies[0]
        self.assertEqual(len(status.edits), 2)
        self.assertEqual(status.edits[0]["content"], render.THINKING)

    def test_a_long_answer_follows_as_plain_messages(self) -> None:
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 150 for i in range(8))
        bridge = FakeBridge(result={"state": "answered", "text": text, "sources": []})
        channel = Channel()
        question = Question(channel)
        self._ask(bridge, question)
        self.assertGreater(len(channel.sent), 0)
        for msg in channel.sent:
            self.assertLess(len(msg.content), render.LIMIT)
            self.assertEqual(
                msg.kwargs["allowed_mentions"].to_dict(),
                discord.AllowedMentions.none().to_dict(),
            )

    def test_a_slow_answer_pings_the_asker_and_nobody_else(self) -> None:
        bridge = FakeBridge(slow=True)
        channel = Channel()
        question = Question(channel)
        self._ask(bridge, question)
        status = question.replies[0]
        self.assertEqual(status.edits[-1]["content"], render.ANSWERED_BELOW)
        answer = channel.sent[0]
        self.assertTrue(answer.content.startswith("<@111> "))
        allowed = answer.kwargs["allowed_mentions"]
        self.assertEqual(
            allowed.to_dict(),
            {"parse": [], "users": [111]},
        )
        self.assertFalse(allowed.replied_user or allowed.roles or allowed.everyone)
        self.assertEqual(answer.kwargs["reference"].message_id, 4242)

    def test_a_quick_answer_is_a_silent_edit(self) -> None:
        bridge = FakeBridge()
        channel = Channel()
        question = Question(channel)
        self._ask(bridge, question)
        self.assertEqual(channel.sent, [])
        self.assertIn("Friday", question.replies[0].content)

    def test_a_refusal_is_a_reply_that_pings_nobody(self) -> None:
        bridge = FakeBridge(refusal="This server isn't set up for Mylo.")
        channel = Channel()
        question = Question(channel)
        self._ask(bridge, question)
        self.assertEqual(question.replies[0].content, "This server isn't set up for Mylo.")
        self.assertEqual(
            question.replies[0].kwargs["allowed_mentions"].to_dict(),
            discord.AllowedMentions.none().to_dict(),
        )

    def test_a_queued_question_gets_an_hourglass(self) -> None:
        bridge = FakeBridge(queued=True)
        question = Question(Channel())
        self._ask(bridge, question)
        self.assertEqual(question.reactions, [cog_module.HOURGLASS])

    def test_a_stopped_or_failed_turn_says_so(self) -> None:
        for state, text in (("cancelled", render.STOPPED), ("failed", render.FAILED)):
            bridge = FakeBridge(result={"state": state, "error": ""})
            question = Question(Channel())
            self._ask(bridge, question)
            self.assertEqual(question.replies[0].content, text)


class RecoveryTests(unittest.TestCase):
    def test_a_restart_with_a_pending_row_delivers_the_answer_once(self) -> None:
        pending = handle(turn_id=7, status_message_id="61000")
        bridge = FakeBridge(pending=[pending])
        channel = Channel()
        cog = _cog(bridge)
        cog.bot.get_channel = lambda cid: channel
        _run(cog.recover())
        _run(cog.recover())  # a gateway resume right after
        status = channel.partials[61000]
        self.assertEqual(len(status.edits), 1)
        self.assertIn("Friday", status.edits[0]["content"])
        self.assertEqual(bridge.finished, [(7, "answered")])

    def test_a_turn_that_ended_in_an_error_is_lost_track_of(self) -> None:
        pending = handle(turn_id=8, status_message_id="61001")
        bridge = FakeBridge(pending=[pending], result={"state": "failed", "error": ""})
        channel = Channel()
        cog = _cog(bridge)
        cog.bot.get_channel = lambda cid: channel
        _run(cog.recover())
        self.assertEqual(bridge.finished, [(8, "failed")])


class ReplyHintTests(unittest.TestCase):
    def test_a_reply_without_a_ping_gets_one_hint_an_hour(self) -> None:
        now = [0.0]
        cog = _cog(FakeBridge(), now=now)
        question = Question(Channel())
        _run(cog.hint(question))
        now[0] = 600.0
        _run(cog.hint(question))
        self.assertEqual(len(question.replies), 1)
        self.assertEqual(question.replies[0].content, chat_module.REPLY_HINT)
        now[0] = 3700.0
        _run(cog.hint(question))
        self.assertEqual(len(question.replies), 2)


class RouteTests(unittest.TestCase):
    def _message(self, **kw):
        base = dict(
            author=SimpleNamespace(id=1, bot=False),
            guild=SimpleNamespace(id=900),
            content="hello",
            mentions=[],
            role_mentions=[],
            webhook_id=None,
            reference=None,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_triggers(self) -> None:
        bot = SimpleNamespace(id=999)
        route = chat_module.route
        self.assertEqual(route(self._message(guild=None), bot).kind, "chat")
        mention = self._message(content="<@999> what is due?", mentions=[bot])
        self.assertEqual(route(mention, bot), chat_module.Route("chat", "what is due?"))
        self.assertEqual(route(self._message(), bot).kind, "none")
        reply = self._message(
            content="",
            reference=SimpleNamespace(resolved=SimpleNamespace(author=bot)),
        )
        self.assertEqual(route(reply, bot).kind, "reply_hint")
        role = SimpleNamespace(id=5, tags=SimpleNamespace(bot_id=999))
        self.assertEqual(
            route(self._message(content="<@&5> hi", role_mentions=[role]), bot),
            chat_module.Route("chat", "hi"),
        )

    def test_ignored(self) -> None:
        bot = SimpleNamespace(id=999)
        route = chat_module.route
        other_bot = self._message(author=SimpleNamespace(id=2, bot=True), mentions=[bot])
        self.assertEqual(route(other_bot, bot).kind, "none")
        hook = self._message(webhook_id=5, mentions=[bot])
        self.assertEqual(route(hook, bot).kind, "none")
        everyone = self._message(content="@everyone look")
        self.assertEqual(route(everyone, bot).kind, "none")


if __name__ == "__main__":
    unittest.main()

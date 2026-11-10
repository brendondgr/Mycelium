"""The listen cog: what it carries, what it refuses to, and what it never does.

Nothing here touches Discord or the database. The cog's whole job is to hand a
message to :mod:`mylo.listening` and get out of the way, so these tests assert
exactly that hand-off — and the three rules around it:

* **Stage B is off.** Server-wide listening needs the Message Content
  privileged intent, and the code for it ships dark behind two switches that
  must both be true.
* **A listener never kills the gateway.** A backend that raises loses one
  message, not the connection that would have carried the next thousand.
* **The cog decides nothing about people.** It forwards a snowflake; whether
  that person may be listened to is answered on the backend, every time.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

from mylo.bot.client import _intents
from mylo.bot.cogs import listen as listen_module
from mylo.bot.cogs.listen import ListenCog, _place_kind
from mylo.config import MyloConfig, load_config


def _run(coro):
    return asyncio.run(coro)


class FakeListening:
    """Stands in for :mod:`mylo.listening`, recording what it was asked."""

    def __init__(self, *, stored=True, notify=False, raises=False, reply=""):
        self.calls: list[dict] = []
        self.turns: list[tuple] = []
        self.buttons: list[tuple] = []
        self._reply = reply
        self.edits: list[tuple] = []
        self.deletes: list[tuple] = []
        self.notices: list[tuple] = []
        self._stored = stored
        self._notify = notify
        self._raises = raises

    async def heard(self, **fields):
        if self._raises:
            raise RuntimeError("the backend is down")
        self.calls.append(fields)
        return {
            "stored": self._stored,
            "reason": "",
            "notify_member": self._notify,
        }

    async def dialogue(self, discord_user_id, text, *, reply_to_id=""):
        self.turns.append((discord_user_id, text, reply_to_id))
        return self._reply

    async def answer_button(self, discord_user_id, suggestion_id, choice):
        self.buttons.append((discord_user_id, suggestion_id, choice))
        return "Done — from tomorrow morning's run."

    async def message_edited(self, guild_id, message_id, text, *, is_dm=False):
        self.edits.append((guild_id, message_id, text, is_dm))
        return 0

    async def message_deleted(self, guild_id, message_id, *, is_dm=False):
        self.deletes.append((guild_id, message_id, is_dm))
        return True

    async def record_notice(self, guild_id, discord_user_id, *, delivered):
        self.notices.append((guild_id, discord_user_id, delivered))

    async def note(self, discord_user_id, text, *, guild_id=""):
        self.calls.append({"note": True, "text": text, "guild_id": guild_id})
        return {"stored": self._stored, "reason": ""}


class FakeChannel:
    def __init__(self, channel_id="chan-1", name="methods"):
        self.id = channel_id
        self.name = name
        self.sent: list[str] = []

    async def send(self, content):
        self.sent.append(content)


class FakeAuthor:
    def __init__(self, author_id=111, bot=False):
        self.id = author_id
        self.bot = bot
        self.dms: list[str] = []
        self.dm_fails = False

    async def send(self, content):
        if self.dm_fails:
            raise discord.HTTPException(mock.Mock(status=403), "blocked")
        self.dms.append(content)


def _message(*, guild=True, mentions=None, author=None, content="x" * 40, channel=None):
    return SimpleNamespace(
        id=555,
        content=content,
        created_at="2026-09-18T00:00:00Z",
        author=author or FakeAuthor(),
        mentions=mentions or [],
        attachments=[],
        channel=channel or FakeChannel(),
        guild=SimpleNamespace(id=900, name="PULSE Lab") if guild else None,
    )


def _cog(fake, *, listen_enabled=False, message_content=False, bot_user_id=999):
    bot = SimpleNamespace(
        config=MyloConfig(token="x", error_channel_id=1, listen_enabled=listen_enabled),
        intents=SimpleNamespace(message_content=message_content),
        user=SimpleNamespace(id=bot_user_id),
    )
    cog = ListenCog(bot)  # type: ignore[arg-type]
    return cog


class StageSwitchTests(unittest.TestCase):
    def test_stage_b_needs_both_the_flag_and_the_intent(self) -> None:
        fake = FakeListening()
        self.assertFalse(_cog(fake).stage_b)
        self.assertFalse(_cog(fake, listen_enabled=True).stage_b)
        self.assertFalse(_cog(fake, message_content=True).stage_b)
        self.assertTrue(
            _cog(fake, listen_enabled=True, message_content=True).stage_b
        )

    def test_the_bot_asks_for_no_privileged_intent_by_default(self) -> None:
        intents = _intents(MyloConfig(token="x", error_channel_id=1))
        self.assertFalse(intents.message_content)

    def test_message_content_is_requested_only_for_stage_b(self) -> None:
        intents = _intents(
            MyloConfig(token="x", error_channel_id=1, listen_enabled=True)
        )
        self.assertTrue(intents.message_content)

    def test_the_flag_defaults_off_and_reads_plain_words(self) -> None:
        self.assertFalse(load_config({"DISCORD_API_KEY": "t"}).listen_enabled)
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                config = load_config(
                    {"DISCORD_API_KEY": "t", "MYLO_LISTEN_ENABLED": value}
                )
                self.assertTrue(config.listen_enabled)

    def test_a_malformed_switch_fails_closed(self) -> None:
        """A typo in the switch that reads a server's conversation reads as off."""
        config = load_config({"DISCORD_API_KEY": "t", "MYLO_LISTEN_ENABLED": "maybe"})
        self.assertFalse(config.listen_enabled)


class GuildMessageTests(unittest.TestCase):
    def test_an_ordinary_channel_message_is_not_carried_in_stage_a(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message()))
        self.assertEqual(fake.calls, [])

    def test_a_mention_is_carried_and_marked_explicit(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message(mentions=[cog.bot.user])))
        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(fake.calls[0]["explicit"])
        self.assertEqual(fake.calls[0]["place_label"], "methods")

    def test_people_named_are_forwarded_and_bots_are_not(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        colleague = SimpleNamespace(id=333, bot=False)
        message = _message(mentions=[cog.bot.user, colleague])
        cog.bot.user.bot = True
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(message))
        self.assertEqual(fake.calls[0]["mention_ids"], ["333"])

    def test_stage_b_carries_everything_in_a_channel(self) -> None:
        fake = FakeListening()
        cog = _cog(fake, listen_enabled=True, message_content=True)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message()))
        self.assertEqual(len(fake.calls), 1)
        self.assertFalse(fake.calls[0]["explicit"])  # overheard, not addressed

    def test_an_owner_command_is_never_carried(self) -> None:
        fake = FakeListening()
        cog = _cog(fake, listen_enabled=True, message_content=True)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message(content="!mylo sync global")))
            _run(cog.on_message(_message(guild=False, content="!mylo global sync")))
        self.assertEqual(fake.calls, [])
        self.assertEqual(fake.turns, [])

    def test_mylos_own_line_is_carried_as_its_own(self) -> None:
        """A question Mylo asked is what makes the next line an answer."""
        fake = FakeListening()
        cog = _cog(fake)
        message = _message(author=FakeAuthor(author_id=999, bot=True))
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(message))
        self.assertTrue(fake.calls[0]["from_mylo"])
        self.assertFalse(fake.calls[0]["explicit"])

    def test_another_bot_is_forwarded_and_refused_on_the_backend(self) -> None:
        """The cog does not decide; it reports what it saw and lets the ledger say no."""
        fake = FakeListening(stored=False)
        cog = _cog(fake, listen_enabled=True, message_content=True)
        message = _message(author=FakeAuthor(author_id=222, bot=True))
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(message))
        self.assertTrue(fake.calls[0]["is_bot"])

    def test_an_attachment_contributes_its_url_and_never_its_content(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        message = _message(mentions=[_cog(fake).bot.user])
        message.mentions = [cog.bot.user]
        message.attachments = [SimpleNamespace(url="https://example.org/p.pdf")]
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(message))
        self.assertEqual(
            fake.calls[0]["attachment_urls"], ["https://example.org/p.pdf"]
        )


class DirectMessageTests(unittest.TestCase):
    def test_a_dm_is_a_conversation_with_mylo(self) -> None:
        """Plan D: a DM that is not an answer to an ambient question goes to
        Mylo chat, not to the ledger as a note, and gets no acknowledgement."""
        fake = FakeListening()
        cog = _cog(fake)
        asked = []

        class Chat:
            async def ask(self, message, text):
                asked.append(text)

        cog.bot.get_cog = lambda name: Chat() if name == "Chat" else None
        channel = FakeChannel()
        message = _message(guild=False, content="we dropped the simulation approach",
                           channel=channel)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(message))
        self.assertEqual(fake.calls, [])  # not stored as an explicit note
        self.assertEqual(asked, ["we dropped the simulation approach"])
        self.assertEqual(channel.sent, [])

    def test_an_answer_to_a_question_gets_the_dialogues_reply(self) -> None:
        """Plan 06: a DM that answers one of Mylo's questions is answered in
        the dialogue's words, instead of the plain acknowledgement."""
        fake = FakeListening(reply="Done — I'll include it from tomorrow's run.")
        cog = _cog(fake)
        channel = FakeChannel()
        message = _message(guild=False, content="yes please", channel=channel)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(message))
        self.assertEqual(fake.turns[0][1], "yes please")
        self.assertEqual(channel.sent, ["Done — I'll include it from tomorrow's run."])

    def test_a_question_button_is_answered_and_its_buttons_removed(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        responses, edits = [], []

        class Response:
            async def send_message(self, text):
                responses.append(text)

        class Message:
            async def edit(self, **kwargs):
                edits.append(kwargs)

        interaction = SimpleNamespace(
            type=discord.InteractionType.component,
            data={"custom_id": "ambient:42:reports"},
            user=SimpleNamespace(id=111),
            response=Response(),
            message=Message(),
        )
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_interaction(interaction))
        self.assertEqual(fake.buttons, [("111", "42", "reports")])
        self.assertEqual(responses, ["Done — from tomorrow morning's run."])
        self.assertEqual(edits, [{"view": None}])

    def test_other_components_are_not_ours(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        interaction = SimpleNamespace(
            type=discord.InteractionType.component,
            data={"custom_id": "setup:listening:on"},
            user=SimpleNamespace(id=111),
            response=None,
            message=None,
        )
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_interaction(interaction))
        self.assertEqual(fake.buttons, [])

    def test_an_unstored_dm_is_not_acknowledged(self) -> None:
        """Somebody who has not opted in should not be told "got it"."""
        fake = FakeListening(stored=False)
        cog = _cog(fake)
        channel = FakeChannel()
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message(guild=False, channel=channel)))
        self.assertEqual(channel.sent, [])

    def test_another_bots_dm_is_ignored_entirely(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        message = _message(guild=False, author=FakeAuthor(author_id=222, bot=True))
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(message))
        self.assertEqual(fake.calls, [])


class NoticeTests(unittest.TestCase):
    def test_somebody_is_told_once_that_the_server_is_listening(self) -> None:
        fake = FakeListening(stored=False, notify=True)
        cog = _cog(fake, listen_enabled=True, message_content=True)
        author = FakeAuthor()
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message(author=author)))
        self.assertEqual(len(author.dms), 1)
        self.assertIn("PULSE Lab", author.dms[0])
        self.assertIn("your messages are being dropped", author.dms[0].lower())
        self.assertIn("/mylo listening on", author.dms[0])
        self.assertEqual(fake.notices, [("900", "111", True)])

    def test_a_notice_nobody_received_is_not_recorded_as_delivered(self) -> None:
        fake = FakeListening(stored=False, notify=True)
        cog = _cog(fake, listen_enabled=True, message_content=True)
        author = FakeAuthor()
        author.dm_fails = True
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message(author=author)))
        self.assertEqual(fake.notices, [("900", "111", False)])

    def test_nobody_is_told_twice(self) -> None:
        """The backend holds the record; the cog only acts when told to."""
        fake = FakeListening(stored=False, notify=False)
        cog = _cog(fake, listen_enabled=True, message_content=True)
        author = FakeAuthor()
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message(author=author)))
        self.assertEqual(author.dms, [])
        self.assertEqual(fake.notices, [])


class EditAndDeleteTests(unittest.TestCase):
    def test_an_edit_to_what_was_said_is_forwarded(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        payload = SimpleNamespace(
            data={"content": "the compute cost is the blocker"},
            guild_id=900,
            channel_id=1,
            message_id=555,
        )
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_raw_message_edit(payload))
        self.assertEqual(
            fake.edits, [("900", "555", "the compute cost is the blocker", False)]
        )

    def test_an_embed_resolving_is_not_an_edit(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        payload = SimpleNamespace(
            data={"embeds": [{}]}, guild_id=900, channel_id=1, message_id=555
        )
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_raw_message_edit(payload))
        self.assertEqual(fake.edits, [])

    def test_a_deletion_is_forwarded(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        payload = SimpleNamespace(guild_id=900, channel_id=1, message_id=555)
        deleted = []

        async def question_deleted(message_id):
            deleted.append(message_id)
            return True

        fake_chat = SimpleNamespace(question_deleted=question_deleted)
        with mock.patch.object(listen_module, "listening", fake), mock.patch.object(
            listen_module, "chat", fake_chat
        ):
            _run(cog.on_raw_message_delete(payload))
        self.assertEqual(fake.deletes, [("900", "555", False)])
        # a question to Mylo leaves the chat queue and is blanked too
        self.assertEqual(deleted, ["555"])

    def test_clearing_a_channel_deletes_every_message_in_it(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        payload = SimpleNamespace(
            guild_id=900, channel_id=1, message_ids={1, 2, 3}
        )
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_raw_bulk_message_delete(payload))
        self.assertEqual(len(fake.deletes), 3)

    def test_a_dm_edit_is_keyed_on_the_channel(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        payload = SimpleNamespace(
            data={"content": "actually never mind"},
            guild_id=None,
            channel_id=77,
            message_id=555,
        )
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_raw_message_edit(payload))
        self.assertEqual(fake.edits[0][3], True)


class ResilienceTests(unittest.TestCase):
    def test_a_backend_failure_loses_a_message_not_the_gateway(self) -> None:
        fake = FakeListening(raises=True)
        cog = _cog(fake, listen_enabled=True, message_content=True)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message()))  # must not raise

    def test_a_blocked_dialogue_reply_is_survivable(self) -> None:
        fake = FakeListening(reply="Done.")
        cog = _cog(fake)

        class Blocked(FakeChannel):
            async def send(self, content):
                raise discord.HTTPException(mock.Mock(status=403), "blocked")

        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_message(_message(guild=False, channel=Blocked())))
        self.assertEqual(len(fake.turns), 1)


class ReactionTests(unittest.TestCase):
    def _payload(self, *, message_author_id=999, user_id=111, guild_id=900):
        return SimpleNamespace(
            user_id=user_id,
            message_author_id=message_author_id,
            message_id=555,
            channel_id=7,
            guild_id=guild_id,
            emoji="\N{THUMBS UP SIGN}",
        )

    def test_a_reaction_on_mylos_post_is_the_shortest_possible_answer(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_raw_reaction_add(self._payload()))
        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(fake.calls[0]["explicit"])
        self.assertIn("reacted", fake.calls[0]["text"])

    def test_a_reaction_on_somebody_elses_post_is_between_them(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_raw_reaction_add(self._payload(message_author_id=222)))
        self.assertEqual(fake.calls, [])

    def test_mylo_reacting_to_itself_is_not_an_answer(self) -> None:
        fake = FakeListening()
        cog = _cog(fake)
        with mock.patch.object(listen_module, "listening", fake):
            _run(cog.on_raw_reaction_add(self._payload(user_id=999)))
        self.assertEqual(fake.calls, [])


class MessageActionTests(unittest.TestCase):
    def _interaction(self, user_id=111, bot_user_id=999):
        sent: list[str] = []

        async def _defer(*, ephemeral=False):
            return None

        async def _send(content, *, ephemeral=False):
            sent.append(content)

        return (
            SimpleNamespace(
                user=SimpleNamespace(id=user_id),
                client=SimpleNamespace(user=SimpleNamespace(id=bot_user_id)),
                guild_id=900,
                response=SimpleNamespace(defer=_defer),
                followup=SimpleNamespace(send=_send),
            ),
            sent,
        )

    def test_your_own_message_is_kept(self) -> None:
        fake = FakeListening()
        interaction, sent = self._interaction()
        message = _message(author=FakeAuthor(author_id=111))
        with mock.patch.object(listen_module, "listening", fake):
            _run(listen_module.tell_mylo_about_this(interaction, message))
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("Got it", sent[0])

    def test_somebody_elses_message_is_refused_with_a_reason(self) -> None:
        """One person must not be able to feed a colleague's words into the ledger."""
        fake = FakeListening()
        interaction, sent = self._interaction()
        message = _message(author=FakeAuthor(author_id=222))
        with mock.patch.object(listen_module, "listening", fake):
            _run(listen_module.tell_mylo_about_this(interaction, message))
        self.assertEqual(fake.calls, [])
        self.assertIn("Somebody else's words are theirs", sent[0])
        self.assertIn("/mylo note", sent[0])

    def test_mylos_own_message_may_be_kept(self) -> None:
        fake = FakeListening()
        interaction, sent = self._interaction()
        message = _message(author=FakeAuthor(author_id=999, bot=True))
        with mock.patch.object(listen_module, "listening", fake):
            _run(listen_module.tell_mylo_about_this(interaction, message))
        self.assertEqual(len(fake.calls), 1)

    def test_a_refusal_says_what_to_do_about_it(self) -> None:
        fake = FakeListening(stored=False)

        async def _note(user_id, text, *, guild_id=""):
            return {"stored": False, "reason": "person_not_opted_in"}

        fake.note = _note
        interaction, sent = self._interaction()
        message = _message(author=FakeAuthor(author_id=111))
        with mock.patch.object(listen_module, "listening", fake):
            _run(listen_module.tell_mylo_about_this(interaction, message))
        self.assertIn("/mylo listening on", sent[0])


class PlaceKindTests(unittest.TestCase):
    def test_a_channel_is_a_channel(self) -> None:
        self.assertEqual(_place_kind(FakeChannel()), "channel")

    def _thread(self, parent_type) -> discord.Thread:
        """A Thread with only the attribute under test.

        ``Thread.parent`` is a read-only property that resolves through the
        connection state, so it is patched on the class for the duration of the
        check rather than set on the instance.
        """
        thread = discord.Thread.__new__(discord.Thread)
        return thread, mock.patch.object(
            discord.Thread,
            "parent",
            new_callable=mock.PropertyMock,
            return_value=SimpleNamespace(type=parent_type),
        )

    def test_a_thread_is_a_thread(self) -> None:
        thread, patched = self._thread(discord.ChannelType.text)
        with patched:
            self.assertEqual(_place_kind(thread), "thread")

    def test_a_forum_post_is_a_forum_post(self) -> None:
        thread, patched = self._thread(discord.ChannelType.forum)
        with patched:
            self.assertEqual(_place_kind(thread), "forum")

    def test_a_dm_channel_is_a_dm(self) -> None:
        channel = discord.DMChannel.__new__(discord.DMChannel)
        self.assertEqual(_place_kind(channel), "dm")


class HealthTests(unittest.TestCase):
    """`/mylo health` has to answer what Mylo can actually hear, not what a
    database row says."""

    def _cog_with(self, *, listen_enabled, message_content):
        from mylo.bot.cogs.mylo_commands import MyloCog

        bot = SimpleNamespace(
            config=MyloConfig(
                token="x", error_channel_id=1, listen_enabled=listen_enabled
            ),
            intents=SimpleNamespace(message_content=message_content),
            user=SimpleNamespace(id=999),
        )
        return MyloCog(bot)  # type: ignore[arg-type]

    def _lines(self, cog, state):
        import mylo.bot.cogs.mylo_commands as commands_module

        fake = SimpleNamespace()

        async def _listening_state(guild_id):
            return state

        fake.listening_state = _listening_state
        interaction = SimpleNamespace(guild_id=900)
        with mock.patch.object(commands_module, "listening", fake):
            return _run(cog._listening_lines(interaction))

    def test_listening_off_says_off(self) -> None:
        cog = self._cog_with(listen_enabled=False, message_content=False)
        lines = self._lines(cog, {"known": True, "listening": False})
        self.assertEqual(lines, ["Listening here: **off**."])

    def test_stage_a_says_what_it_can_actually_hear(self) -> None:
        cog = self._cog_with(listen_enabled=False, message_content=False)
        lines = self._lines(
            cog,
            {"known": True, "listening": True, "heard_today": 3, "stored_today": 1},
        )
        self.assertIn("server-wide listening is not enabled", lines[0])
        self.assertIn("heard 3", lines[-1])

    def test_stage_b_says_it_reads_the_channels(self) -> None:
        cog = self._cog_with(listen_enabled=True, message_content=True)
        lines = self._lines(cog, {"known": True, "listening": True})
        self.assertIn("every channel it is not excluded from", lines[0])

    def test_an_unknown_server_is_reported_as_off(self) -> None:
        cog = self._cog_with(listen_enabled=True, message_content=True)
        self.assertEqual(
            self._lines(cog, {"known": False}), ["Listening here: **off**."]
        )


if __name__ == "__main__":
    unittest.main()

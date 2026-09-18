"""`/setup`'s Listening section: what a manager is told, and what people see.

The switch itself is one of three gates, and the menu has to say so — a manager
who believes turning it on decides the matter for everybody has been misled by
the interface, whatever the code does. And when it goes on, a visible notice
goes up in the server, because the whole feature rests on people knowing
(OD-02b).
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

from mylo.bot.cogs import setup as setup_module
from mylo.bot.cogs.setup import SetupView, _marker_text, _render_status


def _run(coro):
    return asyncio.run(coro)


class FakeListening:
    def __init__(self, *, status="ok", payload=None):
        self.status = status
        self.payload = payload if payload is not None else {}
        self.calls: list[tuple] = []
        self.markers: list[tuple] = []

    async def set_guild_listening(self, user_id, guild_id, *, on):
        self.calls.append(("listening", guild_id, on))
        return (self.status, {**self.payload, "listening": on})

    async def set_channel_rule(self, user_id, guild_id, channel_id, *, rule, on):
        self.calls.append(("channel", channel_id, rule, on))
        excluded = list(self.payload.get("excluded") or [])
        if on:
            excluded.append(channel_id)
        else:
            excluded = [one for one in excluded if one != channel_id]
        self.payload = {**self.payload, "excluded": excluded}
        return (self.status, dict(self.payload))

    async def set_marker(self, guild_id, *, channel_id, message_id):
        self.markers.append((guild_id, channel_id, message_id))

    async def listening_state(self, guild_id):
        return dict(self.payload)


class FakeMessage:
    def __init__(self, message_id=77):
        self.id = message_id
        self.content = ""
        self.pinned = False

    async def edit(self, content):
        self.content = content

    async def pin(self):
        self.pinned = True


class FakeChannel:
    def __init__(self, channel_id=5, fails=False):
        self.id = channel_id
        self.sent: list[str] = []
        self.fails = fails
        self.message = FakeMessage()

    async def send(self, content):
        if self.fails:
            raise discord.HTTPException(mock.Mock(status=403), "denied")
        self.sent.append(content)
        return self.message

    async def fetch_message(self, message_id):
        return self.message


class FakeInteraction:
    def __init__(self, channel=None):
        self.channel = channel or FakeChannel()
        self.client = SimpleNamespace(get_channel=lambda _id: None)
        self.edited: list[str] = []
        self.response = SimpleNamespace(defer=self._defer)

    async def _defer(self):
        return None

    async def edit_original_response(self, *, content, view=None):
        self.edited.append(content)


def _view(state=None) -> SetupView:
    return SetupView(1, "900", state or {"lab_name": "PULSE"})


class RenderTests(unittest.TestCase):
    def test_listening_off_reads_as_off(self) -> None:
        text = _render_status({"lab_name": "PULSE", "listening": False})
        self.assertIn("**Listening:** _off_", text)

    def test_listening_on_says_members_still_choose(self) -> None:
        """A manager must not be able to read the switch as deciding for everyone."""
        text = _render_status({"lab_name": "PULSE", "listening": True})
        self.assertIn("your members choose for themselves", text)

    def test_an_unavailable_deployment_says_so_rather_than_off(self) -> None:
        text = _render_status(
            {"lab_name": "PULSE", "listening": False, "available": False}
        )
        self.assertIn("not available on Mycelium yet", text)

    def test_a_refusal_posts_no_notice(self) -> None:
        fake = FakeListening(
            status="unavailable",
            payload={"message": "Listening isn't switched on for Mycelium yet."},
        )
        view = _view()
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_listening(interaction, on=True))
        self.assertEqual(interaction.channel.sent, [])
        self.assertIn("isn't switched on", interaction.edited[-1])

    def test_excluded_channels_are_counted_in_the_menu(self) -> None:
        text = _render_status(
            {"lab_name": "PULSE", "listening": True, "excluded": ["1", "2"]}
        )
        self.assertIn("never reading 2 channel(s)", text)


class MarkerTests(unittest.TestCase):
    def test_the_notice_states_the_three_things_that_matter(self) -> None:
        text = _marker_text([])
        self.assertIn("Mylo is listening in this server", text)
        self.assertIn("Nobody is included unless they choose to be", text)
        self.assertIn("I do not keep your messages", text)
        self.assertIn("/mylo listening off", text)

    def test_the_notice_names_the_channels_it_never_reads(self) -> None:
        self.assertIn("<#42>", _marker_text(["42"]))

    def test_the_notice_says_nothing_about_exclusions_when_there_are_none(self):
        self.assertNotIn("I never read", _marker_text([]))


class ListeningControlTests(unittest.TestCase):
    def test_turning_it_on_posts_and_pins_the_notice(self) -> None:
        fake = FakeListening()
        view = _view()
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_listening(interaction, on=True))
        self.assertEqual(len(interaction.channel.sent), 1)
        self.assertIn("Mylo is listening", interaction.channel.sent[0])
        self.assertTrue(interaction.channel.message.pinned)
        self.assertEqual(fake.markers, [("900", "5", "77")])

    def test_turning_it_on_says_members_still_have_to_opt_in(self) -> None:
        fake = FakeListening()
        view = _view()
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_listening(interaction, on=True))
        self.assertIn("Each member still chooses", interaction.edited[-1])

    def test_turning_it_off_says_the_buffer_went_with_it(self) -> None:
        fake = FakeListening()
        view = _view()
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_listening(interaction, on=False))
        self.assertIn("deleted straight away", interaction.edited[-1])
        self.assertEqual(interaction.channel.sent, [])  # no notice for "off"

    def test_a_refused_change_says_so_and_changes_nothing(self) -> None:
        fake = FakeListening(status="not_manager")
        view = _view()
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_listening(interaction, on=True))
        self.assertIn("Nothing was changed", interaction.edited[-1])
        self.assertEqual(interaction.channel.sent, [])

    def test_an_existing_notice_is_edited_rather_than_repeated(self) -> None:
        fake = FakeListening()
        view = _view(
            {"lab_name": "PULSE", "marker_channel_id": "5", "marker_message_id": "77"}
        )
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_listening(interaction, on=True))
        self.assertEqual(interaction.channel.sent, [])
        self.assertIn("Mylo is listening", interaction.channel.message.content)

    def test_a_notice_that_cannot_be_posted_is_reported_not_swallowed(self) -> None:
        """People should be able to see that Mylo is listening, so a failure is loud."""
        fake = FakeListening()
        view = _view()
        interaction = FakeInteraction(channel=FakeChannel(fails=True))
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_listening(interaction, on=True))
        self.assertIn("could not post the listening notice", interaction.edited[-1])


class ExclusionTests(unittest.TestCase):
    def test_choosing_a_channel_excludes_it(self) -> None:
        fake = FakeListening()
        view = _view({"lab_name": "PULSE", "excluded": []})
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_exclusion(interaction, "42"))
        self.assertEqual(fake.calls[-1], ("channel", "42", "excluded", True))
        self.assertIn("never read <#42>", interaction.edited[-1])

    def test_choosing_it_again_lifts_the_exclusion(self) -> None:
        fake = FakeListening(payload={"excluded": ["42"]})
        view = _view({"lab_name": "PULSE", "excluded": ["42"]})
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_exclusion(interaction, "42"))
        self.assertEqual(fake.calls[-1], ("channel", "42", "excluded", False))
        self.assertIn("no longer excluded", interaction.edited[-1])

    def test_a_new_exclusion_updates_the_visible_notice(self) -> None:
        """The notice lists what Mylo never reads, so it cannot go stale."""
        fake = FakeListening(payload={"listening": True, "excluded": []})
        view = _view({"lab_name": "PULSE", "listening": True, "excluded": []})
        interaction = FakeInteraction()
        with mock.patch.object(setup_module, "listening", fake):
            _run(view._apply_exclusion(interaction, "42"))
        self.assertIn("<#42>", interaction.channel.sent[0])


if __name__ == "__main__":
    unittest.main()

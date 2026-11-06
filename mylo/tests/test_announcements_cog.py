"""The announcement buttons on Mylo's forum threads: ``ann:<post>:<action>``.

The cog only routes: every decision is the backend's, reached through
``linking.announcement_action``, which is patched here so no ORM is touched.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

from mylo.bot.cogs import announcements as module
from mylo.bot.cogs.announcements import AnnouncementsCog, NotForUsForm, RemindPicker


def _run(coro):
    return asyncio.run(coro)


class FakeResponse:
    def __init__(self) -> None:
        self.deferred, self.modals = [], []

    async def defer(self, **kwargs):
        self.deferred.append(kwargs)

    async def send_modal(self, modal):
        self.modals.append(modal)


class FakeFollowup:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, text, **kwargs):
        self.sent.append((text, kwargs))


def _interaction(custom_id: str, guild_id=1507):
    return SimpleNamespace(
        type=discord.InteractionType.component,
        data={"custom_id": custom_id},
        user=SimpleNamespace(id=111),
        guild_id=guild_id,
        response=FakeResponse(),
        followup=FakeFollowup(),
    )


class AnnouncementButtonTests(unittest.TestCase):
    def _press(self, custom_id, reply=("ok", {"message": "👍 Noted."})):
        calls = []

        async def action(*args, **kwargs):
            calls.append((args, kwargs))
            return reply

        interaction = _interaction(custom_id)
        cog = AnnouncementsCog(bot=SimpleNamespace())
        with mock.patch.object(module.linking, "announcement_action", action):
            _run(cog.on_interaction(interaction))
        return interaction, calls

    def test_interested_is_routed_with_the_presser_and_answered_privately(self):
        interaction, calls = self._press("ann:42:interested")
        self.assertEqual(calls, [(("111", "42", "interested"), {"guild_id": "1507"})])
        self.assertEqual(interaction.followup.sent[0][0], "👍 Noted.")
        self.assertTrue(interaction.followup.sent[0][1]["ephemeral"])

    def test_remind_me_opens_a_private_picker(self):
        options = [{"value": "2w", "label": "2 weeks before · Thu, Dec 31", "default": True}]
        interaction, _ = self._press(
            "ann:42:remind", reply=("ok", {"message": "Remind you?", "options": options})
        )
        text, kwargs = interaction.followup.sent[0]
        self.assertEqual(text, "Remind you?")
        self.assertIsInstance(kwargs["view"], RemindPicker)
        self.assertTrue(kwargs["ephemeral"])

    def test_not_for_us_asks_why_in_a_form(self):
        interaction, calls = self._press("ann:42:notforus")
        self.assertEqual(calls, [])
        self.assertIsInstance(interaction.response.modals[0], NotForUsForm)

    def test_other_buttons_are_not_ours(self):
        interaction, calls = self._press("ambient:42:reports")
        self.assertEqual(calls, [])
        self.assertEqual(interaction.followup.sent, [])


if __name__ == "__main__":
    unittest.main()


class SearchLinkTests(unittest.TestCase):
    def test_announce_buttons_only_for_rows_with_options(self):
        from mylo.bot.cogs.mylo_commands import _announce_view

        async def build():
            return _announce_view(
                [
                    {"content_id": "c1", "announce": [
                        {"binding_id": 7, "purpose": "grants"}]},
                    {"content_id": "c2", "announce": []},
                ]
            )

        view = _run(build())
        self.assertEqual([b.custom_id for b in view.children], ["annx:7:c1"])
        self.assertIsNone(_run(self._none()))

    async def _none(self):
        from mylo.bot.cogs.mylo_commands import _announce_view

        return _announce_view([{"content_id": "c1", "announce": []}])

    def test_announce_to_is_routed_to_the_manual_announce(self):
        calls = []

        async def manual(*args):
            calls.append(args)
            return ("ok", {"message": "📣 Posted → https://discord.com/channels/1/2"})

        interaction = _interaction("annx:7:c1")
        interaction.message = None
        cog = AnnouncementsCog(bot=SimpleNamespace())
        with mock.patch.object(module.linking, "announcement_manual", manual):
            _run(cog.on_interaction(interaction))
        self.assertEqual(calls, [("111", "1507", "7", "c1")])
        self.assertIn("Posted", interaction.followup.sent[0][0])

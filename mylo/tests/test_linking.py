"""Command dispatch routing for the linking cogs, without Django.

We patch ``mylo.linking.mycelium.db`` so no ORM (and no ``django.setup()``) is
touched: the fake records which synchronous body each call routed to. This pins the
argument validation and channel-gate branching for ``/activate`` (personal),
``/activate-lab`` (server), and ``/setup`` (channel config) before any DB work.
"""

from __future__ import annotations

import unittest
from unittest import mock

from mylo import linking


def _fake_db_factory(activation_channel: str = ""):
    async def _fake_db(fn, /, *args, **kwargs):
        # The `/activate` channel gate reads the activation channel first.
        if fn is linking._activation_channel:
            return activation_channel
        return ("routed", fn.__name__)

    return _fake_db


class ActivateDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_code_is_rejected_before_any_db(self) -> None:
        with mock.patch.object(linking.mycelium, "db", side_effect=AssertionError):
            status, _ = await linking.activate("1", code="", channel_id="9")
        self.assertEqual(status, "no_code")

    async def test_code_routes_to_identity_redemption(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db_factory("")):
            status, name = await linking.activate(
                "1", code="AAAA-BBBB", channel_id="9"
            )
        self.assertEqual((status, name), ("routed", "_activate_code_sync"))

    async def test_code_outside_activation_channel_is_gated(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db_factory("123")):
            status, _ = await linking.activate("1", code="AAAA-BBBB", channel_id="9")
        self.assertEqual(status, "wrong_channel")


class ActivateLabDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_in_a_dm_needs_a_guild(self) -> None:
        with mock.patch.object(linking.mycelium, "db", side_effect=AssertionError):
            status, _ = await linking.activate_lab("1", code="12345-67890", guild_id="")
        self.assertEqual(status, "no_guild")

    async def test_missing_code_is_rejected_before_any_db(self) -> None:
        with mock.patch.object(linking.mycelium, "db", side_effect=AssertionError):
            status, _ = await linking.activate_lab("1", code="", guild_id="9")
        self.assertEqual(status, "no_code")

    async def test_code_routes_to_lab_activation(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db_factory("")):
            status, name = await linking.activate_lab(
                "1", code="12345-67890", guild_id="9", guild_name="G"
            )
        self.assertEqual((status, name), ("routed", "_activate_lab_code_sync"))


class SetupDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_needs_a_guild(self) -> None:
        with mock.patch.object(linking.mycelium, "db", side_effect=AssertionError):
            status, _ = await linking.setup_state("1", "")
        self.assertEqual(status, "no_guild")

    async def test_state_routes_to_setup_state(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db_factory("")):
            status, name = await linking.setup_state("1", "9")
        self.assertEqual((status, name), ("routed", "_setup_state_sync"))

    async def test_bind_routes_to_channel_config(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db_factory("")):
            status, name = await linking.bind_setup_channel(
                "1", "9", kind="deadlines", channel_id="5"
            )
        self.assertEqual((status, name), ("routed", "_bind_setup_channel_sync"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

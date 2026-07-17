"""``/activate`` dispatch routing, without Django.

We patch ``mylo.linking.mycelium.db`` so no ORM (and no ``django.setup()``) is
touched: the fake records which synchronous body each call routed to. This pins
the code/lab/both/neither branching that decides whether ``/activate`` links an
identity, connects a server, or shows help.
"""

from __future__ import annotations

import unittest
from unittest import mock

from mylo import linking


async def _fake_db(fn, /, *args, **kwargs):
    # The channel gate reads the activation channel first; report "unset" so the
    # code path proceeds to redemption instead of short-circuiting.
    if fn is linking._activation_channel:
        return ""
    return ("routed", fn.__name__)


class ActivateDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_code_and_lab_together_is_rejected_before_any_db(self) -> None:
        with mock.patch.object(linking.mycelium, "db", side_effect=AssertionError):
            status, _ = await linking.activate(
                "1", code="AAAA-BBBB", lab_slug="my-lab", guild_id="9"
            )
        self.assertEqual(status, "ambiguous")

    async def test_code_routes_to_identity_redemption(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db):
            status, name = await linking.activate(
                "1", code="AAAA-BBBB", guild_id="9", channel_id="9"
            )
        self.assertEqual((status, name), ("routed", "_activate_code_sync"))

    async def test_lab_routes_to_server_activation(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db):
            status, name = await linking.activate(
                "1", lab_slug="my-lab", guild_id="9", guild_name="G"
            )
        self.assertEqual((status, name), ("routed", "_activate_lab_sync"))

    async def test_no_args_in_a_guild_routes_to_help(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db):
            status, name = await linking.activate("1", guild_id="9", guild_name="G")
        self.assertEqual((status, name), ("routed", "_activate_help_sync"))

    async def test_lab_in_a_dm_needs_a_guild(self) -> None:
        with mock.patch.object(linking.mycelium, "db", side_effect=AssertionError):
            status, _ = await linking.activate("1", lab_slug="my-lab", guild_id="")
        self.assertEqual(status, "no_guild")


class SetupChannelDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_needs_a_guild(self) -> None:
        with mock.patch.object(linking.mycelium, "db", side_effect=AssertionError):
            status, _ = await linking.setup_channel("1", "", channel_id="5")
        self.assertEqual(status, "no_guild")

    async def test_setup_routes_to_channel_config(self) -> None:
        with mock.patch.object(linking.mycelium, "db", _fake_db):
            status, name = await linking.setup_channel("1", "9", channel_id="5")
        self.assertEqual((status, name), ("routed", "_setup_channel_sync"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

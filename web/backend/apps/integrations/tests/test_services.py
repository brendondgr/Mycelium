"""Service-layer tests: OAuth flows (HTTP mocked), probe outcomes, activation
lockout survival, and the ERROR_CHANNEL sink dedupe/circuit-breaker."""

from __future__ import annotations

import importlib
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Lab
from apps.integrations.models import DiscordGuildLink, DiscordIdentity
from apps.integrations.services import (
    activation,
    discord_api,
    errors,
    oauth,
    probe,
    resolve,
    state,
)
from apps.integrations.services.discord_api import DiscordHTTPError, RawResponse

from .base import clear_discord_cache, discord_test_settings

User = get_user_model()


@discord_test_settings
class OAuthUserLinkTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.user = User.objects.create_user("oauth-user", password="x")

    def test_complete_user_link_binds_authoritative_snowflake(self):
        token = {
            "access_token": "AT",
            "refresh_token": "RT",
            "expires_in": 604800,
            "scope": "identify applications.commands",
        }
        with mock.patch.object(discord_api, "exchange_code", return_value=token), \
             mock.patch.object(
                 discord_api,
                 "get_current_user",
                 return_value={"id": "999", "username": "cool", "global_name": "Cool"},
             ):
            identity = oauth.complete_user_link(self.user, "code-123")

        self.assertEqual(identity.discord_user_id, "999")  # from /users/@me, not input
        self.assertEqual(identity.state, DiscordIdentity.State.ACTIVE)
        self.assertEqual(identity.access_token, "AT")
        self.assertIn("applications.commands", identity.scopes)
        self.assertIsNotNone(identity.token_expires_at)

    def test_refresh_invalid_grant_revokes(self):
        identity = resolve.bind_identity(
            self.user, "999", method=resolve.LINK_OAUTH,
            tokens={"access_token": "AT", "refresh_token": "RT"},
        )
        with mock.patch.object(
            discord_api,
            "refresh_access_token",
            side_effect=DiscordHTTPError(400, None, "invalid_grant"),
        ):
            ok = oauth.refresh_identity(identity)
        self.assertFalse(ok)
        identity.refresh_from_db()
        self.assertEqual(identity.state, DiscordIdentity.State.REVOKED)


@discord_test_settings
class OAuthGuildLinkTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.lab = Lab.objects.create(name="Lab", slug="lab")
        self.installer = User.objects.create_user("installer", password="x")

    def test_complete_guild_link_binds_from_exchange_guild(self):
        token = {"access_token": "AT", "guild": {"id": "g-1", "name": "Guild"}}
        with mock.patch.object(discord_api, "exchange_code", return_value=token), \
             mock.patch.object(discord_api, "create_message") as msg:
            link = oauth.complete_guild_link(
                self.lab, "code", installed_by=self.installer
            )
        self.assertEqual(link.guild_id, "g-1")
        self.assertTrue(link.verified_via_code_grant)
        self.assertEqual(link.state, DiscordGuildLink.State.PENDING_SETUP)
        # No system_channel_id in the guild object → no nudge attempted.
        msg.assert_not_called()

    def test_missing_guild_object_raises(self):
        with mock.patch.object(
            discord_api, "exchange_code", return_value={"access_token": "AT"}
        ):
            with self.assertRaises(ValueError):
                oauth.complete_guild_link(self.lab, "code")


@discord_test_settings
class ProbeTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.user = User.objects.create_user("probe-user", password="x")
        self.identity = resolve.bind_identity(
            self.user, "777", method=resolve.LINK_OAUTH
        )

    def test_probe_success_sets_dm_ok(self):
        with mock.patch.object(
            discord_api, "open_dm_raw",
            return_value=RawResponse(200, {"id": "chan-1"})
        ), mock.patch.object(
            discord_api, "create_message", return_value=RawResponse(200, {})
        ):
            result = probe.run_probe(self.identity)
        self.assertTrue(result.dm_ok)
        self.identity.refresh_from_db()
        self.assertTrue(self.identity.dm_ok)
        self.assertEqual(self.identity.dm_channel_id, "chan-1")

    def test_probe_blocked_50007_sets_dm_false_state_unchanged(self):
        with mock.patch.object(
            discord_api, "open_dm_raw",
            return_value=RawResponse(200, {"id": "chan-1"})
        ), mock.patch.object(
            discord_api, "create_message",
            return_value=RawResponse(403, {"code": 50007})
        ):
            result = probe.run_probe(self.identity)
        self.assertFalse(result.dm_ok)
        self.identity.refresh_from_db()
        self.assertFalse(self.identity.dm_ok)
        self.assertEqual(self.identity.last_error_code, 50007)
        self.assertEqual(self.identity.state, DiscordIdentity.State.ACTIVE)

    def test_probe_429_is_transient_no_state_flip(self):
        with mock.patch.object(
            discord_api, "open_dm_raw",
            return_value=RawResponse(429, {}, retry_after=2.5)
        ):
            result = probe.run_probe(self.identity)
        self.assertTrue(result.transient)
        self.assertEqual(result.retry_after, 2.5)
        self.identity.refresh_from_db()
        self.assertIsNone(self.identity.dm_ok)  # untouched


@discord_test_settings
class ActivationLockoutTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.user = User.objects.create_user("lock-user", password="x")

    def test_lockout_after_threshold_failures(self):
        did = "d-attacker"
        self.assertFalse(state.is_locked_out(did))
        for _ in range(5):
            r = activation.redeem("BADCODE1", did)
        self.assertEqual(r.outcome, activation.RedeemOutcome.NOT_FOUND)
        self.assertTrue(state.is_locked_out(did))
        # Further attempts are short-circuited as locked out.
        self.assertEqual(
            activation.redeem("BADCODE1", did).outcome,
            activation.RedeemOutcome.LOCKED_OUT,
        )

    def test_lockout_survives_process_restart(self):
        did = "d-persist"
        for _ in range(5):
            activation.redeem("WRONGXYZ", did)
        self.assertTrue(state.is_locked_out(did))
        # Simulate a process restart: reload the module. The lock lives in the
        # cache backend, not module-global memory, so it must persist.
        importlib.reload(state)
        self.assertTrue(state.is_locked_out(did))


@discord_test_settings
class ErrorSinkTests(TestCase):
    def setUp(self):
        clear_discord_cache()

    def test_dedupe_one_message_per_bucket(self):
        with mock.patch.object(errors, "_emit") as emit:
            errors.note_incident("probe", "500", detail="boom")
            errors.note_incident("probe", "500", detail="boom")
            errors.note_incident("probe", "500", detail="boom")
        self.assertEqual(emit.call_count, 1)  # rolled up, not 3

    def test_distinct_buckets_each_emit(self):
        with mock.patch.object(errors, "_emit") as emit:
            errors.note_incident("probe", "500")
            errors.note_incident("oauth", "400")
        self.assertEqual(emit.call_count, 2)

    def test_circuit_breaker_goes_quiet_under_flood(self):
        with mock.patch.object(errors, "_emit") as emit:
            # 25 distinct buckets → rate threshold (20) trips the breaker.
            for i in range(25):
                errors.note_incident("comp", i)
        # One "cascade" emit + the pre-threshold emits, but NOT 25.
        self.assertLess(emit.call_count, 25)

    def test_post_embed_uses_transport_and_reports_success(self):
        seen = {}

        def transport(url, data, headers):
            seen["url"] = url
            seen["auth"] = headers.get("Authorization")
            return 204

        ok = errors.post_embed("t", "b", transport=transport)
        self.assertTrue(ok)
        self.assertIn("/channels/999000/messages", seen["url"])
        self.assertEqual(seen["auth"], "Bot test-bot-token")

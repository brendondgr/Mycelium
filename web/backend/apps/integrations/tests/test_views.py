"""HTTP flow tests for the portal + OAuth callback endpoints."""

from __future__ import annotations

import urllib.parse
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Lab, LabMembership
from apps.integrations.models import DiscordGuildLink, DiscordIdentity
from apps.integrations.services import discord_api, resolve

from .base import clear_discord_cache, discord_test_settings

User = get_user_model()


def _state_from(url: str) -> str:
    query = urllib.parse.urlparse(url).query
    return urllib.parse.parse_qs(query)["state"][0]


@discord_test_settings
class PathAViewTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.user = User.objects.create_user("web-user", password="x")
        self.client.force_login(self.user)

    def _start(self) -> str:
        resp = self.client.get(reverse("discord-start"))
        self.assertEqual(resp.status_code, 200)
        url = resp.json()["authorize_url"]
        self.assertIn("client_id=test-client-id", url)
        self.assertIn("integration_type=1", url)
        return _state_from(url)

    def _callback(self, state, code="code-1"):
        return self.client.get(
            reverse("discord-callback"), {"code": code, "state": state}
        )

    def test_full_link_flow_success(self):
        state = self._start()
        with mock.patch.object(
            discord_api, "exchange_code",
            return_value={"access_token": "AT", "refresh_token": "RT",
                          "expires_in": 100, "scope": "identify"},
        ), mock.patch.object(
            discord_api, "get_current_user",
            return_value={"id": "abc", "username": "u", "global_name": ""},
        ), mock.patch(
            "apps.integrations.services.probe.run_probe"
        ):
            resp = self._callback(state)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("discord=linked", resp["Location"])
        self.assertTrue(
            DiscordIdentity.objects.filter(
                user=self.user, discord_user_id="abc",
                state=DiscordIdentity.State.ACTIVE,
            ).exists()
        )

    def test_tampered_state_400_no_row(self):
        resp = self._callback("not-a-real-nonce")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(DiscordIdentity.objects.exists())

    def test_replayed_state_400(self):
        state = self._start()
        with mock.patch.object(
            discord_api, "exchange_code",
            return_value={"access_token": "AT", "scope": "identify"},
        ), mock.patch.object(
            discord_api, "get_current_user",
            return_value={"id": "abc", "username": "u"},
        ), mock.patch("apps.integrations.services.probe.run_probe"):
            first = self._callback(state)
            second = self._callback(state)  # nonce already consumed
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 400)

    def test_snowflake_bound_to_other_user_409(self):
        other = User.objects.create_user("other", password="x")
        resolve.bind_identity(other, "taken", method=resolve.LINK_OAUTH)
        state = self._start()
        with mock.patch.object(
            discord_api, "exchange_code",
            return_value={"access_token": "AT", "scope": "identify"},
        ), mock.patch.object(
            discord_api, "get_current_user",
            return_value={"id": "taken", "username": "u"},
        ):
            resp = self._callback(state)
        self.assertEqual(resp.status_code, 409)

    def test_status_reflects_link(self):
        resolve.bind_identity(
            self.user, "mine", method=resolve.LINK_OAUTH, username="me"
        )
        resp = self.client.get(reverse("discord-status"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["connected"])

    def test_status_empty_when_unlinked(self):
        resp = self.client.get(reverse("discord-status"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["connected"])

    def test_disconnect_deletes_and_revokes(self):
        resolve.bind_identity(
            self.user, "mine", method=resolve.LINK_OAUTH,
            tokens={"access_token": "AT", "refresh_token": "RT"},
        )
        with mock.patch.object(discord_api, "revoke_token", return_value=True) as rev:
            resp = self.client.post(reverse("discord-disconnect"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(DiscordIdentity.objects.filter(user=self.user).exists())
        self.assertTrue(rev.called)

    def test_issue_activation_code(self):
        resp = self.client.post(reverse("discord-code"))
        self.assertEqual(resp.status_code, 200)
        code = resp.json()["code"]
        self.assertRegex(code, r"^[0-9A-Z]{4}-[0-9A-Z]{4}$")

    def test_endpoints_require_auth(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("discord-start")).status_code, 403)
        self.assertEqual(self.client.get(reverse("discord-status")).status_code, 403)


@discord_test_settings
class PathCViewTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.lab = Lab.objects.create(name="Lab", slug="lab")
        self.manager = User.objects.create_user("manager", password="x")
        self.member = User.objects.create_user("member", password="x")
        LabMembership.objects.create(
            user=self.manager, lab=self.lab, role=LabMembership.Role.OWNER
        )
        LabMembership.objects.create(
            user=self.member, lab=self.lab, role=LabMembership.Role.MEMBER
        )

    def test_guild_start_requires_manager(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("discord-guild-start"), {"lab": "lab"})
        self.assertEqual(resp.status_code, 403)

    def test_guild_start_requires_own_identity(self):
        # Manager with no linked Discord identity → gated (D-6).
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("discord-guild-start"), {"lab": "lab"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json().get("code"), "link_required")

    def test_guild_start_ok_for_linked_manager(self):
        resolve.bind_identity(self.manager, "d-mgr", method=resolve.LINK_OAUTH)
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("discord-guild-start"), {"lab": "lab"})
        self.assertEqual(resp.status_code, 200)
        url = resp.json()["authorize_url"]
        self.assertIn("integration_type=0", url)
        self.assertIn("scope=bot", url)

    def test_guild_callback_installs_pending_setup(self):
        resolve.bind_identity(self.manager, "d-mgr", method=resolve.LINK_OAUTH)
        self.client.force_login(self.manager)
        start = self.client.get(reverse("discord-guild-start"), {"lab": "lab"})
        state = _state_from(start.json()["authorize_url"])
        with mock.patch.object(
            discord_api, "exchange_code",
            return_value={"access_token": "AT", "guild": {"id": "g-77", "name": "S"}},
        ), mock.patch.object(discord_api, "create_message"):
            resp = self.client.get(
                reverse("discord-guild-callback"), {"code": "c", "state": state}
            )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("discord=installed", resp["Location"])
        link = DiscordGuildLink.objects.get(guild_id="g-77")
        self.assertEqual(link.state, DiscordGuildLink.State.PENDING_SETUP)
        self.assertTrue(link.verified_via_code_grant)

    def test_guild_callback_conflict_409(self):
        # g-77 already bound to another lab.
        other = Lab.objects.create(name="Other", slug="other")
        resolve.bind_guild(other, {"id": "g-77"})
        resolve.bind_identity(self.manager, "d-mgr", method=resolve.LINK_OAUTH)
        self.client.force_login(self.manager)
        start = self.client.get(reverse("discord-guild-start"), {"lab": "lab"})
        state = _state_from(start.json()["authorize_url"])
        with mock.patch.object(
            discord_api, "exchange_code",
            return_value={"access_token": "AT", "guild": {"id": "g-77"}},
        ):
            resp = self.client.get(
                reverse("discord-guild-callback"), {"code": "c", "state": state}
            )
        self.assertEqual(resp.status_code, 409)

    def test_guild_status_requires_manager(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("discord-guild-status"), {"lab": "lab"})
        self.assertEqual(resp.status_code, 403)

    def test_guild_status_not_connected(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("discord-guild-status"), {"lab": "lab"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["synced"])
        self.assertIsNone(body["state"])

    def test_guild_status_pending_then_active(self):
        # Installed but unconfirmed → pending_setup, not yet synced.
        resolve.bind_guild(self.lab, {"id": "g-77", "name": "S"})
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("discord-guild-status"), {"lab": "lab"})
        body = resp.json()
        self.assertFalse(body["synced"])
        self.assertEqual(body["state"], "pending_setup")
        self.assertEqual(body["guild_name"], "S")
        # A manager confirms it → active → synced.
        resolve.bind_identity(self.manager, "d-mgr", method=resolve.LINK_OAUTH)
        resolve.confirm_guild("g-77", confirmed_by=self.manager)
        resp = self.client.get(reverse("discord-guild-status"), {"lab": "lab"})
        body = resp.json()
        self.assertTrue(body["synced"])
        self.assertEqual(body["state"], "active")

"""Path C — lab activation code: issue/redeem, guild bind, conflict, add-on gate,
lockout, the two independent `/setup` channels, and the manager-gated `/lab-code`
endpoint. Real Discord HTTP is never touched here — binding is pure ORM."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership
from apps.integrations.models import DiscordGuildLink, DiscordLabActivationCode
from apps.integrations.services import lab_activation, resolve, state

from .base import clear_discord_cache, discord_test_settings, grant_bot_server

User = get_user_model()


@discord_test_settings
class LabActivationServiceTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.lab = Lab.objects.create(name="Reef Lab", slug="reef")
        grant_bot_server(self.lab)
        self.manager = User.objects.create_user("mgr", password="x")
        LabMembership.objects.create(
            user=self.manager, lab=self.lab, role=LabMembership.Role.OWNER
        )

    def test_issue_returns_10_digit_grouped_code_hash_only(self):
        code = lab_activation.issue_code(self.manager, self.lab)
        self.assertRegex(code, r"^\d{5}-\d{5}$")
        row = DiscordLabActivationCode.objects.get(lab=self.lab)
        self.assertEqual(len(row.code_hash), 64)  # sha256 hex, plaintext never stored
        self.assertIsNone(row.consumed_at)
        self.assertEqual(row.issued_by_id, self.manager.id)

    def test_redeem_binds_this_guild_active(self):
        code = lab_activation.issue_code(self.manager, self.lab)
        result = lab_activation.redeem(code, "d-user", "g-1", "Reef Server")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.OK)
        self.assertEqual(result.lab_name, "Reef Lab")
        link = DiscordGuildLink.objects.get(guild_id="g-1")
        self.assertEqual(link.lab_id, self.lab.id)
        self.assertEqual(link.state, DiscordGuildLink.State.ACTIVE)
        # The code carries authority, not the forgeable OAuth redirect.
        self.assertFalse(link.verified_via_code_grant)
        row = DiscordLabActivationCode.objects.get(lab=self.lab)
        self.assertIsNotNone(row.consumed_at)
        self.assertEqual(row.consumed_guild_id, "g-1")
        self.assertEqual(row.consumed_by_discord_id, "d-user")

    def test_redeem_needs_no_linked_identity(self):
        # The redeemer has no DiscordIdentity — possession of the code is enough.
        code = lab_activation.issue_code(self.manager, self.lab)
        result = lab_activation.redeem(code, "d-anon", "g-2")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.OK)
        self.assertIsNone(DiscordGuildLink.objects.get(guild_id="g-2").installed_by)

    def test_dashes_and_spaces_are_cosmetic(self):
        code = lab_activation.issue_code(self.manager, self.lab)  # NNNNN-NNNNN
        digits = code.replace("-", "")
        spaced = f" {digits[:3]} {digits[3:]} "
        self.assertEqual(
            lab_activation.redeem(spaced, "d-user", "g-1").outcome,
            lab_activation.RedeemOutcome.OK,
        )

    def test_single_use(self):
        code = lab_activation.issue_code(self.manager, self.lab)
        lab_activation.redeem(code, "d-user", "g-1")
        again = lab_activation.redeem(code, "d-user", "g-1")
        self.assertEqual(again.outcome, lab_activation.RedeemOutcome.ALREADY_USED)

    def test_bad_code_not_found(self):
        result = lab_activation.redeem("0000000000", "d-user", "g-1")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.NOT_FOUND)

    def test_no_guild_is_conflict(self):
        code = lab_activation.issue_code(self.manager, self.lab)
        result = lab_activation.redeem(code, "d-user", "")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.CONFLICT)
        # Not consumed — no guild to bind.
        self.assertIsNone(DiscordLabActivationCode.objects.get(lab=self.lab).consumed_at)

    def test_conflict_when_guild_bound_to_other_lab_does_not_consume(self):
        other = Lab.objects.create(name="Other", slug="other")
        resolve.bind_guild(other, {"id": "g-1"})  # g-1 already Other's
        code = lab_activation.issue_code(self.manager, self.lab)
        result = lab_activation.redeem(code, "d-user", "g-1")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.CONFLICT)
        self.assertIsNone(DiscordLabActivationCode.objects.get(lab=self.lab).consumed_at)

    def test_addon_required_gate_does_not_consume(self):
        bare = Lab.objects.create(name="Bare", slug="bare")
        LabMembership.objects.create(
            user=self.manager, lab=bare, role=LabMembership.Role.OWNER
        )
        code = lab_activation.issue_code(self.manager, bare)
        result = lab_activation.redeem(code, "d-user", "g-9")
        self.assertEqual(
            result.outcome, lab_activation.RedeemOutcome.BOT_SERVER_REQUIRED
        )
        self.assertFalse(DiscordGuildLink.objects.filter(guild_id="g-9").exists())
        # Not consumed — add the add-on, then reuse the same code.
        self.assertIsNone(DiscordLabActivationCode.objects.get(lab=bare).consumed_at)

    def test_issue_supersedes_prior_live_code(self):
        first = lab_activation.issue_code(self.manager, self.lab)
        second = lab_activation.issue_code(self.manager, self.lab)
        self.assertEqual(
            lab_activation.redeem(first, "d-user", "g-1").outcome,
            lab_activation.RedeemOutcome.ALREADY_USED,
        )
        self.assertEqual(
            lab_activation.redeem(second, "d-user", "g-1").outcome,
            lab_activation.RedeemOutcome.OK,
        )

    def test_lockout_after_threshold_failures(self):
        did = "d-brute"
        for _ in range(5):
            r = lab_activation.redeem("1234512345", did, "g-1")
        self.assertEqual(r.outcome, lab_activation.RedeemOutcome.NOT_FOUND)
        self.assertTrue(state.is_locked_out(did))
        self.assertEqual(
            lab_activation.redeem("1234512345", did, "g-1").outcome,
            lab_activation.RedeemOutcome.LOCKED_OUT,
        )

    def test_conflict_does_not_count_toward_lockout(self):
        other = Lab.objects.create(name="Other", slug="other")
        resolve.bind_guild(other, {"id": "g-1"})
        did = "d-honest"
        for _ in range(6):
            code = lab_activation.issue_code(self.manager, self.lab)
            r = lab_activation.redeem(code, did, "g-1")
            self.assertEqual(r.outcome, lab_activation.RedeemOutcome.CONFLICT)
        self.assertFalse(state.is_locked_out(did))  # honest conflicts don't lock out

    def test_setup_channels_are_independent_and_optional(self):
        code = lab_activation.issue_code(self.manager, self.lab)
        lab_activation.redeem(code, "d-user", "g-1")
        now = timezone.now()
        resolve.set_announcement_channel("g-1", "chan-dead", verified_at=now)
        resolve.set_updates_channel("g-1", "chan-upd", verified_at=now)
        get_dead = resolve.get_announcement_channel_for_lab
        self.assertEqual(get_dead(self.lab), "chan-dead")
        self.assertEqual(resolve.get_updates_channel_for_lab(self.lab), "chan-upd")
        # Opt out of deadlines without touching updates.
        resolve.clear_announcement_channel("g-1")
        self.assertEqual(resolve.get_announcement_channel_for_lab(self.lab), "")
        self.assertEqual(resolve.get_updates_channel_for_lab(self.lab), "chan-upd")
        resolve.clear_updates_channel("g-1")
        self.assertEqual(resolve.get_updates_channel_for_lab(self.lab), "")


@discord_test_settings
class LabActivationCodeViewTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.lab = Lab.objects.create(name="Lab", slug="lab")
        grant_bot_server(self.lab)
        self.manager = User.objects.create_user("manager", password="x")
        self.member = User.objects.create_user("member", password="x")
        LabMembership.objects.create(
            user=self.manager, lab=self.lab, role=LabMembership.Role.OWNER
        )
        LabMembership.objects.create(
            user=self.member, lab=self.lab, role=LabMembership.Role.MEMBER
        )

    def _url(self, slug="lab"):
        return reverse("discord-lab-code") + f"?lab={slug}"

    def test_manager_issues_code(self):
        self.client.force_login(self.manager)
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertRegex(resp.json()["code"], r"^\d{5}-\d{5}$")
        self.assertIn("expires_in", resp.json())
        self.assertTrue(DiscordLabActivationCode.objects.filter(lab=self.lab).exists())

    def test_member_cannot_issue_403(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(self._url()).status_code, 403)

    def test_unknown_lab_404(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(self._url("nope")).status_code, 404)

    def test_requires_auth_403(self):
        self.assertEqual(self.client.post(self._url()).status_code, 403)

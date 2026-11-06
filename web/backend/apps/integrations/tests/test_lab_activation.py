"""Path C — lab and department activation codes: issue/redeem, bindings (one server
holds many, one target binds in many servers), add-on gate, lockout, the two
independent `/setup` channels, removal, and the manager-gated code endpoints. Real
Discord HTTP is never touched here — binding is pure ORM."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Department, DeptMembership, Lab, LabMembership
from apps.integrations.models import (
    DiscordDepartmentActivationCode,
    DiscordGuildLink,
    DiscordLabActivationCode,
    DiscordTargetBinding,
)
from apps.integrations.services import lab_activation, resolve, state

from .base import clear_discord_cache, discord_test_settings

User = get_user_model()


@discord_test_settings
class LabActivationServiceTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        # No Mylo-server add-on granted: lab activation must not require one.
        self.lab = Lab.objects.create(name="Reef Lab", slug="reef")
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
        binding = link.bindings.get()
        self.assertEqual(binding.lab_id, self.lab.id)
        self.assertEqual(binding.state, DiscordTargetBinding.State.ACTIVE)
        self.assertEqual(link.state, DiscordGuildLink.State.ACTIVE)
        self.assertEqual(link.guild_name_cache, "Reef Server")
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

    def test_a_server_can_hold_two_labs(self):
        other = Lab.objects.create(name="Other", slug="other")
        resolve.bind_guild(other, {"id": "g-1"})  # g-1 already serves Other
        code = lab_activation.issue_code(self.manager, self.lab)
        result = lab_activation.redeem(code, "d-user", "g-1")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.OK)
        labs = set(
            DiscordTargetBinding.objects.filter(guild__guild_id="g-1").values_list(
                "lab_id", flat=True
            )
        )
        self.assertEqual(labs, {other.id, self.lab.id})

    def test_a_lab_can_be_bound_in_two_servers(self):
        for guild in ("g-own", "g-dept"):
            code = lab_activation.issue_code(self.manager, self.lab)
            self.assertEqual(
                lab_activation.redeem(code, "d-user", guild).outcome,
                lab_activation.RedeemOutcome.OK,
            )
        guilds = [b.guild.guild_id for b in resolve.bindings_for_lab(self.lab)]
        self.assertEqual(guilds, ["g-own", "g-dept"])

    def test_redeeming_twice_in_one_server_keeps_one_binding(self):
        for _ in range(2):
            code = lab_activation.issue_code(self.manager, self.lab)
            lab_activation.redeem(code, "d-user", "g-1")
        self.assertEqual(DiscordTargetBinding.objects.filter(lab=self.lab).count(), 1)

    def test_activates_without_any_billing_addon(self):
        # Regression: a valid code binds the guild even with no Mylo-server add-on —
        # the bot is already in the server, so activation must not gate on billing.
        bare = Lab.objects.create(name="Bare", slug="bare")  # no subscription/add-on
        LabMembership.objects.create(
            user=self.manager, lab=bare, role=LabMembership.Role.OWNER
        )
        code = lab_activation.issue_code(self.manager, bare)
        result = lab_activation.redeem(code, "d-user", "g-9")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.OK)
        binding = DiscordTargetBinding.objects.get(guild__guild_id="g-9")
        self.assertEqual(binding.lab_id, bare.id)
        self.assertEqual(binding.state, DiscordTargetBinding.State.ACTIVE)

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
        did = "d-honest"
        for _ in range(6):
            code = lab_activation.issue_code(self.manager, self.lab)
            r = lab_activation.redeem(code, did, "")  # no server to bind to
            self.assertEqual(r.outcome, lab_activation.RedeemOutcome.CONFLICT)
        self.assertFalse(state.is_locked_out(did))  # honest conflicts don't lock out

    def test_setup_channels_are_independent_and_optional(self):
        code = lab_activation.issue_code(self.manager, self.lab)
        lab_activation.redeem(code, "d-user", "g-1")
        binding = resolve.bindings_for_lab(self.lab)[0]
        now = timezone.now()
        resolve.set_route(binding, "deadlines", "chan-dead", verified_at=now)
        resolve.set_route(binding, "updates", "chan-upd", verified_at=now)
        get_dead = resolve.get_announcement_channel_for_lab
        self.assertEqual(get_dead(self.lab), "chan-dead")
        self.assertEqual(resolve.get_updates_channel_for_lab(self.lab), "chan-upd")
        # Opt out of deadlines without touching updates.
        resolve.clear_route(binding, "deadlines")
        self.assertEqual(resolve.get_announcement_channel_for_lab(self.lab), "")
        self.assertEqual(resolve.get_updates_channel_for_lab(self.lab), "chan-upd")
        resolve.clear_route(binding, "updates")
        self.assertEqual(resolve.get_updates_channel_for_lab(self.lab), "")

    def test_removing_one_binding_leaves_the_others(self):
        dept = Department.objects.create(owner=self.manager, name="Dept")
        for guild in ("g-own", "g-dept"):
            code = lab_activation.issue_code(self.manager, self.lab)
            lab_activation.redeem(code, "d-user", guild)
        dcode = lab_activation.issue_department_code(self.manager, dept)
        lab_activation.redeem_department(dcode, "d-user", "g-dept")
        own, in_dept = resolve.bindings_for_lab(self.lab)
        now = timezone.now()
        resolve.set_route(own, "updates", "c-own", verified_at=now)
        resolve.set_route(in_dept, "updates", "c-dept", verified_at=now)

        resolve.remove_binding(own)

        self.assertEqual(
            [b.guild.guild_id for b in resolve.bindings_for_lab(self.lab)], ["g-dept"]
        )
        self.assertEqual(resolve.get_updates_channel_for_lab(self.lab), "c-dept")
        self.assertEqual(len(resolve.bindings_for_department(dept)), 1)
        self.assertEqual(resolve.resolve_lab_for_guild("g-own"), None)
        self.assertEqual(resolve.resolve_lab_for_guild("g-dept"), self.lab)

    def test_the_primary_server_keeps_the_old_one_server_behaviour(self):
        """Reminders and the digest read one channel; the oldest binding with that
        route wins, so binding a second server never moves them."""
        for guild in ("g-own", "g-dept"):
            code = lab_activation.issue_code(self.manager, self.lab)
            lab_activation.redeem(code, "d-user", guild)
        own, in_dept = resolve.bindings_for_lab(self.lab)
        now = timezone.now()
        resolve.set_route(in_dept, "deadlines", "c-dept", verified_at=now)
        self.assertEqual(resolve.get_announcement_channel_for_lab(self.lab), "c-dept")
        resolve.set_route(own, "deadlines", "c-own", verified_at=now)
        self.assertEqual(resolve.get_announcement_channel_for_lab(self.lab), "c-own")


@discord_test_settings
class DepartmentActivationTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.head = User.objects.create_user("head", password="x")
        self.dept = Department.objects.create(owner=self.head, name="EOAS")
        DeptMembership.objects.create(
            user=self.head, department=self.dept, role=DeptMembership.Role.OWNER
        )
        self.lab = Lab.objects.create(
            name="Reef Lab", slug="reef", department=self.dept
        )

    def test_department_code_binds_the_department_not_its_labs(self):
        code = lab_activation.issue_department_code(self.head, self.dept)
        self.assertRegex(code, r"^\d{5}-\d{5}$")
        result = lab_activation.redeem_department(code, "d-head", "g-dept", "EOAS")
        self.assertEqual(result.outcome, lab_activation.RedeemOutcome.OK)
        self.assertEqual(result.lab_name, "EOAS")
        binding = DiscordTargetBinding.objects.get(guild__guild_id="g-dept")
        self.assertEqual(binding.department_id, self.dept.id)
        self.assertIsNone(binding.lab_id)
        self.assertEqual(resolve.bindings_for_lab(self.lab), [])
        self.assertIsNone(resolve.resolve_lab_for_guild("g-dept"))
        row = DiscordDepartmentActivationCode.objects.get(department=self.dept)
        self.assertEqual(row.consumed_guild_id, "g-dept")

    def test_department_and_lab_share_a_server_independently(self):
        lab_manager = User.objects.create_user("pi", password="x")
        LabMembership.objects.create(
            user=lab_manager, lab=self.lab, role=LabMembership.Role.OWNER
        )
        lab_activation.redeem_department(
            lab_activation.issue_department_code(self.head, self.dept), "d", "g-dept"
        )
        lab_activation.redeem(
            lab_activation.issue_code(lab_manager, self.lab), "d", "g-dept"
        )
        kinds = sorted(b.target_kind for b in resolve.bindings_for_guild("g-dept"))
        self.assertEqual(kinds, ["department", "lab"])
        # One server, one lab binding → server-scoped commands still find the lab.
        self.assertEqual(resolve.resolve_lab_for_guild("g-dept"), self.lab)

    def test_department_code_single_use_and_lockout_shared(self):
        code = lab_activation.issue_department_code(self.head, self.dept)
        lab_activation.redeem_department(code, "d-head", "g-dept")
        self.assertEqual(
            lab_activation.redeem_department(code, "d-head", "g-dept").outcome,
            lab_activation.RedeemOutcome.ALREADY_USED,
        )

    def test_department_code_endpoint_is_manager_gated(self):
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("discord-department-code")
        outsider = User.objects.create_user("outsider", password="x")
        client.force_authenticate(outsider)
        resp = client.post(f"{url}?department={self.dept.id}")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(client.post(f"{url}?department=not-a-uuid").status_code, 404)
        client.force_authenticate(self.head)
        resp = client.post(f"{url}?department={self.dept.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertRegex(resp.data["code"], r"^\d{5}-\d{5}$")

    def test_remove_endpoint_needs_the_bindings_own_manager(self):
        from rest_framework.test import APIClient

        lab_activation.redeem_department(
            lab_activation.issue_department_code(self.head, self.dept), "d", "g-dept"
        )
        binding = resolve.bindings_for_department(self.dept)[0]
        url = reverse("discord-binding-remove", args=[binding.id])
        client = APIClient()
        pi = User.objects.create_user("pi2", password="x")
        LabMembership.objects.create(
            user=pi, lab=self.lab, role=LabMembership.Role.OWNER
        )
        client.force_authenticate(pi)  # a lab manager cannot switch off the department
        self.assertEqual(client.post(url).status_code, 404)
        client.force_authenticate(self.head)
        self.assertEqual(client.post(url).status_code, 200)
        self.assertEqual(resolve.bindings_for_department(self.dept), [])


@discord_test_settings
class LabActivationCodeViewTests(TestCase):
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

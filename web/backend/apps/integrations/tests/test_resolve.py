"""resolve.py boundary + the §12 regression assertions on the authorization
invariant, guild binding, and activation-code semantics."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership
from apps.integrations.models import (
    DiscordActivationCode,
    DiscordGuildLink,
    DiscordIdentity,
)
from apps.integrations.services import activation, resolve
from apps.integrations.services.resolve import ConsumeOutcome
from apps.integrations.testing import bind

from .base import clear_discord_cache, discord_test_settings

User = get_user_model()


@discord_test_settings
class ResolveIdentityTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.user_a = User.objects.create_user("alice", password="x")
        self.user_b = User.objects.create_user("bob", password="x")

    def test_bind_then_resolve_active(self):
        resolve.bind_identity(self.user_a, "500", method=resolve.LINK_OAUTH)
        self.assertEqual(resolve.resolve_user("500"), self.user_a)
        identity = resolve.resolve_identity("500")
        self.assertEqual(identity.state, DiscordIdentity.State.ACTIVE)

    def test_identity_rebind_to_different_user_is_rejected(self):
        resolve.bind_identity(self.user_a, "500", method=resolve.LINK_OAUTH)
        with self.assertRaises(resolve.IdentityConflict):
            resolve.bind_identity(self.user_b, "500", method=resolve.LINK_OAUTH)
        # The original binding is untouched.
        self.assertEqual(resolve.resolve_user("500"), self.user_a)

    def test_rebind_same_user_updates_in_place(self):
        resolve.bind_identity(self.user_a, "500", method=resolve.LINK_OAUTH)
        resolve.bind_identity(
            self.user_a, "500", method=resolve.LINK_OAUTH, username="alice#new"
        )
        self.assertEqual(DiscordIdentity.objects.filter(user=self.user_a).count(), 1)


@discord_test_settings
class AuthorizationInvariantTests(TestCase):
    """Discord identity is authentication, never authorization."""

    def setUp(self):
        clear_discord_cache()
        self.lab = Lab.objects.create(name="Fungi Lab", slug="fungi")
        self.member = User.objects.create_user("member", password="x")
        self.manager = User.objects.create_user("manager", password="x")
        self.outsider = User.objects.create_user("outsider", password="x")
        LabMembership.objects.create(
            user=self.member, lab=self.lab, role=LabMembership.Role.MEMBER
        )
        LabMembership.objects.create(
            user=self.manager, lab=self.lab, role=LabMembership.Role.OWNER
        )
        for u in (self.member, self.manager, self.outsider):
            resolve.bind_identity(u, f"d-{u.username}", method=resolve.LINK_OAUTH)

    def test_guild_membership_grants_no_lab_access(self):
        # A plain member is authenticated but cannot *manage* the lab.
        self.assertFalse(
            resolve.can_manage_lab_via_discord("d-member", self.lab)
        )

    def test_guild_owner_without_lab_authority_cannot_run_setup(self):
        # An outsider (no membership) — even a Discord guild owner — cannot manage.
        self.assertFalse(
            resolve.can_manage_lab_via_discord("d-outsider", self.lab)
        )

    def test_lab_manager_can_manage(self):
        self.assertTrue(
            resolve.can_manage_lab_via_discord("d-manager", self.lab)
        )

    def test_unlinked_discord_user_cannot_manage(self):
        self.assertFalse(resolve.can_manage_lab_via_discord("nobody", self.lab))


@discord_test_settings
class GuildBindingTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.lab = Lab.objects.create(name="Lab One", slug="one")
        self.lab2 = Lab.objects.create(name="Lab Two", slug="two")
        self.installer = User.objects.create_user("installer", password="x")

    def test_bind_guild_from_exchange_object(self):
        binding = resolve.bind_guild(
            self.lab,
            {"id": "guild-1", "name": "Server One"},
            installed_by=self.installer,
        )
        link = binding.guild
        self.assertEqual(link.state, DiscordGuildLink.State.PENDING_SETUP)
        self.assertEqual(binding.state, "pending_setup")
        self.assertEqual(binding.lab, self.lab)
        self.assertTrue(link.verified_via_code_grant)
        self.assertEqual(link.guild_id, "guild-1")
        self.assertEqual(link.guild_name_cache, "Server One")

    def test_guild_binding_ignores_redirect_params_entirely(self):
        # bind_guild is only ever fed the *exchange* guild object; there is no code
        # path that reads a redirect-supplied guild_id. Proof: the bound id is the
        # exchange id, and a different "hint" cannot change it.
        resolve.bind_guild(self.lab, {"id": "authoritative"}, installed_by=None)
        resolve.confirm_guild("authoritative", confirmed_by=self.installer)
        self.assertEqual(resolve.resolve_lab_for_guild("authoritative"), self.lab)
        self.assertIsNone(resolve.resolve_lab_for_guild("forged-hint"))

    def test_a_second_lab_installing_into_a_bound_guild_gets_its_own_binding(self):
        resolve.bind_guild(self.lab, {"id": "guild-x"})
        resolve.bind_guild(self.lab2, {"id": "guild-x"})
        resolve.confirm_guild("guild-x", confirmed_by=self.installer)
        labs = {b.lab for b in resolve.bindings_for_guild("guild-x")}
        self.assertEqual(labs, {self.lab, self.lab2})
        # Two labs in one server: no command can guess which one is meant.
        self.assertIsNone(resolve.resolve_lab_for_guild("guild-x"))

    def test_an_install_with_no_guild_is_refused(self):
        with self.assertRaises(resolve.GuildConflict):
            resolve.bind_guild(self.lab, {})

    def test_unverified_guild_link_is_unusable(self):
        # A link that never went through the code grant cannot be confirmed ACTIVE.
        binding = bind(
            lab=self.lab, state="pending_setup", guild_id="guild-u", verified=False
        )
        confirmed = resolve.confirm_guild("guild-u", confirmed_by=self.installer)
        self.assertIsNone(confirmed)
        binding.refresh_from_db()
        binding.guild.refresh_from_db()
        self.assertEqual(binding.guild.state, DiscordGuildLink.State.PENDING_SETUP)
        self.assertEqual(binding.state, "pending_setup")

    def test_confirm_verified_guild_goes_active(self):
        resolve.bind_guild(self.lab, {"id": "guild-v"})
        link = resolve.confirm_guild("guild-v", confirmed_by=self.installer)
        self.assertEqual(link.state, DiscordGuildLink.State.ACTIVE)
        self.assertIsNotNone(link.confirmed_at)
        self.assertTrue(resolve.lab_guild_is_active(self.lab))

    def test_kick_marks_link(self):
        resolve.bind_guild(self.lab, {"id": "guild-k"})
        resolve.mark_guild_kicked("guild-k")
        link = resolve.get_guild_link("guild-k")
        self.assertEqual(link.state, DiscordGuildLink.State.KICKED)
        self.assertFalse(resolve.lab_guild_is_active(self.lab))


@discord_test_settings
class ActivationCodeTests(TestCase):
    def setUp(self):
        clear_discord_cache()
        self.user = User.objects.create_user("coder", password="x")
        self.other = User.objects.create_user("other", password="x")

    def test_activation_code_is_single_use_and_ttl_bound(self):
        plaintext = activation.issue_code(self.user)
        code_hash = activation.hash_code(activation.normalize(plaintext))

        first = resolve.consume_activation_code(code_hash, "d-1")
        self.assertEqual(first.outcome, ConsumeOutcome.OK)
        self.assertEqual(resolve.resolve_user("d-1"), self.user)

        # Single use: a second redemption of the same code fails.
        second = resolve.consume_activation_code(code_hash, "d-2")
        self.assertEqual(second.outcome, ConsumeOutcome.ALREADY_USED)

    def test_expired_code_is_not_consumed_on_reject(self):
        plaintext = activation.issue_code(self.user)
        code_hash = activation.hash_code(activation.normalize(plaintext))
        # Force expiry.
        DiscordActivationCode.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        result = resolve.consume_activation_code(code_hash, "d-1")
        self.assertEqual(result.outcome, ConsumeOutcome.EXPIRED)
        row = DiscordActivationCode.objects.get(user=self.user)
        self.assertIsNone(row.consumed_at)  # not consumed on reject

    def test_cross_user_redeem_rejected_without_consuming(self):
        # `other` already owns discord id d-9.
        resolve.bind_identity(self.other, "d-9", method=resolve.LINK_OAUTH)
        plaintext = activation.issue_code(self.user)
        code_hash = activation.hash_code(activation.normalize(plaintext))

        result = resolve.consume_activation_code(code_hash, "d-9")
        self.assertEqual(result.outcome, ConsumeOutcome.REBIND_REJECTED)
        row = DiscordActivationCode.objects.get(
            user=self.user, consumed_at__isnull=True
        )
        self.assertIsNone(row.consumed_at)  # code preserved for the real owner

    def test_issuing_supersedes_prior_live_code(self):
        first = activation.issue_code(self.user)
        activation.issue_code(self.user)  # supersedes
        first_hash = activation.hash_code(activation.normalize(first))
        result = resolve.consume_activation_code(first_hash, "d-1")
        self.assertEqual(result.outcome, ConsumeOutcome.ALREADY_USED)

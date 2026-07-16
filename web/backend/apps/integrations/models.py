"""Discord integration data model — all in Mycelium's Postgres.

Three tables, one per link concern:

* ``DiscordIdentity``   — a Mycelium user's Discord identity (Path A/B). An
  *authentication* artifact only; it confers no authorization (see the plan §7 and
  ``services.resolve``).
* ``DiscordActivationCode`` — the Path B fallback: a short-lived, single-use code a
  user redeems from Discord to bind their identity without OAuth.
* ``DiscordGuildLink``  — a Discord server bound to a Lab (Path C). One guild ↔ one
  lab, gated on real Mycelium lab authority.

Auditing reuses ``apps.accounts.services.record_audit_event`` — no table here.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .fields import EncryptedTextField


class DiscordIdentity(models.Model):
    """A Mycelium user's Discord identity. Authentication only — no authorization."""

    class State(models.TextChoices):
        PENDING = "pending", "Pending"  # flow started, not confirmed
        ACTIVE = "active", "Active"  # bound
        REVOKED = "revoked", "Revoked"  # unlinked / deauthorized

    class LinkMethod(models.TextChoices):
        OAUTH = "oauth", "OAuth"
        ACTIVATION_CODE = "activation_code", "Activation code"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discord",
    )
    # The snowflake — the ONLY identity key. Usernames change and are never a key.
    discord_user_id = models.CharField(max_length=32, unique=True, db_index=True)
    username_cache = models.CharField(max_length=64, blank=True)  # display only
    global_name_cache = models.CharField(max_length=64, blank=True)
    dm_channel_id = models.CharField(max_length=32, blank=True)  # cached; stable

    link_method = models.CharField(max_length=16, choices=LinkMethod.choices)
    # OAuth scopes granted. JSONField (not ArrayField) so the model works on both
    # SQLite (tests) and Postgres; we never query by scope.
    scopes = models.JSONField(default=list, blank=True)
    access_token = EncryptedTextField(blank=True, default="")  # empty on code path
    refresh_token = EncryptedTextField(blank=True, default="")
    token_expires_at = models.DateTimeField(null=True, blank=True)

    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING
    )
    # Reachability, orthogonal to `state`: a link can be ACTIVE with dm_ok=False.
    # null = unknown, True = a probe DM landed, False = blocked (50007).
    dm_ok = models.BooleanField(null=True, blank=True)
    dm_checked_at = models.DateTimeField(null=True, blank=True)

    linked_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Discord identity"
        verbose_name_plural = "Discord identities"

    def __str__(self) -> str:
        return f"DiscordIdentity(user={self.user_id}, state={self.state})"


class DiscordActivationCode(models.Model):
    """Path B: a short-lived, single-use code a user redeems from Discord.

    Only the sha256 of the plaintext is stored; the plaintext is shown once at
    issue and never persisted or logged.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discord_codes",
    )
    code_hash = models.CharField(max_length=64, db_index=True)  # sha256 hex
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # created_at + TTL
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_by_discord_id = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["code_hash", "expires_at"])]

    def __str__(self) -> str:
        state = "consumed" if self.consumed_at else "live"
        return f"DiscordActivationCode(user={self.user_id}, {state})"


class DiscordGuildLink(models.Model):
    """A Discord server bound to a Lab. One guild ↔ one lab."""

    class State(models.TextChoices):
        PENDING_SETUP = "pending_setup", "Pending setup"  # installed, unclaimed
        ACTIVE = "active", "Active"  # confirmed by a lab manager
        KICKED = "kicked", "Kicked"

    lab = models.OneToOneField(
        "accounts.Lab",
        on_delete=models.CASCADE,
        related_name="discord_link",
    )
    guild_id = models.CharField(max_length=32, unique=True, db_index=True)
    guild_name_cache = models.CharField(max_length=100, blank=True)
    installed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discord_guild_installs",
    )
    # Load-bearing: the binding is trusted only because it came from the OAuth
    # code-grant token exchange (an authoritative `guild` object), not from the
    # forgeable redirect params. Downstream use gates on this being True.
    verified_via_code_grant = models.BooleanField(default=False)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING_SETUP
    )
    installed_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"DiscordGuildLink(lab={self.lab_id}, state={self.state})"

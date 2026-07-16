"""THE ONLY place Discord code touches the ORM.

Every Discord-originated database read or write goes through this module. Handlers
(bot cogs), views, and tasks call these functions and import no model themselves —
asserted by ``test_discord_path_imports_no_models_outside_resolve_module``. This
keeps the "Mylo owns no data / access only when appropriate" boundary enforceable
and reviewable at the application layer, since there is no network boundary to
enforce it at.

The authorization invariant (plan §7) lives here too: a Discord identity is
*authentication only*. ``can_manage_lab_via_discord`` terminates in the existing
``apps.accounts.permissions`` checks — there is no parallel Discord-side permission
logic anywhere.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Lab
from apps.accounts.permissions import user_can_manage_lab

from ..models import DiscordActivationCode, DiscordGuildLink, DiscordIdentity
from . import audit

User = get_user_model()

# Re-exported so orchestration modules (which must not import models) can name a
# link method without reaching into ``..models``.
LINK_OAUTH = DiscordIdentity.LinkMethod.OAUTH
LINK_ACTIVATION_CODE = DiscordIdentity.LinkMethod.ACTIVATION_CODE


class IdentityConflict(Exception):
    """The snowflake is already bound to a different Mycelium user (→ 409)."""


class GuildConflict(Exception):
    """The guild (or lab) is already bound to a different lab (→ 409)."""


# --------------------------------------------------------------------------- #
# Identity — reads
# --------------------------------------------------------------------------- #
def get_identity_for_user(user) -> DiscordIdentity | None:
    return DiscordIdentity.objects.filter(user=user).first()


def get_identity(pk) -> DiscordIdentity | None:
    return DiscordIdentity.objects.filter(pk=pk).first()


def get_identity_by_discord_id(discord_user_id: str) -> DiscordIdentity | None:
    return DiscordIdentity.objects.filter(
        discord_user_id=str(discord_user_id)
    ).first()


def resolve_identity(discord_user_id: str) -> DiscordIdentity | None:
    """The ACTIVE identity for a snowflake, or None. Authentication lookup."""
    return DiscordIdentity.objects.filter(
        discord_user_id=str(discord_user_id),
        state=DiscordIdentity.State.ACTIVE,
    ).first()


def resolve_user(discord_user_id: str):
    identity = resolve_identity(discord_user_id)
    return identity.user if identity else None


def active_identity_for_user(user) -> DiscordIdentity | None:
    """The user's ACTIVE Discord identity, or None — the outbound-DM lookup.

    Only ACTIVE identities are reachable; PENDING/REVOKED users are never messaged.
    Callers read ``discord_user_id`` / ``dm_ok`` / ``dm_channel_id`` off the result.
    """
    return DiscordIdentity.objects.filter(
        user=user, state=DiscordIdentity.State.ACTIVE
    ).first()


# --------------------------------------------------------------------------- #
# Identity — writes
# --------------------------------------------------------------------------- #
def bind_identity(
    user,
    discord_user_id: str,
    *,
    method: str,
    scopes: list[str] | None = None,
    tokens: dict | None = None,
    username: str = "",
    global_name: str = "",
    actor=None,
) -> DiscordIdentity:
    """Bind (or re-bind) a user's Discord identity to ACTIVE.

    Rejects binding a snowflake already held by a *different* user
    (``IdentityConflict`` → 409, never a silent rebind).
    """
    discord_user_id = str(discord_user_id)
    existing = get_identity_by_discord_id(discord_user_id)
    if existing and existing.user_id != user.id:
        audit.discord_audit(
            action="discord.link.rejected",
            actor=actor,
            discord_user_id=discord_user_id,
            metadata={"reason": "snowflake_bound_to_other_user"},
        )
        raise IdentityConflict(discord_user_id)

    identity, _ = DiscordIdentity.objects.get_or_create(user=user)
    identity.discord_user_id = discord_user_id
    identity.link_method = method
    identity.scopes = list(scopes or [])
    identity.username_cache = (username or "")[:64]
    identity.global_name_cache = (global_name or "")[:64]
    if tokens is not None:
        identity.access_token = tokens.get("access_token", "") or ""
        identity.refresh_token = tokens.get("refresh_token", "") or ""
        identity.token_expires_at = tokens.get("expires_at")
    identity.state = DiscordIdentity.State.ACTIVE
    identity.linked_at = timezone.now()
    identity.save()

    audit.discord_audit(
        action="discord.link.completed",
        actor=actor or user,
        discord_user_id=discord_user_id,
        metadata={"method": method},
    )
    return identity


def set_identity_dm(
    identity: DiscordIdentity,
    *,
    dm_ok: bool | None,
    dm_channel_id: str = "",
    error_code: int | None = None,
) -> None:
    identity.dm_ok = dm_ok
    identity.dm_checked_at = timezone.now()
    if dm_channel_id:
        identity.dm_channel_id = str(dm_channel_id)
    if error_code is not None:
        identity.last_error_code = error_code
        identity.last_error_at = timezone.now()
    identity.save(
        update_fields=[
            "dm_ok",
            "dm_checked_at",
            "dm_channel_id",
            "last_error_code",
            "last_error_at",
            "updated_at",
        ]
    )
    if dm_ok is False:
        audit.discord_audit(
            action="discord.link.dm_blocked",
            actor=identity.user,
            discord_user_id=identity.discord_user_id,
            metadata={"error_code": error_code},
        )


def pop_identity_tokens_and_delete(user) -> dict:
    """Delete a user's identity, returning its (decrypted) tokens to revoke.

    Unlink deletes the row (a clean re-link afterwards is the smoke test); the
    caller revokes the returned tokens against Discord out of band.
    """
    identity = get_identity_for_user(user)
    if not identity:
        return {}
    tokens = {
        "access_token": identity.access_token or "",
        "refresh_token": identity.refresh_token or "",
        "discord_user_id": identity.discord_user_id,
    }
    identity.delete()
    audit.discord_audit(
        action="discord.link.revoked",
        actor=user,
        discord_user_id=tokens["discord_user_id"],
    )
    return tokens


def mark_identity_revoked(discord_user_id: str) -> None:
    """Mark an identity REVOKED (e.g. reconciliation saw invalid_grant)."""
    identity = get_identity_by_discord_id(discord_user_id)
    if not identity:
        return
    identity.state = DiscordIdentity.State.REVOKED
    identity.save(update_fields=["state", "updated_at"])
    audit.discord_audit(
        action="discord.link.revoked",
        actor=identity.user,
        discord_user_id=discord_user_id,
        metadata={"reason": "reconcile"},
    )


def identities_with_tokens_expiring_before(when: datetime):
    """ACTIVE OAuth identities whose access token expires before ``when``."""
    return list(
        DiscordIdentity.objects.filter(
            state=DiscordIdentity.State.ACTIVE,
            link_method=DiscordIdentity.LinkMethod.OAUTH,
            token_expires_at__isnull=False,
            token_expires_at__lt=when,
        )
    )


def update_identity_tokens(
    identity: DiscordIdentity,
    *,
    access_token: str,
    refresh_token: str,
    expires_at: datetime | None,
) -> None:
    identity.access_token = access_token or ""
    identity.refresh_token = refresh_token or ""
    identity.token_expires_at = expires_at
    identity.save(
        update_fields=[
            "access_token",
            "refresh_token",
            "token_expires_at",
            "updated_at",
        ]
    )


# --------------------------------------------------------------------------- #
# Guild ↔ Lab
# --------------------------------------------------------------------------- #
def get_lab_by_id(lab_id) -> Lab | None:
    return Lab.objects.filter(id=lab_id).first()


def get_lab_by_slug(slug: str) -> Lab | None:
    return Lab.objects.filter(slug=slug).first()


def get_user_by_id(user_id):
    return User.objects.filter(id=user_id).first()


def web_user_can_manage_lab(user, lab) -> bool:
    """Manager check for a logged-in web user (Path C install initiation)."""
    return user_can_manage_lab(user, lab)


def get_guild_link(guild_id: str) -> DiscordGuildLink | None:
    return DiscordGuildLink.objects.filter(guild_id=str(guild_id)).first()


def get_guild_link_for_lab(lab) -> DiscordGuildLink | None:
    return DiscordGuildLink.objects.filter(lab=lab).first()


def resolve_lab_for_guild(guild_id: str) -> Lab | None:
    link = get_guild_link(guild_id)
    return link.lab if link else None


def set_announcement_channel(
    guild_id: str, channel_id: str, *, verified_at
) -> DiscordGuildLink | None:
    """Bind (channel-verified) the default announcement channel for a guild's lab."""
    link = get_guild_link(guild_id)
    if link is None:
        return None
    link.announcement_channel_id = str(channel_id)
    link.channel_verified_at = verified_at
    link.save(
        update_fields=[
            "announcement_channel_id",
            "channel_verified_at",
            "updated_at",
        ]
    )
    audit.discord_audit(
        action="discord.guild.channel_bound",
        guild_id=guild_id,
        metadata={"channel_id": str(channel_id)},
    )
    return link


def get_announcement_channel_for_lab(lab) -> str:
    """The lab's verified default announcement channel id, or '' if none bound."""
    link = get_guild_link_for_lab(lab)
    return link.announcement_channel_id if link else ""


def bind_guild(lab, guild: dict, *, installed_by=None) -> DiscordGuildLink:
    """Create/refresh a PENDING_SETUP guild link from the authoritative exchange.

    ``guild`` is the object from the OAuth code-grant token response — never the
    forgeable redirect params. Enforces one-guild-one-lab (``GuildConflict`` → 409).
    """
    guild_id = str(guild.get("id") or "")
    if not guild_id:
        raise GuildConflict("token exchange returned no guild")

    existing_for_guild = get_guild_link(guild_id)
    if existing_for_guild and existing_for_guild.lab_id != lab.id:
        audit.discord_audit(
            action="discord.guild.rejected",
            actor=installed_by,
            guild_id=guild_id,
            metadata={"reason": "guild_bound_to_other_lab"},
        )
        raise GuildConflict(guild_id)

    existing_for_lab = get_guild_link_for_lab(lab)
    if existing_for_lab and existing_for_lab.guild_id != guild_id:
        audit.discord_audit(
            action="discord.guild.rejected",
            actor=installed_by,
            guild_id=guild_id,
            metadata={"reason": "lab_bound_to_other_guild"},
        )
        raise GuildConflict(f"lab already bound to guild {existing_for_lab.guild_id}")

    link, _ = DiscordGuildLink.objects.get_or_create(
        lab=lab, defaults={"guild_id": guild_id}
    )
    link.guild_id = guild_id
    link.guild_name_cache = (guild.get("name") or "")[:100]
    link.verified_via_code_grant = True
    if installed_by is not None:
        link.installed_by = installed_by
    # A fresh (re)install returns to PENDING_SETUP unless already ACTIVE.
    if link.state == DiscordGuildLink.State.KICKED:
        link.state = DiscordGuildLink.State.PENDING_SETUP
    link.save()

    audit.discord_audit(
        action="discord.guild.installed",
        actor=installed_by,
        guild_id=guild_id,
        metadata={"lab_id": str(lab.id), "verified_via_code_grant": True},
    )
    audit.discord_audit(
        action="discord.guild.verified",
        actor=installed_by,
        guild_id=guild_id,
        metadata={"lab_id": str(lab.id)},
    )
    return link


def confirm_guild(guild_id: str, *, confirmed_by) -> DiscordGuildLink | None:
    link = get_guild_link(guild_id)
    if not link:
        return None
    if not link.verified_via_code_grant:
        # Never usable: an unverified link cannot be confirmed.
        return None
    link.state = DiscordGuildLink.State.ACTIVE
    link.confirmed_at = timezone.now()
    link.save(update_fields=["state", "confirmed_at", "updated_at"])
    audit.discord_audit(
        action="discord.guild.confirmed",
        actor=confirmed_by,
        guild_id=guild_id,
        metadata={"lab_id": str(link.lab_id)},
    )
    return link


def mark_guild_kicked(guild_id: str) -> None:
    link = get_guild_link(guild_id)
    if not link or link.state == DiscordGuildLink.State.KICKED:
        return
    link.state = DiscordGuildLink.State.KICKED
    link.save(update_fields=["state", "updated_at"])
    audit.discord_audit(
        action="discord.guild.kicked",
        guild_id=guild_id,
        metadata={"lab_id": str(link.lab_id)},
    )


def active_guild_ids() -> list[str]:
    """guild_ids of every link the reconcile sweep should still expect to see."""
    return list(
        DiscordGuildLink.objects.exclude(
            state=DiscordGuildLink.State.KICKED
        ).values_list("guild_id", flat=True)
    )


# --------------------------------------------------------------------------- #
# Authorization — always terminates in apps.accounts.permissions
# --------------------------------------------------------------------------- #
def can_manage_lab_via_discord(discord_user_id: str, lab) -> bool:
    """Auth (Discord identity) → user → the EXISTING lab-manager permission."""
    user = resolve_user(discord_user_id)
    if user is None:
        return False
    return user_can_manage_lab(user, lab)


# --------------------------------------------------------------------------- #
# Activation codes (Path B) — ORM side
# --------------------------------------------------------------------------- #
class ConsumeOutcome(enum.StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    ALREADY_USED = "already_used"
    REBIND_REJECTED = "rebind_rejected"


@dataclass
class ConsumeResult:
    outcome: ConsumeOutcome
    identity: DiscordIdentity | None = None


def store_activation_code(user, code_hash: str, expires_at: datetime) -> None:
    """Persist a new code hash, invalidating any prior live code for the user."""
    now = timezone.now()
    DiscordActivationCode.objects.filter(
        user=user, consumed_at__isnull=True, expires_at__gt=now
    ).update(consumed_at=now)  # supersede prior live codes
    DiscordActivationCode.objects.create(
        user=user, code_hash=code_hash, expires_at=expires_at
    )
    audit.discord_audit(action="discord.activate.issued", actor=user)


def consume_activation_code(code_hash: str, discord_user_id: str) -> ConsumeResult:
    """Atomically redeem a code and bind the redeemer's identity.

    * Expired or already-used or unknown → not consumed, classified for messaging.
    * Snowflake already bound to a *different* user → REBIND_REJECTED, and the code
      is **not** consumed (so the real owner can still use it).
    """
    discord_user_id = str(discord_user_id)
    now = timezone.now()
    with transaction.atomic():
        row = (
            DiscordActivationCode.objects.select_for_update()
            .filter(code_hash=code_hash, consumed_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at")
            .first()
        )
        if row is None:
            # Classify why for a helpful (still ephemeral) message.
            any_row = (
                DiscordActivationCode.objects.filter(code_hash=code_hash)
                .order_by("-created_at")
                .first()
            )
            if any_row is None:
                return ConsumeResult(ConsumeOutcome.NOT_FOUND)
            if any_row.consumed_at is not None:
                return ConsumeResult(ConsumeOutcome.ALREADY_USED)
            return ConsumeResult(ConsumeOutcome.EXPIRED)

        conflict = get_identity_by_discord_id(discord_user_id)
        if conflict and conflict.user_id != row.user_id:
            audit.discord_audit(
                action="discord.activate.failed",
                actor=row.user,
                discord_user_id=discord_user_id,
                metadata={"reason": "snowflake_bound_to_other_user"},
            )
            return ConsumeResult(ConsumeOutcome.REBIND_REJECTED)

        identity = bind_identity(
            row.user,
            discord_user_id,
            method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
            actor=row.user,
        )
        row.consumed_at = now
        row.consumed_by_discord_id = discord_user_id
        row.save(update_fields=["consumed_at", "consumed_by_discord_id"])
        audit.discord_audit(
            action="discord.activate.consumed",
            actor=row.user,
            discord_user_id=discord_user_id,
        )
        return ConsumeResult(ConsumeOutcome.OK, identity=identity)

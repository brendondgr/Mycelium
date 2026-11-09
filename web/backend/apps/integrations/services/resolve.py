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

from apps.accounts.models import Department, Lab, LabMembership
from apps.accounts.permissions import user_can_manage_department, user_can_manage_lab

from ..models import (
    DiscordActivationCode,
    DiscordChannelRoute,
    DiscordDepartmentActivationCode,
    DiscordGuildLink,
    DiscordIdentity,
    DiscordLabActivationCode,
    DiscordOutboxMessage,
    DiscordTargetBinding,
)
from . import audit

User = get_user_model()

# Re-exported so orchestration modules (which must not import models) can name a
# link method without reaching into ``..models``.
LINK_OAUTH = DiscordIdentity.LinkMethod.OAUTH
LINK_ACTIVATION_CODE = DiscordIdentity.LinkMethod.ACTIVATION_CODE

# Guild-link states, re-exported so orchestration (mylo.linking) can branch on
# them without importing the model.
GUILD_ACTIVE = DiscordGuildLink.State.ACTIVE
GUILD_PENDING = DiscordGuildLink.State.PENDING_SETUP
GUILD_KICKED = DiscordGuildLink.State.KICKED
BINDING_ACTIVE = DiscordTargetBinding.State.ACTIVE
ROUTE_PURPOSES = tuple(DiscordChannelRoute.Purpose.values)


class IdentityConflict(Exception):
    """The snowflake is already bound to a different Mycelium user (→ 409)."""


class GuildConflict(Exception):
    """The OAuth install returned no usable guild (→ 409)."""


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


def active_discord_ids_for_users(users) -> dict:
    """Map ``{user_id: discord_user_id}`` for the ACTIVE identities among ``users``.

    Batch lookup for lab mention resolution — a user absent from the result has no
    active identity and must be rendered as plain text (no ping), never dropped.
    """
    ids = [u.id for u in users]
    if not ids:
        return {}
    rows = DiscordIdentity.objects.filter(
        user_id__in=ids, state=DiscordIdentity.State.ACTIVE
    ).values_list("user_id", "discord_user_id")
    return {user_id: discord_user_id for user_id, discord_user_id in rows}


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


def set_daily_report_opt_out(identity: DiscordIdentity, *, opt_out: bool) -> None:
    """Set whether this identity is excluded from the daily "Mylo Report" DM."""
    identity.daily_report_opt_out = bool(opt_out)
    identity.save(update_fields=["daily_report_opt_out", "updated_at"])
    audit.discord_audit(
        action="discord.daily_report.opt_out"
        if opt_out
        else "discord.daily_report.opt_in",
        actor=identity.user,
        discord_user_id=identity.discord_user_id,
    )


def report_recipient_user_ids(user_ids) -> set:
    """User ids among ``user_ids`` reachable for the daily report DM.

    A recipient must have an ACTIVE identity, not have opted out, and not be a known
    DM-blocked address (``dm_ok is False``). ``dm_ok is None`` (never probed) is kept
    — the send path opens the DM and finds out. Bulk query so the daily command never
    resolves identities one user at a time.
    """
    ids = [u.id if hasattr(u, "id") else u for u in user_ids]
    if not ids:
        return set()
    rows = DiscordIdentity.objects.filter(
        user_id__in=ids,
        state=DiscordIdentity.State.ACTIVE,
        daily_report_opt_out=False,
    ).exclude(dm_ok=False).values_list("user_id", flat=True)
    return set(rows)


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
# Servers, labs, departments
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


def web_user_can_manage_department(user, department) -> bool:
    return user_can_manage_department(user, department)


def web_user_can_manage_binding(user, binding) -> bool:
    """A binding is managed by its own target's managers — never the other kind."""
    if binding.lab_id:
        return user_can_manage_lab(user, binding.lab)
    return user_can_manage_department(user, binding.department)


def get_guild_link(guild_id: str) -> DiscordGuildLink | None:
    return DiscordGuildLink.objects.filter(guild_id=str(guild_id)).first()


def get_department_by_id(department_id) -> Department | None:
    return Department.objects.filter(id=department_id).first()


# --------------------------------------------------------------------------- #
# Bindings: one lab or department in one server
# --------------------------------------------------------------------------- #
def _live_bindings():
    """Bindings Mylo may post for: the binding is ACTIVE and Mylo is still in the
    server. ``PENDING_SETUP`` is not live (nobody claimed it yet), and a ``KICKED``
    guild silences every binding in it without deleting their configuration, so a
    re-install picks up where it left off."""
    return DiscordTargetBinding.objects.filter(
        state=DiscordTargetBinding.State.ACTIVE,
        guild__state=DiscordGuildLink.State.ACTIVE,
    ).select_related("guild", "lab", "department")


def get_binding(binding_id) -> DiscordTargetBinding | None:
    return (
        DiscordTargetBinding.objects.filter(id=binding_id)
        .select_related("guild", "lab", "department")
        .first()
    )


def bindings_for_lab(lab) -> list[DiscordTargetBinding]:
    """Every live binding of ``lab``, oldest activation first."""
    return list(_live_bindings().filter(lab=lab))


def bindings_for_department(department) -> list[DiscordTargetBinding]:
    return list(_live_bindings().filter(department=department))


def bindings_for_guild(guild_id: str, *, include_pending: bool = False):
    """The bindings in one server — labs first, then the department — by activation."""
    qs = DiscordTargetBinding.objects.filter(guild__guild_id=str(guild_id)).exclude(
        state=DiscordTargetBinding.State.REMOVED
    )
    if not include_pending:
        qs = qs.filter(state=DiscordTargetBinding.State.ACTIVE)
    return list(qs.select_related("guild", "lab", "department"))


def all_bindings_for_lab(lab) -> list[DiscordTargetBinding]:
    """Every non-removed binding of ``lab`` (live or not), for the portal's list."""
    return list(
        DiscordTargetBinding.objects.filter(lab=lab)
        .exclude(state=DiscordTargetBinding.State.REMOVED)
        .select_related("guild")
    )


def binding_is_live(binding) -> bool:
    return bool(
        binding
        and binding.state == DiscordTargetBinding.State.ACTIVE
        and binding.guild.state == DiscordGuildLink.State.ACTIVE
    )


def binding_name(binding) -> str:
    return binding.target.name if binding.target is not None else ""


def routes_for_binding(binding) -> dict[str, DiscordChannelRoute]:
    return {r.purpose: r for r in binding.routes.all()}


def route_channel(binding, purpose: str) -> str:
    row = binding.routes.filter(purpose=purpose).first()
    return row.channel_id if row else ""


def get_route(binding, purpose: str) -> DiscordChannelRoute | None:
    return binding.routes.filter(purpose=purpose).first()


def set_route(
    binding,
    purpose: str,
    channel_id: str,
    *,
    verified_at,
    channel_type: int | None = None,
    forum_tag_ids: dict | None = None,
    created_by_mylo: bool | None = None,
    channel_name: str | None = None,
    actor=None,
) -> DiscordChannelRoute:
    """Bind (channel-verified) ``purpose`` for one binding to ``channel_id``."""
    route, _ = DiscordChannelRoute.objects.update_or_create(
        binding=binding,
        purpose=purpose,
        defaults={
            "channel_id": str(channel_id),
            "verified_at": verified_at,
            "ok": True,
        },
    )
    fields = []
    if channel_type is not None:
        route.channel_type = channel_type
        fields.append("channel_type")
    if forum_tag_ids is not None:
        route.forum_tag_ids = forum_tag_ids
        fields.append("forum_tag_ids")
    if created_by_mylo is not None:
        route.created_by_mylo = created_by_mylo
        fields.append("created_by_mylo")
    if channel_name is not None:
        route.channel_name = channel_name[:100]
        fields.append("channel_name")
    if fields:
        route.save(update_fields=[*fields, "updated_at"])
    audit.discord_audit(
        action=(
            "discord.guild.channel_bound"
            if purpose == "deadlines"
            else f"discord.guild.{purpose}_channel_bound"
        ),
        actor=actor,
        guild_id=binding.guild.guild_id,
        metadata={"channel_id": str(channel_id), "binding_id": binding.id},
    )
    return route


def set_route_poster_policy(binding, purpose: str, *, policy: str, role_ids=()) -> bool:
    rows = DiscordChannelRoute.objects.filter(binding=binding, purpose=purpose)
    updated = rows.update(
        poster_policy=policy,
        poster_role_ids=[str(r) for r in role_ids],
        updated_at=timezone.now(),
    )
    return bool(updated)


def clear_route(binding, purpose: str, *, actor=None) -> bool:
    """Opt one binding out of ``purpose`` — delete its route."""
    deleted, _ = DiscordChannelRoute.objects.filter(
        binding=binding, purpose=purpose
    ).delete()
    if deleted:
        audit.discord_audit(
            action="discord.guild.channel_cleared",
            actor=actor,
            guild_id=binding.guild.guild_id,
            metadata={"kind": purpose, "binding_id": binding.id},
        )
    return bool(deleted)


# --------------------------------------------------------------------------- #
# The lab's primary server — what the pre-binding features still read
# --------------------------------------------------------------------------- #
@dataclass
class LabServer:
    """A lab's primary binding flattened to what the older lab features read.

    Lab deadline reminders, the lab digest, the weekly and report re-sends were all
    built for one server per lab, and keep exactly that behaviour: they use the
    lab's *primary* binding — its oldest live binding that has the route in question,
    else its oldest binding at all. New features (opportunity announcements) post to
    every binding instead.
    """

    binding: DiscordTargetBinding
    state: str
    guild_id: str
    guild_name_cache: str
    verified_via_code_grant: bool
    confirmed_at: datetime | None
    announcement_channel_id: str
    updates_channel_id: str


def _binding_state(binding) -> str:
    if binding.guild.state == DiscordGuildLink.State.KICKED:
        return DiscordGuildLink.State.KICKED
    if binding.state == DiscordTargetBinding.State.ACTIVE:
        return DiscordGuildLink.State.ACTIVE
    return DiscordGuildLink.State.PENDING_SETUP


def _primary_binding(lab, purpose: str | None = None):
    rows = all_bindings_for_lab(lab)
    if not rows:
        return None
    live = [b for b in rows if binding_is_live(b)]
    pool = live or rows
    if purpose:
        with_route = [b for b in pool if route_channel(b, purpose)]
        if with_route:
            return with_route[0]
    return pool[0]


def primary_server_for_lab(lab, purpose: str | None = None) -> LabServer | None:
    binding = _primary_binding(lab, purpose)
    if binding is None:
        return None
    return LabServer(
        binding=binding,
        state=_binding_state(binding),
        guild_id=binding.guild.guild_id,
        guild_name_cache=binding.guild.guild_name_cache,
        verified_via_code_grant=binding.guild.verified_via_code_grant,
        confirmed_at=binding.activated_at,
        announcement_channel_id=route_channel(binding, "deadlines"),
        updates_channel_id=route_channel(binding, "updates"),
    )


# --------------------------------------------------------------------------- #
# Places: whose room a message is in (Mylo chat, plan D)
# --------------------------------------------------------------------------- #
PLACE_DM = "dm"
PLACE_ANNOUNCEMENT = "announcement"
PLACE_CLOSING_SOON = "closing_soon"
PLACE_THREAD = "thread"
PLACE_CHANNEL = "channel"
PLACE_AMBIGUOUS = "ambiguous"
PLACE_UNBOUND = "unbound"


@dataclass(frozen=True)
class Place:
    """Whose room a Discord message is in, decided from the gateway's ids alone.

    ``binding`` is the owning live binding (``None`` in a DM, an unbound server,
    or a server with several bindings none of which owns the channel). ``shared``
    places hold one conversation for everyone (a thread); elsewhere each person
    has their own. ``anchor`` is what the place is about (``{kind, key}``)."""

    kind: str
    binding: DiscordTargetBinding | None = None
    shared: bool = False
    anchor: dict | None = None
    title: str = ""
    closed: bool = False
    #: Any live binding of the server, for the server's own entitlement check
    #: where no binding owns the channel.
    any_binding: DiscordTargetBinding | None = None

    @property
    def lab(self):
        return self.binding.lab if self.binding is not None else None

    @property
    def department(self):
        return self.binding.department if self.binding is not None else None

    @property
    def server_name(self) -> str:
        b = self.binding or self.any_binding
        return b.guild.guild_name_cache if b is not None else ""


def _delivery_read():
    from tools._framework import services

    return services.get("delivery", "read")


def place_for(
    guild_id: str, channel_id: str, thread_id: str = "", parent_id: str = ""
) -> Place:
    """The one function that decides whose room a message is in.

    A DM is the person's own. In a server: a thread with a live announcement
    post belongs to that post's binding and is about the announcement; a
    closing-soon thread to its binding; any other thread or channel to the
    binding whose route names it (or its parent forum), else to the server's
    only live binding. Several bindings and no owner: ``ambiguous`` (public
    material only). No live binding: ``unbound``."""
    if not guild_id:
        return Place(kind=PLACE_DM)
    live = list(_live_bindings().filter(guild__guild_id=str(guild_id)))
    if not live:
        return Place(kind=PLACE_UNBOUND)
    by_id = {b.pk: b for b in live}
    read = _delivery_read()
    if thread_id and read is not None:
        post = read.announcement_post_for_thread(str(thread_id))
        if post and post["binding_id"] in by_id:
            return Place(
                kind=PLACE_ANNOUNCEMENT,
                binding=by_id[post["binding_id"]],
                shared=True,
                anchor={"kind": "announcement", "key": post["announcement_id"]},
                title=post["title"],
                closed=post["closed"],
                any_binding=live[0],
            )
        soon = read.closing_soon_for_thread(str(thread_id))
        if soon and soon["binding_id"] in by_id:
            return Place(
                kind=PLACE_CLOSING_SOON,
                binding=by_id[soon["binding_id"]],
                shared=True,
                title=f"Closing soon: {soon['category']}s, {soon['on_date']}",
                any_binding=live[0],
            )
    kind = PLACE_THREAD if thread_id else PLACE_CHANNEL
    rooms = {str(channel_id), str(parent_id or "")} - {""}
    owners = list(
        {
            r.binding_id
            for r in DiscordChannelRoute.objects.filter(
                binding__in=live, channel_id__in=rooms
            )
        }
    )
    if len(owners) == 1:
        binding = by_id[owners[0]]
    elif len(live) == 1:
        binding = live[0]
    else:
        return Place(kind=PLACE_AMBIGUOUS, shared=bool(thread_id), any_binding=live[0])
    return Place(
        kind=kind, binding=binding, shared=bool(thread_id), any_binding=live[0]
    )


def lab_guild_is_active(lab) -> bool:
    """Whether the lab has at least one live, claimed Discord binding.

    ``PENDING_SETUP`` is not live — the bot sits in the guild but no manager has
    claimed it, so nothing may be posted on the lab's behalf yet; ``KICKED`` is
    plainly dead. Callers outside this boundary ask through here rather than
    comparing states themselves, so the meaning of "synced" is defined once.
    """
    return _live_bindings().filter(lab=lab).exists()


def resolve_lab_for_guild(guild_id: str) -> Lab | None:
    """The lab a server-scoped command means when none is named: the server's only
    live lab binding. ``None`` when it has none or several (a department server with
    several labs) — the caller then has to name the lab."""
    labs = [b.lab for b in bindings_for_guild(guild_id) if b.lab_id]
    return labs[0] if len(labs) == 1 else None


def get_announcement_channel_for_lab(lab) -> str:
    """The lab's verified deadline-announcement channel id, or '' if none bound."""
    binding = _primary_binding(lab, "deadlines")
    return route_channel(binding, "deadlines") if binding else ""


def get_updates_channel_for_lab(lab) -> str:
    """The lab's verified daily/weekly-updates channel id, or '' if none bound."""
    binding = _primary_binding(lab, "updates")
    return route_channel(binding, "updates") if binding else ""


# --------------------------------------------------------------------------- #
# Install, activation, removal
# --------------------------------------------------------------------------- #
def _ensure_guild(guild_id: str, guild_name: str = "") -> DiscordGuildLink:
    guild, _ = DiscordGuildLink.objects.get_or_create(guild_id=str(guild_id))
    if guild_name:
        guild.guild_name_cache = guild_name[:100]
    return guild


def bind_guild(lab, guild: dict, *, installed_by=None) -> DiscordTargetBinding:
    """Record an OAuth install for ``lab``: the server plus a PENDING_SETUP binding.

    ``guild`` is the object from the OAuth code-grant token response — never the
    forgeable redirect params. A server can hold several bindings, so an install
    into a server that already serves another lab or a department is not a conflict.
    """
    guild_id = str(guild.get("id") or "")
    if not guild_id:
        raise GuildConflict("token exchange returned no guild")

    link = _ensure_guild(guild_id, guild.get("name") or "")
    link.verified_via_code_grant = True
    if installed_by is not None:
        link.installed_by = installed_by
    if link.state == DiscordGuildLink.State.KICKED:
        link.state = DiscordGuildLink.State.PENDING_SETUP
    link.save()

    binding, _ = DiscordTargetBinding.objects.get_or_create(guild=link, lab=lab)
    if binding.state == DiscordTargetBinding.State.REMOVED:
        binding.state = DiscordTargetBinding.State.PENDING_SETUP
        binding.save(update_fields=["state", "updated_at"])

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
    return binding


def confirm_guild(guild_id: str, *, confirmed_by) -> DiscordGuildLink | None:
    """Claim every pending binding in an OAuth-installed server."""
    link = get_guild_link(guild_id)
    if not link:
        return None
    if not link.verified_via_code_grant:
        # Never usable: an unverified link cannot be confirmed.
        return None
    now = timezone.now()
    link.state = DiscordGuildLink.State.ACTIVE
    link.confirmed_at = now
    link.save(update_fields=["state", "confirmed_at", "updated_at"])
    link.bindings.filter(state=DiscordTargetBinding.State.PENDING_SETUP).update(
        state=DiscordTargetBinding.State.ACTIVE,
        activated_at=now,
        activated_by=confirmed_by,
        updated_at=now,
    )
    audit.discord_audit(
        action="discord.guild.confirmed",
        actor=confirmed_by,
        guild_id=guild_id,
        metadata={},
    )
    return link


def _activate_binding(
    guild_id: str, guild_name: str, *, lab=None, department=None, confirmer=None
) -> DiscordTargetBinding:
    now = timezone.now()
    link = _ensure_guild(guild_id, guild_name)
    if link.installed_by_id is None and confirmer is not None:
        link.installed_by = confirmer
    link.state = DiscordGuildLink.State.ACTIVE
    link.confirmed_at = link.confirmed_at or now
    link.save()
    binding, _ = DiscordTargetBinding.objects.get_or_create(
        guild=link, lab=lab, department=department
    )
    binding.state = DiscordTargetBinding.State.ACTIVE
    binding.activated_at = now
    if confirmer is not None:
        binding.activated_by = confirmer
    binding.save()
    return binding


def remove_binding(binding, *, actor=None) -> None:
    """Switch one binding off. Its routes are kept, so re-activating restores them;
    every other binding in the server, and the target's other servers, carry on."""
    binding.state = DiscordTargetBinding.State.REMOVED
    binding.save(update_fields=["state", "updated_at"])
    audit.discord_audit(
        action="discord.binding.removed",
        actor=actor,
        guild_id=binding.guild.guild_id,
        metadata={"binding_id": binding.id, "target": binding.target_kind},
    )


def mark_guild_kicked(guild_id: str) -> None:
    link = get_guild_link(guild_id)
    if not link or link.state == DiscordGuildLink.State.KICKED:
        return
    link.state = DiscordGuildLink.State.KICKED
    link.save(update_fields=["state", "updated_at"])
    audit.discord_audit(
        action="discord.guild.kicked",
        guild_id=guild_id,
        metadata={},
    )


def active_guild_ids() -> list[str]:
    """guild_ids of every server the reconcile sweep should still expect to see."""
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


# --------------------------------------------------------------------------- #
# Lab activation codes (Path C) — ORM side
# --------------------------------------------------------------------------- #
class LabConsumeOutcome(enum.StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    ALREADY_USED = "already_used"
    CONFLICT = "conflict"  # code valid, but there is no server to bind it to


@dataclass
class LabCodeResult:
    outcome: LabConsumeOutcome
    lab: Lab | None = None
    binding: DiscordTargetBinding | None = None
    department: Department | None = None


def store_lab_activation_code(lab, user, code_hash: str, expires_at: datetime) -> None:
    """Persist a new lab code hash, superseding any prior live code for the lab."""
    now = timezone.now()
    DiscordLabActivationCode.objects.filter(
        lab=lab, consumed_at__isnull=True, expires_at__gt=now
    ).update(consumed_at=now)  # supersede prior live codes
    DiscordLabActivationCode.objects.create(
        lab=lab, issued_by=user, code_hash=code_hash, expires_at=expires_at
    )
    audit.discord_audit(
        action="discord.lab_activate.issued",
        actor=user,
        metadata={"lab_id": str(lab.id)},
    )


def store_department_activation_code(
    department, user, code_hash: str, expires_at: datetime
) -> None:
    """The department twin of :func:`store_lab_activation_code`."""
    now = timezone.now()
    DiscordDepartmentActivationCode.objects.filter(
        department=department, consumed_at__isnull=True, expires_at__gt=now
    ).update(consumed_at=now)
    DiscordDepartmentActivationCode.objects.create(
        department=department,
        issued_by=user,
        code_hash=code_hash,
        expires_at=expires_at,
    )
    audit.discord_audit(
        action="discord.department_activate.issued",
        actor=user,
        metadata={"department_id": str(department.id)},
    )


def _consume_code(model, target_field: str, code_hash: str, now):
    """Lock and return the live code row for ``code_hash``, or the outcome why not."""
    row = (
        model.objects.select_for_update()
        .filter(code_hash=code_hash, consumed_at__isnull=True, expires_at__gt=now)
        .select_related(target_field)
        .order_by("-created_at")
        .first()
    )
    if row is not None:
        return row, None
    any_row = model.objects.filter(code_hash=code_hash).order_by("-created_at").first()
    if any_row is None:
        return None, LabConsumeOutcome.NOT_FOUND
    if any_row.consumed_at is not None:
        return None, LabConsumeOutcome.ALREADY_USED
    return None, LabConsumeOutcome.EXPIRED


def _mark_consumed(row, discord_user_id: str, guild_id: str, now) -> None:
    row.consumed_at = now
    row.consumed_by_discord_id = discord_user_id
    row.consumed_guild_id = guild_id
    row.save(
        update_fields=["consumed_at", "consumed_by_discord_id", "consumed_guild_id"]
    )


def consume_lab_activation_code(
    code_hash: str, discord_user_id: str, guild_id: str, guild_name: str = ""
) -> LabCodeResult:
    """Atomically redeem a lab code and bind *that lab* in *this guild* (ACTIVE).

    A server holds many bindings and a lab can be bound in many servers, so neither
    is a conflict any more; redeeming in a server where the lab is already bound
    simply re-activates that binding. The code carries the authority — the
    redeemer needs no linked identity.
    """
    discord_user_id = str(discord_user_id)
    guild_id = str(guild_id or "")
    now = timezone.now()
    with transaction.atomic():
        row, outcome = _consume_code(DiscordLabActivationCode, "lab", code_hash, now)
        if row is None:
            return LabCodeResult(outcome)
        lab = row.lab
        if not guild_id:
            return LabCodeResult(LabConsumeOutcome.CONFLICT, lab=lab)
        confirmer = resolve_user(discord_user_id)  # may be None (identity optional)
        binding = _activate_binding(guild_id, guild_name, lab=lab, confirmer=confirmer)
        _mark_consumed(row, discord_user_id, guild_id, now)
        audit.discord_audit(
            action="discord.lab_activate.consumed",
            actor=confirmer,
            guild_id=guild_id,
            metadata={"lab_id": str(lab.id), "binding_id": binding.id},
        )
        return LabCodeResult(LabConsumeOutcome.OK, lab=lab, binding=binding)


def consume_department_activation_code(
    code_hash: str, discord_user_id: str, guild_id: str, guild_name: str = ""
) -> LabCodeResult:
    """Atomically redeem a department code and bind *that department* here."""
    discord_user_id = str(discord_user_id)
    guild_id = str(guild_id or "")
    now = timezone.now()
    with transaction.atomic():
        row, outcome = _consume_code(
            DiscordDepartmentActivationCode, "department", code_hash, now
        )
        if row is None:
            return LabCodeResult(outcome)
        department = row.department
        if not guild_id:
            return LabCodeResult(LabConsumeOutcome.CONFLICT, department=department)
        confirmer = resolve_user(discord_user_id)
        binding = _activate_binding(
            guild_id, guild_name, department=department, confirmer=confirmer
        )
        _mark_consumed(row, discord_user_id, guild_id, now)
        audit.discord_audit(
            action="discord.department_activate.consumed",
            actor=confirmer,
            guild_id=guild_id,
            metadata={"department_id": str(department.id), "binding_id": binding.id},
        )
        return LabCodeResult(
            LabConsumeOutcome.OK, department=department, binding=binding
        )


# --------------------------------------------------------------------------- #
# Outbound message queue (Workstream A)
# --------------------------------------------------------------------------- #
# Re-exported so ``services.outbox`` can branch on state without importing the model.
OUTBOX_PENDING = DiscordOutboxMessage.Status.PENDING
OUTBOX_SENDING = DiscordOutboxMessage.Status.SENDING
OUTBOX_SENT = DiscordOutboxMessage.Status.SENT
OUTBOX_FAILED = DiscordOutboxMessage.Status.FAILED
OUTBOX_DEAD = DiscordOutboxMessage.Status.DEAD
OUTBOX_DM = DiscordOutboxMessage.Target.DM
OUTBOX_CHANNEL = DiscordOutboxMessage.Target.CHANNEL
OUTBOX_MODE = DiscordOutboxMessage.Mode


def next_resend_key(base: str) -> str:
    """A dedupe key that deliberately misses ``base`` — for a manual re-send.

    ``enqueue_outbox`` is idempotent on ``dedupe_key``, which is what stops a re-run
    of the daily chain from messaging everyone twice. It also silently swallows every
    deliberate re-send: an operator asking Mylo to send today's report again re-found
    the settled row from this morning and queued nothing, with no error to explain it.

    So a re-send takes its own key — ``<base>:resend:<n>``, where ``n`` is the first
    free number. The daily key is untouched (the chain stays idempotent), each
    re-send is a distinct row rather than a resurrection of a settled one, and the
    history reads as what it is: the morning send, then two re-sends.
    """
    taken = set(
        DiscordOutboxMessage.objects.filter(
            dedupe_key__startswith=f"{base}:resend:"
        ).values_list("dedupe_key", flat=True)
    )
    attempt = 1
    while f"{base}:resend:{attempt}" in taken:
        attempt += 1
    return f"{base}:resend:{attempt}"


def enqueue_outbox(
    *,
    dedupe_key: str,
    kind: str,
    target_type: str,
    recipient_user=None,
    recipient_discord_id: str = "",
    channel_id: str = "",
    lab=None,
    content: str = "",
    embed: dict | None = None,
    allowed_mentions: dict | None = None,
    attachment_path: str = "",
    attachment_filename: str = "",
    subject_type: str = "",
    subject_id: str = "",
    now: datetime | None = None,
    not_before: datetime | None = None,
    components: list | None = None,
    mode: str = DiscordOutboxMessage.Mode.MESSAGE,
    extra: dict | None = None,
) -> tuple[DiscordOutboxMessage, bool]:
    """Queue one message. Returns ``(row, created)``.

    Idempotent on ``dedupe_key``: re-running a producer re-finds the existing row
    rather than queueing a second message. That is what lets the daily chain be
    re-run without spamming anyone, and it is deliberately a database uniqueness
    constraint rather than an application check.

    ``not_before`` holds the row back until a wall-clock instant, by setting the
    ``next_attempt_at`` the drain already filters on (``<= now``). No new machinery:
    scheduled delivery and retry backoff are the same mechanism, so a scheduled row
    retries, dead-letters and reports exactly like every other row. A ``not_before``
    already in the past is due immediately, which is the right answer when the
    nightly run finishes after the recipient's send hour — the alternative is
    holding a finished report for 23 hours.
    """
    now = now or timezone.now()
    return DiscordOutboxMessage.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "kind": kind,
            "target_type": target_type,
            "recipient_user": recipient_user,
            "recipient_discord_id": str(recipient_discord_id or ""),
            "channel_id": channel_id,
            "lab": lab,
            "content": content,
            "embed": embed,
            "components": components,
            "mode": mode,
            "extra": extra,
            "allowed_mentions": allowed_mentions,
            "attachment_path": attachment_path,
            "attachment_filename": attachment_filename,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "next_attempt_at": max(not_before, now) if not_before else now,
        },
    )


def claim_outbox_batch(
    *, limit: int = 50, now: datetime | None = None
) -> list[DiscordOutboxMessage]:
    """Claim up to ``limit`` due messages, marking each in flight.

    ``attempts`` is incremented and the status flipped to SENDING **before** the HTTP
    call, inside the lock. A process that dies mid-send therefore leaves a row that
    has visibly consumed an attempt, instead of one that looks untouched and gets
    re-sent from scratch by the next drain.

    ``skip_locked`` keeps concurrent drains from contending over the same rows; it is
    Postgres-only, so on SQLite (most of the test suite) this degrades to a plain
    ordered read, which is correct for the single-threaded case tests exercise.
    """
    now = now or timezone.now()
    with transaction.atomic():
        rows = list(
            DiscordOutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(
                status__in=(
                    DiscordOutboxMessage.Status.PENDING,
                    DiscordOutboxMessage.Status.SENDING,
                ),
                next_attempt_at__lte=now,
            )
            .order_by("next_attempt_at", "id")[:limit]
        )
        for row in rows:
            row.status = DiscordOutboxMessage.Status.SENDING
            row.attempts += 1
            row.save(update_fields=["status", "attempts", "updated_at"])
    return rows


def mark_outbox_sent(
    message: DiscordOutboxMessage,
    *,
    discord_message_id: str = "",
    now: datetime | None = None,
) -> None:
    now = now or timezone.now()
    message.status = DiscordOutboxMessage.Status.SENT
    message.discord_message_id = discord_message_id or ""
    message.last_error_code = None
    message.last_error_reason = ""
    message.sent_at = now
    message.settled_at = now
    message.save(
        update_fields=[
            "status",
            "discord_message_id",
            "last_error_code",
            "last_error_reason",
            "sent_at",
            "settled_at",
            "updated_at",
        ]
    )


def mark_outbox_retry(
    message: DiscordOutboxMessage,
    *,
    next_attempt_at: datetime,
    error_code: int | None = None,
    reason: str = "",
) -> None:
    """Release a claimed message back to PENDING, due later."""
    message.status = DiscordOutboxMessage.Status.PENDING
    message.next_attempt_at = next_attempt_at
    message.last_error_code = error_code
    message.last_error_reason = reason
    message.save(
        update_fields=[
            "status",
            "next_attempt_at",
            "last_error_code",
            "last_error_reason",
            "updated_at",
        ]
    )


def mark_outbox_permanent(
    message: DiscordOutboxMessage,
    *,
    error_code: int | None = None,
    reason: str = "",
    now: datetime | None = None,
) -> None:
    """Settle a message that retrying cannot help."""
    _settle_unsendable(
        message,
        status=DiscordOutboxMessage.Status.FAILED,
        error_code=error_code,
        reason=reason,
        now=now,
    )


def mark_outbox_dead(
    message: DiscordOutboxMessage,
    *,
    error_code: int | None = None,
    reason: str = "",
    now: datetime | None = None,
) -> None:
    """Settle a message whose attempts are exhausted."""
    _settle_unsendable(
        message,
        status=DiscordOutboxMessage.Status.DEAD,
        error_code=error_code,
        reason=reason,
        now=now,
    )


def _settle_unsendable(
    message: DiscordOutboxMessage,
    *,
    status: str,
    error_code: int | None,
    reason: str,
    now: datetime | None,
) -> None:
    message.status = status
    message.last_error_code = error_code
    message.last_error_reason = reason
    message.settled_at = now or timezone.now()
    message.save(
        update_fields=[
            "status",
            "last_error_code",
            "last_error_reason",
            "settled_at",
            "updated_at",
        ]
    )


def channels_found_gone(*, kind_prefix: str) -> list[str]:
    """Channel ids whose queued sends failed because the channel no longer exists
    (Discord's Unknown Channel), for producers of ``kind_prefix``."""
    return list(
        DiscordOutboxMessage.objects.filter(
            kind__startswith=kind_prefix,
            status=DiscordOutboxMessage.Status.FAILED,
            last_error_reason="channel_gone",
        )
        .values_list("channel_id", flat=True)
        .distinct()
    )


def get_outbox_by_key(dedupe_key: str) -> DiscordOutboxMessage | None:
    return DiscordOutboxMessage.objects.filter(dedupe_key=dedupe_key).first()


def get_outbox_message(pk) -> DiscordOutboxMessage | None:
    return DiscordOutboxMessage.objects.filter(pk=pk).first()


def outbox_counters(*, since: datetime | None = None) -> dict:
    """Attempted / delivered / retried / dead, for operations and the portal."""
    rows = DiscordOutboxMessage.objects.all()
    if since is not None:
        rows = rows.filter(created_at__gte=since)
    return {
        "queued": rows.count(),
        "attempted": rows.filter(attempts__gt=0).count(),
        "delivered": rows.filter(status=DiscordOutboxMessage.Status.SENT).count(),
        "retried": rows.filter(attempts__gt=1).count(),
        "failed": rows.filter(status=DiscordOutboxMessage.Status.FAILED).count(),
        "dead": rows.filter(status=DiscordOutboxMessage.Status.DEAD).count(),
        "pending": rows.filter(
            status__in=(
                DiscordOutboxMessage.Status.PENDING,
                DiscordOutboxMessage.Status.SENDING,
            )
        ).count(),
    }


def purge_outbox(*, before: datetime) -> list[str]:
    """Delete settled-successful rows older than ``before``; return their file paths.

    Only SENT rows are purged. FAILED and DEAD rows are the diagnostic record of what
    went wrong and why, so they stay until someone looks at them. The caller unlinks
    the returned attachment paths — this module owns the database, not the filesystem.
    """
    rows = DiscordOutboxMessage.objects.filter(
        status=DiscordOutboxMessage.Status.SENT, settled_at__lt=before
    )
    paths = [p for p in rows.values_list("attachment_path", flat=True) if p]
    rows.delete()
    return paths


def outbox_attachment_paths_for_settled() -> list[str]:
    """Attachment paths on rows that will never be sent again (FAILED/DEAD/SENT)."""
    return [
        p
        for p in DiscordOutboxMessage.objects.filter(
            status__in=DiscordOutboxMessage.TERMINAL
        ).values_list("attachment_path", flat=True)
        if p
    ]


# --------------------------------------------------------------------------- #
# Route health (Workstream E)
# --------------------------------------------------------------------------- #
def set_route_health(
    route, *, ok: bool | None, error_code: int | None = None
) -> DiscordChannelRoute:
    """Record whether Mylo can still post to one bound channel.

    Mirrors :func:`set_identity_dm` for people: reachability is *measured* and
    stored, never inferred at read time, so the portal can explain a silence instead
    of a lab discovering it by noticing nothing arrived.
    """
    now = timezone.now()
    route.ok = ok
    route.checked_at = now
    route.save(update_fields=["ok", "checked_at", "updated_at"])
    binding = route.binding
    binding.channel_checked_at = now
    fields = ["channel_checked_at", "updated_at"]
    if error_code is not None:
        binding.last_error_code = error_code
        fields.append("last_error_code")
    binding.save(update_fields=fields)
    if ok is False:
        audit.discord_audit(
            action="discord.guild.channel_unreachable",
            guild_id=binding.guild.guild_id,
            metadata={
                "kind": route.purpose,
                "error_code": error_code,
                "binding_id": binding.id,
            },
        )
    return route


def set_channel_health_by_channel(
    channel_id: str, *, ok: bool | None, error_code: int | None = None
) -> int:
    """``set_route_health`` for every route posting to ``channel_id``; returns how
    many. A permanent outbox failure knows the channel, not which binding."""
    rows = list(
        DiscordChannelRoute.objects.filter(channel_id=str(channel_id)).select_related(
            "binding__guild"
        )
    )
    for route in rows:
        set_route_health(route, ok=ok, error_code=error_code)
    return len(rows)


def clear_channel_by_id(guild_id: str, channel_id: str) -> str:
    """Unbind every route in this server that used ``channel_id``; return the
    purposes it held (comma-joined, '' if none). Discord tells us a channel was
    deleted by id, not by which role it was playing."""
    rows = list(
        DiscordChannelRoute.objects.filter(
            binding__guild__guild_id=str(guild_id), channel_id=str(channel_id)
        ).select_related("binding__guild")
    )
    purposes = []
    for route in rows:
        set_route_health(route, ok=False)
        clear_route(route.binding, route.purpose)
        purposes.append(route.purpose)
    return ",".join(sorted(set(purposes)))


def set_addon_ok(binding, *, ok: bool) -> DiscordTargetBinding:
    """Record whether the target's Mylo add-on was live at the last check."""
    if binding.addon_ok == ok:
        return binding
    binding.addon_ok = ok
    binding.save(update_fields=["addon_ok", "updated_at"])
    if not ok:
        audit.discord_audit(
            action="discord.guild.addon_lapsed",
            guild_id=binding.guild.guild_id,
            metadata={"binding_id": binding.id, "target": binding.target_kind},
        )
    return binding


def active_bindings():
    """Every binding in a server Mylo is still in — the reconcile sweep's set."""
    return list(
        DiscordTargetBinding.objects.filter(state=DiscordTargetBinding.State.ACTIVE)
        .exclude(guild__state=DiscordGuildLink.State.KICKED)
        .select_related("guild", "lab", "department")
        .prefetch_related("routes")
    )


def _route_health(route) -> dict:
    if route is None:
        return {"bound": False, "channel_id": "", "ok": None, "verified_at": None}
    return {
        "bound": True,
        "channel_id": route.channel_id,
        "ok": route.ok,
        "verified_at": route.verified_at,
    }


def binding_health(binding) -> dict:
    routes = routes_for_binding(binding)
    return {
        "binding_id": binding.id,
        "state": _binding_state(binding),
        "guild_id": binding.guild.guild_id,
        "guild_name": binding.guild.guild_name_cache,
        "checked_at": binding.channel_checked_at,
        "addon_ok": binding.addon_ok,
        "last_error_code": binding.last_error_code,
        "channels": {
            "announcements": _route_health(routes.get("deadlines")),
            "updates": _route_health(routes.get("updates")),
        },
        "routes": {
            purpose: {**_route_health(route), "channel_type": route.channel_type,
                      "channel_name": route.channel_name,
                      "poster_policy": route.poster_policy}
            for purpose, route in routes.items()
        },
    }


def guild_health_for_lab(lab) -> dict | None:
    """The lab's Discord health for the portal: its primary server, flattened, plus
    every server it is bound in. ``None`` when unlinked."""
    binding = _primary_binding(lab)
    if binding is None:
        return None
    health = binding_health(binding)
    health["servers"] = [binding_health(b) for b in all_bindings_for_lab(lab)]
    return health


def member_reachability(users) -> dict:
    """``{user_id: {linked, dm_ok, ...}}`` for a lab roster.

    Note ``linked`` and ``dm_ok`` are genuinely independent of guild membership: a
    personal DM works through the user's own installation and does not require
    sharing a server with the bot. Conflating them would tell someone their
    reminders are broken when only their ability to be *tagged* is.
    """
    ids = [u.id for u in users]
    if not ids:
        return {}
    rows = DiscordIdentity.objects.filter(user_id__in=ids)
    by_user = {r.user_id: r for r in rows}
    out = {}
    for user in users:
        identity = by_user.get(user.id)
        out[user.id] = {
            "linked": bool(
                identity and identity.state == DiscordIdentity.State.ACTIVE
            ),
            "dm_ok": identity.dm_ok if identity else None,
            "checked_at": identity.dm_checked_at if identity else None,
        }
    return out


def lab_member_reachability(lab) -> list[dict]:
    """The lab's roster with each person's Discord reachability, for the portal.

    Lives here rather than in the view because ``views.py`` is one of the modules the
    import-graph test forbids from touching a model at all — the whole point of the
    boundary. One query for memberships, one for identities.
    """
    from apps.core.people import display_name

    memberships = list(
        LabMembership.objects.filter(lab=lab)
        .select_related("user")
        .order_by("user__username")
    )
    reach = member_reachability([m.user for m in memberships])
    return [
        {
            "username": m.user.get_username(),
            "name": display_name(m.user),
            "role": m.role,
            **reach.get(m.user_id, {"linked": False, "dm_ok": None}),
        }
        for m in memberships
    ]

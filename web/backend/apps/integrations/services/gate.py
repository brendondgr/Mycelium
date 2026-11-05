"""The one gate every inbound Discord interaction passes through.

Five stages, in this order, and the order is load-bearing:

1. **Identity** — the snowflake Discord itself vouches for on the interaction, resolved
   to an ACTIVE linked Mycelium account.
2. **Rate limit** — before any object lookup, so an unlinked or hostile caller cannot
   use the gate as an oracle for which labs exist.
3. **Object permission** — through ``apps.accounts.permissions``, never a parallel
   Discord-side rule.
4. **Entitlement** — through ``apps.billing.entitlements``, at the point of use.
5. **Audit** — every outcome, allowed or denied.

**Authority comes only from the interaction's user id.** A command argument, a
component's ``custom_id``, and ``username_cache`` are all display data that originate
on someone's client; none of them may decide what happens. The gate takes a
``lab_slug`` from the caller precisely *because* it is untrusted — it names which lab
to check, and the check is what decides.

**A refusal never confirms the object exists.** "No such lab" and "not your lab" are
the same sentence, or the gate leaks the shape of every organisation on the platform
to anyone who can type a slug.

Note what does *not* apply here: Mylo is a discord.py gateway client, so there is no
signed HTTP payload to verify and no forged-request class of attack at this layer.
The trust anchor is the bot token at the WebSocket handshake.

``/activate`` and ``/activate-lab`` deliberately do **not** route through this gate:
they are the linking flow, so they cannot require a link, and `/activate-lab` was
explicitly exempted from the billing check on 2026-07-18 (a valid manager-issued code
carries the authority; billing is enforced on the delivery path instead).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from django.conf import settings

from . import audit, resolve, state


class Denial(StrEnum):
    NOT_LINKED = "not_linked"
    RATE_LIMITED = "rate_limited"
    NOT_ENTITLED = "not_entitled"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class GateResult:
    ok: bool
    user: object | None = None
    lab: object | None = None
    department: object | None = None
    binding: object | None = None
    denial: Denial | None = None
    message: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class _Action:
    """What one command needs before it may run.

    Declared in one table rather than re-derived per command, because this table *is*
    the authorization policy — a reviewer should be able to read it in one place and
    know exactly who can do what.
    """

    #: "manage" → owner/admin, "edit" → +PI/lead, "access" → any member, "" → personal.
    lab_permission: str = ""
    #: A ``billing.entitlements.Feature`` required of the *lab*, if any.
    lab_feature: str = ""
    #: Rate-limit bucket name; falls back to the default bucket.
    bucket: str = "command"


_ACTIONS: dict[str, _Action] = {
    # Personal reads — nothing beyond a linked account. Search is deliberately not
    # entitlement-gated: it is ungated on the web for every tier, and making Discord
    # users *less* privileged than web users for the identical capability would be a
    # product regression dressed up as security.
    "search": _Action(bucket="search"),
    "digest": _Action(),
    "saves": _Action(),
    # Reminder management is owner-scoped; the per-object owner check happens in the
    # command, since the gate cannot know which reminder was named until it loads it.
    "snooze": _Action(),
    "cancel": _Action(),
    # Lab-scoped. `/setup` binds where a lab's messages land, so it needs the same
    # management right the web app requires — and the bot add-on that pays for it.
    "setup": _Action(lab_permission="manage", lab_feature="bot_server"),
    "lab_digest": _Action(lab_permission="access", lab_feature="bot_server"),
    # Turning listening on for a whole server is the most consequential switch
    # the bot has, so it is held to the same right as `/setup` and not a looser
    # one. Deciding whether *your own* messages may be read is personal and
    # needs only a linked account — nobody should have to ask a manager for
    # permission to opt out.
    "listening": _Action(lab_permission="manage", lab_feature="bot_server"),
    "listening_self": _Action(),
}

_DEFAULT_ACTION = _Action()

_NOT_LINKED = (
    "Your Discord isn't connected to Mycelium yet. Open your profile in Mycelium "
    "and use **Connect Discord**, or run `/activate` with a code from there."
)
_RATE_LIMITED = "That's a lot at once — give me a moment and try again."
_FORBIDDEN = "You don't have access to that."
_LOCKED = "Too many attempts. Try again in about an hour."


def authorize(
    *,
    discord_user_id: str,
    action: str,
    lab_slug: str = "",
    guild_id: str = "",
    subject_id: str = "",
    binding_id: int | str | None = None,
) -> GateResult:
    """Run the five stages for one interaction. Never raises.

    ``binding_id`` names one lab-or-department binding in a server (untrusted, like
    ``lab_slug``): the check then runs against *that binding's* target, so a
    department manager can configure the department's binding and nobody else's.
    """
    spec = _ACTIONS.get(action, _DEFAULT_ACTION)

    # 1 — who. The only trusted input in this function.
    user = resolve.resolve_user(str(discord_user_id))
    if user is None:
        return _deny(action, discord_user_id, Denial.NOT_LINKED, _NOT_LINKED)

    # 2 — how often. Before any lookup, so this cannot become a probing oracle.
    if state.is_locked_out(str(discord_user_id)):
        return _deny(action, discord_user_id, Denial.RATE_LIMITED, _LOCKED, user=user)
    if not _within_rate(discord_user_id, spec.bucket):
        return _deny(
            action, discord_user_id, Denial.RATE_LIMITED, _RATE_LIMITED, user=user
        )

    # 3 — what they may touch. A lab named by an untrusted argument is resolved and
    # then checked; failing either way gives the same answer.
    lab = None
    department = None
    binding = None
    if spec.lab_permission and binding_id not in (None, ""):
        binding = _resolve_binding(binding_id, guild_id=guild_id)
        if binding is None or not _has_binding_permission(
            user, binding, spec.lab_permission
        ):
            return _deny(
                action, discord_user_id, Denial.FORBIDDEN, _FORBIDDEN, user=user
            )
        lab, department = binding.lab, binding.department
    elif spec.lab_permission:
        lab = _resolve_lab(lab_slug=lab_slug, guild_id=guild_id)
        if lab is None or not _has_lab_permission(user, lab, spec.lab_permission):
            return _deny(
                action, discord_user_id, Denial.FORBIDDEN, _FORBIDDEN, user=user
            )

    # 4 — whether the plan covers it, checked here rather than trusted from install.
    if spec.lab_feature and department is not None:
        allowed, message = _department_entitled(department, spec.lab_feature)
        if not allowed:
            return _deny(
                action, discord_user_id, Denial.NOT_ENTITLED, message, user=user
            )
    if spec.lab_feature and lab is not None:
        allowed, message = _lab_entitled(lab, spec.lab_feature)
        if not allowed:
            return _deny(
                action,
                discord_user_id,
                Denial.NOT_ENTITLED,
                message,
                user=user,
                lab=lab,
            )

    _audit(action, discord_user_id, "allowed", user=user, lab=lab, subject=subject_id)
    return GateResult(
        ok=True, user=user, lab=lab, department=department, binding=binding
    )


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #
def _within_rate(discord_user_id: str, bucket: str) -> bool:
    limits = getattr(settings, "DISCORD_COMMAND_RATE_LIMITS", {}) or {}
    limit, window = limits.get(bucket, limits.get("command", (20, 60)))
    return state.check_rate(
        str(discord_user_id), bucket=bucket, limit=int(limit), window=int(window)
    )


def _resolve_lab(*, lab_slug: str, guild_id: str):
    """The lab this action targets: the named one, else the guild's own.

    Both inputs are untrusted; neither grants anything. Resolution only decides *which*
    permission check to run.
    """
    if lab_slug:
        return resolve.get_lab_by_slug(str(lab_slug))
    if guild_id:
        return resolve.resolve_lab_for_guild(str(guild_id))
    return None


def _resolve_binding(binding_id, *, guild_id: str):
    """The binding named by an untrusted id — only if it sits in *this* server."""
    try:
        binding = resolve.get_binding(int(binding_id))
    except (TypeError, ValueError):
        return None
    if binding is None or binding.state != resolve.BINDING_ACTIVE:
        return None
    if guild_id and binding.guild.guild_id != str(guild_id):
        return None
    return binding


def _has_binding_permission(user, binding, level: str) -> bool:
    if binding.lab_id:
        return _has_lab_permission(user, binding.lab, level)
    from apps.accounts.permissions import (
        user_can_edit_dept_profile,
        user_can_manage_department,
        user_has_department_access,
    )

    if level == "manage":
        return user_can_manage_department(user, binding.department)
    if level == "edit":
        return user_can_edit_dept_profile(user, binding.department)
    return user_has_department_access(user, binding.department)


def _department_entitled(department, feature: str) -> tuple[bool, str]:
    from apps.billing.entitlements import department_has_feature

    if department_has_feature(department, feature):
        return True, ""
    return False, (
        f"**{department.name}**'s plan doesn't include Mylo in Discord. A department "
        "admin can add the Mylo bot add-on from the department's settings in Mycelium."
    )


def _has_lab_permission(user, lab, level: str) -> bool:
    """Terminate in Mycelium's own permission functions — never a Discord-side rule."""
    from apps.accounts.permissions import (
        user_can_edit_lab_profile,
        user_can_manage_lab,
        user_has_lab_access,
    )

    if level == "manage":
        return user_can_manage_lab(user, lab)
    if level == "edit":
        return user_can_edit_lab_profile(user, lab)
    return user_has_lab_access(user, lab)


def _lab_entitled(lab, feature: str) -> tuple[bool, str]:
    from apps.billing.entitlements import lab_has_feature

    if lab_has_feature(lab, feature):
        return True, ""
    return False, (
        f"**{lab.name}**'s plan doesn't include Mylo in Discord. A lab admin can add "
        "the Mylo bot add-on from the lab's settings in Mycelium."
    )


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def _deny(
    action: str,
    discord_user_id: str,
    denial: Denial,
    message: str,
    *,
    user=None,
    lab=None,
) -> GateResult:
    _audit(action, discord_user_id, str(denial), user=user, lab=lab)
    return GateResult(ok=False, user=user, lab=lab, denial=denial, message=message)


def _audit(
    action: str,
    discord_user_id: str,
    outcome: str,
    *,
    user=None,
    lab=None,
    subject: str = "",
) -> None:
    """One row per interaction, allowed or denied.

    Denials matter more than successes here: a refused command is the trace that
    answers "why did nothing happen when I ran that?" months later, and is the only
    signal that would show someone probing for labs they cannot see.
    """
    meta = {"action": action, "outcome": outcome}
    if lab is not None:
        meta["lab_id"] = str(getattr(lab, "id", ""))
    if subject:
        meta["subject_id"] = str(subject)
    audit.discord_audit(
        action=f"discord.command.{action}",
        actor=user,
        discord_user_id=discord_user_id,
        metadata=meta,
    )

"""The one gate: ``decide(caller, function, args)``.

Nine layers, in order, the first deny wins (docs/plans/mylo-agent/permissions.md):

1. loaded            the function's owning tool is LOADED
2. instance          [tools.agent] groups_off, surface_groups_off, max_risk
3. features          features.* flags and billing entitlements
4. org policy        AgentOrgPolicy of the thread's lab or department (narrows only)
5. scope and role    the caller can see the scope and holds min_role there
6. object arguments  every x-ref argument resolves for this caller
7. person            AgentPreference: chat off, groups off, Discord off
8. risk              the function's risk against the thread's mode
9. audience          the function's output is at least as wide as the audience

The catalog shown to the model is built with the same function and no
arguments; every call is decided again with its real arguments. ``decide``
reads the caller and the arguments only, never text the model has read.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.conf import settings

from tools._framework import host
from tools._framework.agentspec import (
    GUEST_LEVELS,
    ROLES,
    AgentFunction,
    guest_rank,
    width_rank,
)

from . import config

#: What each thread mode lets through, per risk.
MODES = {
    "read": {
        "read": "allow",
        "write": "deny",
        "external": "deny",
        "destructive": "deny",
    },
    "ask": {
        "read": "allow",
        "write": "confirm",
        "external": "confirm",
        "destructive": "confirm",
    },
}
_RISK_ORDER = ("read", "write", "external", "destructive")


@dataclass(frozen=True)
class Decision:
    verdict: str  # allow | deny | confirm
    layer: int = 0
    code: str = ""
    detail: str = ""
    fix: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


ALLOW = Decision("allow")


def _deny(layer: int, code: str, detail: str, fix: str = "") -> Decision:
    return Decision("deny", layer, code, detail, fix)


# --------------------------------------------------------------------------- #
# Helpers over the platform's existing checks
# --------------------------------------------------------------------------- #


def feature_on(key: str) -> bool:
    """A ``features.*`` instance key, read through its Django setting so
    ``override_settings`` works in tests."""
    from config.instance import BY_KEY

    spec = BY_KEY.get(key)
    if spec is None:
        return False
    if spec.env and hasattr(settings, spec.env):
        return bool(getattr(settings, spec.env))
    return bool(settings.INSTANCE.values.get(key, spec.default))


def entitled(user, feature: str) -> bool:
    from apps.billing import entitlements

    return entitlements.has_feature(user, feature)


def lab_role(user, lab) -> str | None:
    from apps.accounts.models import LabMembership

    row = LabMembership.objects.filter(user=user, lab=lab).only("role").first()
    return row.role if row else None


def department_role(user, department) -> str | None:
    from apps.accounts.models import DeptMembership
    from apps.accounts.permissions import user_has_department_access

    if department.owner_id == user.id:
        return "owner"
    row = DeptMembership.objects.filter(user=user, department=department).first()
    if row:
        return row.role
    return "member" if user_has_department_access(user, department) else None


def project_role(user, project) -> str | None:
    from apps.research.permissions import user_can_edit_project

    if project.is_archived or not project.is_visible_to(user):
        return None
    return "editor" if user_can_edit_project(user, project) else "viewer"


def role_in(user, kind: str, obj) -> str | None:
    if kind == "lab":
        return lab_role(user, obj)
    if kind == "department":
        return department_role(user, obj)
    if kind == "project":
        return project_role(user, obj)
    return None


def role_of(caller, kind: str, obj) -> str | None:
    """The caller's role on ``obj``. A guest stands where a ``member`` of the
    place stands, and only there: the place is the thread's own lab or
    department (its scope), never anything an argument names."""
    if caller.user is not None:
        return role_in(caller.user, kind, obj)
    if not caller.is_guest or obj is None:
        return None
    place = caller.scope.obj
    if caller.scope.kind == kind and place is not None and place.pk == obj.pk:
        return "member"
    return None


def guest_level(caller) -> str:
    """What a guest may be told here: the host's ceiling, then the place's
    lab or department policy; the lower wins (S-16). ``off`` unless the host
    lets guests ask at all (``discord_access = "public"``)."""
    if config.get("discord_access") != "public":
        return "off"
    level = config.get("discord_guest_level") or "full"
    if caller.scope.kind == "personal":
        # A server where Mylo cannot tell whose room it is: public material
        # only, for everyone (plan D, "Places").
        return level if guest_rank(level) < guest_rank("public") else "public"
    for policy in org_policies(caller.scope):
        own = policy.discord_guests or "full"
        if guest_rank(own) < guest_rank(level):
            level = own
    return level if level in GUEST_LEVELS else "off"


def _at_least(kind: str, held: str | None, needed: str) -> bool:
    ladder = ROLES[kind]
    return held in ladder and ladder.index(held) >= ladder.index(needed)


def within_audience(info, audience) -> bool:
    """Width is not enough: a lab-wide object of lab B is still not for lab
    A's channel. Where the audience is an org, an org-scoped object must
    belong to that org (or a wider one containing it). A project must also be
    scoped at least as wide as the audience
    (:func:`apps.research.visibility.may_surface`): its scope decides, not
    which org owns it."""
    if audience.width == "person" or info.output == "instance":
        return True
    if info.kind == "project" and not _project_may_surface(info.key, audience.width):
        return False
    if info.output == "public":
        return True
    org = audience.obj
    if org is None:  # an unbound channel: only what any signed-in person sees
        return False
    from apps.accounts.models import Department, Lab, LabMembership
    from apps.research.models import Project

    lab_ids, dept_ids = set(), set()
    if isinstance(org, Lab):
        lab_ids = {org.pk}
        dept_ids = {org.department_id} if org.department_id else set()
    elif isinstance(org, Department):
        dept_ids = {org.pk}
        lab_ids = set(Lab.objects.filter(department=org).values_list("pk", flat=True))
    elif isinstance(org, Project):
        if info.kind == "project":
            return str(info.key) == str(org.pk)
        lab_ids = {org.scope_lab_id} if org.scope_lab_id else set()
    kind, key = info.kind, str(info.key)
    if kind == "lab":
        return Lab.objects.filter(slug=key, pk__in=lab_ids).exists()
    if kind == "department":
        return key in {str(d) for d in dept_ids}
    if kind == "project":
        return (
            Project.objects.filter(pk=key).filter(models_q(lab_ids, dept_ids)).exists()
        )
    if kind == "person":
        return LabMembership.objects.filter(
            user__username=key, lab_id__in=lab_ids
        ).exists()
    if kind == "file":
        from django.apps import apps

        stored = apps.get_model("files", "StoredFile").objects.filter(pk=key).first()
        if stored is None:
            return False
        return (
            stored.owner_lab_id in lab_ids
            or (
                stored.owner_department_id is not None
                and str(stored.owner_department_id) in {str(d) for d in dept_ids}
            )
            or Project.objects.filter(pk=stored.owner_project_id)
            .filter(models_q(lab_ids, dept_ids))
            .exists()
        )
    # items, papers and documents carry their own width; a lab-licensed paper
    # is fine to quote in any lab the caller belongs to
    return True


def _project_may_surface(key, width: str) -> bool:
    """Whether the project ``key`` may be named to an audience of ``width``."""
    from apps.research import visibility
    from apps.research.models import Project

    if width in ("person", "project"):
        return True
    project = Project.objects.filter(pk=key).first() if _is_uuid(key) else None
    return project is not None and visibility.may_surface(project, width)


def _is_uuid(value) -> bool:
    from uuid import UUID

    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def models_q(lab_ids, dept_ids):
    from django.db.models import Q

    return Q(scope_lab_id__in=lab_ids) | Q(scope_department_id__in=dept_ids)


def preference(user):
    from .models import AgentPreference

    return AgentPreference.objects.filter(user=user).first()


def org_policies(scope):
    """The policies that apply to a scope: its lab's and its department's."""
    from .models import AgentOrgPolicy

    out = []
    if scope.lab is not None:
        row = AgentOrgPolicy.objects.filter(lab=scope.lab).first()
        if row:
            out.append(row)
    if scope.department is not None:
        row = AgentOrgPolicy.objects.filter(department=scope.department).first()
        if row:
            out.append(row)
    return out


# --------------------------------------------------------------------------- #
# Whole-agent checks (before any function): may this person chat here at all?
# --------------------------------------------------------------------------- #


def _channel_off(caller) -> Decision | None:
    here = {str(caller.via.get(k) or "") for k in ("channel_id", "parent_id")} - {""}
    if caller.surface == "discord" and here:
        for policy in org_policies(caller.scope):
            if here & {str(c) for c in policy.discord_channels_off}:
                return _deny(
                    4,
                    "channel_off",
                    "Mylo chat is turned off in this channel by your lab.",
                    "Ask in a DM instead.",
                )
    return None


def _may_guest_chat(caller) -> Decision:
    """A guest (S-11): only in Discord, only in a lab's or department's own
    server, and only while the guest level there is above ``off``."""
    scope = caller.scope
    ambiguous = scope.kind == "personal" and caller.audience.width in (
        "public",
        "instance",
    )
    if caller.surface != "discord" or not (
        ambiguous or (scope.kind in ("lab", "department") and scope.obj is not None)
    ):
        return _deny(
            5,
            "guest_place",
            "Mylo answers people without an account only in a server a lab or "
            "department has connected.",
            "Connect your Discord to Mycelium from your profile.",
        )
    if guest_level(caller) == "off":
        return _deny(
            4,
            "guests_off",
            "Only people with a linked Mycelium account can ask Mylo here.",
            "Connect your Discord to Mycelium from your profile.",
        )
    return _channel_off(caller) or ALLOW


def may_chat(caller) -> Decision:
    """Layers that apply to the agent as a whole: the two switches (D-5),
    entitlement, the scope, and the person's surface setting."""
    if not host.is_loaded("agent"):
        return _deny(
            1,
            "agent_off",
            "Mylo chat isn't enabled on this instance.",
            "Ask the person who runs this Mycelium to turn it on.",
        )
    if caller.user is None:
        if caller.is_guest:
            return _may_guest_chat(caller)
        return _deny(5, "no_caller", "Mylo doesn't know who is asking.")
    # In Discord the plan check is the host's choice (S-5): only ``entitled``
    # asks for the person's plan; the server's own ``bot_server`` add-on is
    # checked by the Discord gate either way.
    plan_check = caller.surface != "discord" or (
        config.get("discord_access") == "entitled"
    )
    if plan_check and not entitled(caller.user, "agent"):
        return _deny(
            3,
            "not_entitled",
            "Mylo chat isn't part of your plan.",
            "See your plan in account settings.",
        )
    scope = caller.scope
    if scope.kind != "personal":
        if scope.obj is None or role_in(caller.user, scope.kind, scope.obj) is None:
            return _deny(
                5,
                "scope_not_visible",
                f"You can't open this {scope.kind} with Mylo.",
                "Open a personal thread, or one in a workspace you belong to.",
            )
    pref = preference(caller.user)
    if pref is not None and not pref.chat_enabled:
        return _deny(
            7,
            "chat_off",
            "You've turned Mylo chat off for yourself.",
            "Turn it back on in your account settings.",
        )
    if caller.surface == "discord" and pref is not None and not pref.discord_allowed:
        return _deny(
            7,
            "discord_off",
            "You've turned off Mylo in Discord.",
            "Turn it back on in your account settings.",
        )
    return _channel_off(caller) or ALLOW


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


def decide(
    caller,
    fn: AgentFunction,
    args: dict | None = None,
    *,
    owner: str | None = None,
    mode: str = "read",
) -> Decision:
    """Decide one function for one caller. ``args=None`` is the catalog check."""
    from .registry import registry

    reg = registry()
    group = fn.group

    # 1. loaded
    owner = owner or reg.owner.get(fn.name)
    if owner is None or not host.is_loaded(owner):
        return _deny(1, "not_loaded", f"{fn.name} is not available on this instance.")

    # 2. instance policy
    cfg = config.values()
    if group in cfg["groups_off"]:
        return _deny(
            2, "group_off", f"{group} functions are turned off on this instance."
        )
    off = cfg["surface_groups_off"]
    shared = width_rank(caller.audience.width) > width_rank("person")
    if f"{caller.surface}:{group}" in off or (
        shared and f"{caller.surface}_channel:{group}" in off
    ):
        return _deny(
            2,
            "surface_group_off",
            f"{group} functions are turned off in {caller.surface}.",
            "Ask in the web app instead.",
        )
    if caller.surface not in fn.surfaces:
        return _deny(2, "surface", f"{fn.name} isn't available in {caller.surface}.")
    if _RISK_ORDER.index(fn.risk) > _RISK_ORDER.index(cfg["max_risk"]):
        return _deny(2, "risk_off", "Mylo can only read on this instance.")

    # 3. features and entitlements
    for part in (fn.feature or "").split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("entitlement:"):
            if caller.user is None or not entitled(caller.user, part.split(":", 1)[1]):
                return _deny(
                    3,
                    "not_entitled",
                    f"{fn.name} isn't part of your plan.",
                    "See your plan in account settings.",
                )
        elif not feature_on(part):
            return _deny(
                3,
                "feature_off",
                f"{part.removeprefix('features.').replace('_', ' ')} is turned "
                "off on this instance.",
            )

    # 4. org policy (narrows only)
    for policy in org_policies(caller.scope):
        if group in (policy.groups_off or []):
            return _deny(
                4,
                "org_group_off",
                f"Your {'lab' if policy.lab_id else 'department'} has turned "
                f"off {group} for Mylo.",
            )
        if _RISK_ORDER.index(fn.risk) > _RISK_ORDER.index(policy.max_risk or "read"):
            return _deny(4, "org_risk", "Your organization lets Mylo only read.")

    # 5. scope and role (a guest: the function's guest level first)
    scope = caller.scope
    if caller.user is None:
        if fn.guest is None or guest_rank(guest_level(caller)) < guest_rank(fn.guest):
            return _deny(
                5,
                "guest",
                f"{fn.name} isn't available to guests here.",
                "Connect your Discord to Mycelium to ask about more.",
            )
    if scope.kind not in fn.scopes:
        return _deny(5, "scope", f"{fn.name} isn't available in a {scope.kind} thread.")
    if scope.kind != "personal":
        held = role_of(caller, scope.kind, scope.obj)
        if held is None:
            return _deny(5, "scope_not_visible", f"You can't see this {scope.kind}.")
        needed = fn.min_role.get(scope.kind)
        if needed and not _at_least(scope.kind, held, needed):
            return _deny(
                5,
                "role",
                f"{fn.name} needs the {needed} role in this "
                f"{scope.kind}; you are {held}.",
            )
    for kind in ("lab", "department"):
        needed = fn.min_role.get(kind)
        obj = getattr(scope, kind)
        if needed and scope.kind not in (kind, "personal") and obj is not None:
            if not _at_least(kind, role_of(caller, kind, obj), needed):
                return _deny(
                    5, "role", f"{fn.name} needs the {needed} role in this {kind}."
                )

    # 6. object arguments
    if args is not None:
        from . import refs

        for key, kind in fn.ref_args().items():
            value = args.get(key)
            if value in (None, "", []):
                continue
            for token in value if isinstance(value, list) else [value]:
                if kind == "thread":  # resolved inside the caller's own thread
                    continue
                info = refs.resolve(caller, str(token), expect_kind=kind)
                if info is None:
                    return _deny(
                        6,
                        "not_visible",
                        f"{token} is not something you can open.",
                        "Use a reference from this conversation or search for it.",
                    )
                if width_rank(info.output) < width_rank(
                    caller.audience.width
                ) or not within_audience(info, caller.audience):
                    return _deny(
                        9,
                        "audience",
                        f"{token} can't be shown to everyone who will read this.",
                        "Ask me in a DM.",
                    )

    # 7. the person's own settings (a guest has none)
    pref = preference(caller.user) if caller.user is not None else None
    if pref is not None:
        if not pref.chat_enabled:
            return _deny(7, "chat_off", "You've turned Mylo chat off for yourself.")
        if group in (pref.groups_off or []):
            return _deny(
                7,
                "person_group_off",
                f"You've turned off {group} for Mylo.",
                "Turn it back on in your account settings.",
            )
        if caller.surface == "discord" and not pref.discord_allowed:
            return _deny(7, "discord_off", "You've turned off Mylo in Discord.")

    # 8. risk against the thread's mode
    verdict = MODES.get(mode, MODES["read"]).get(fn.risk, "deny")
    if verdict == "deny":
        return _deny(
            8,
            "risk",
            "Mylo can't change anything; it only reads.",
            "Say what the person can do in the app instead.",
        )
    if verdict == "confirm":
        return Decision("confirm", 8, "confirm", f"{fn.name} needs your confirmation.")

    # 9. audience
    if width_rank(fn.output) < width_rank(caller.audience.width):
        return _deny(
            9,
            "audience",
            f"{fn.name} returns things not everyone here may see.",
            "Ask me in a DM.",
        )
    return ALLOW


def catalog(caller, *, mode: str = "read") -> list[tuple[AgentFunction, Decision]]:
    """Every registered function with its catalog-time decision."""
    from .registry import registry

    if not may_chat(caller).allowed:
        return []
    reg = registry()
    return [(fn, decide(caller, fn, None, mode=mode)) for fn in reg.functions.values()]


def allowed_functions(caller, *, mode: str = "read") -> list[AgentFunction]:
    return [fn for fn, d in catalog(caller, mode=mode) if d.allowed]

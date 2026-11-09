"""The ``org`` group: the labs and departments a person belongs to, and the
visible fields of the people in them.

Only what the platform already shows a member: names, usernames, roles, and
the interest labels a person *declared*. Nothing Mylo observed or understood
from conversation is ever read here.

Width is not enough on its own where others read the reply: a lab reference
has width ``lab`` whichever lab it is. So in a shared reply every handler here
also checks that the object belongs to the audience's own lab or department
(:func:`audience_lab_ok`), before the model reads anything.
"""

from __future__ import annotations

from tools._framework.agentspec import FunctionError, Result

from . import common

# --------------------------------------------------------------------------- #
# Shared with feeds.py and knowledge.py
# --------------------------------------------------------------------------- #


def shared(caller) -> bool:
    """True when anyone besides the caller will read the reply."""
    return caller.audience.width != "person"


def audience_lab(caller):
    from apps.accounts.models import Lab

    obj = caller.audience.obj
    if isinstance(obj, Lab):
        return obj
    return caller.scope.lab


def audience_department(caller):
    from apps.accounts.models import Department, Lab

    obj = caller.audience.obj
    if isinstance(obj, Department):
        return obj
    if isinstance(obj, Lab):
        return obj.department
    return caller.scope.department


def _not_here(what: str) -> FunctionError:
    return FunctionError(
        "audience",
        f"{what} can't be shown to everyone who will read this.",
        "Ask me in a DM.",
    )


def audience_lab_ok(caller, lab) -> None:
    """In a shared reply, only the audience's own lab may be read."""
    if not shared(caller):
        return
    here = audience_lab(caller)
    if here is None or here.pk != lab.pk:
        raise _not_here("Another lab")


def audience_department_ok(caller, department) -> None:
    if not shared(caller):
        return
    here = audience_department(caller)
    if here is None or here.pk != department.pk:
        raise _not_here("Another department")


def lab_arg(caller, lab):
    """The lab named by a cleared ``lab`` argument, or the thread's lab."""
    from apps.accounts.models import Lab

    if lab:
        row = Lab.objects.filter(slug=common.ref_key(lab)).first()
        if row is None:  # the gate cleared it; this is a race
            raise FunctionError("not_visible", "That lab is not available.")
        return row
    if caller.scope.lab is not None:
        return caller.scope.lab
    raise FunctionError(
        "need_lab", "Which lab?", "Pass lab='#n' or call org_labs first."
    )


def interest_labels(interests) -> list[str]:
    """The labels a person, lab or department declared: cluster themes, else areas."""
    interests = dict(interests or {})
    labels = [
        str(c.get("label"))
        for c in interests.get("clusters") or []
        if isinstance(c, dict) and c.get("label")
    ]
    if not labels:
        labels = [str(a) for a in interests.get("areas") or [] if a]
    return labels


def _clusters(interests) -> list[str]:
    interests = dict(interests or {})
    out = []
    for c in interests.get("clusters") or []:
        if isinstance(c, dict) and c.get("label"):
            areas = ", ".join(map(str, c.get("areas") or []))
            out.append(f"- {c['label']}" + (f": {areas}" if areas else ""))
    if not out and interests.get("areas"):
        out.append("- " + ", ".join(map(str, interests["areas"])))
    return out


def _name(user) -> str:
    return user.get_full_name() or user.username


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


def org_labs(caller):
    from apps.accounts.models import LabMembership

    rows = (
        LabMembership.objects.filter(user=caller.user)
        .select_related("lab")
        .order_by("lab__name")
    )
    if not rows:
        return Result(content="You are not a member of any lab.")
    refs, lines = [], []
    for m in rows:
        info = common.lab_info(m.lab)
        refs.append(info)
        lead = " (PI)" if m.is_lead else ""
        lines.append(f"- {{ref:{info.ref}}} {m.lab.name} — you are {m.role}{lead}")
    return Result(content="Your labs:\n" + "\n".join(lines), refs=refs)


def org_lab(caller, lab=None):
    from apps.accounts.models import LabProfile

    from .. import permissions

    row = lab_arg(caller, lab)
    audience_lab_ok(caller, row)
    info = common.lab_info(row)
    role = permissions.role_of(caller, "lab", row) or "not a member"
    if caller.is_guest:
        role = "a guest in its Discord server (no Mycelium account)"
    profile = LabProfile.objects.filter(lab=row).first()
    lines = [
        f"{{ref:{info.ref}}} {row.name} [{row.slug}]",
        f"Members: {row.memberships.count()}",
        f"Your role: {role}",
    ]
    refs = [info]
    if row.department_id and row.department is not None:
        lines.append(f"Department: {row.department.name}")
    if profile is not None:
        if profile.statement:
            lines.append("Statement: " + common.clip(profile.statement, 600))
        clusters = _clusters(profile.interests)
        if not clusters and profile.areas:
            clusters = ["- " + ", ".join(map(str, profile.areas))]
        lines.append("Profile clusters:\n" + ("\n".join(clusters) or "(none declared)"))
        if profile.funding_needs:
            lines.append("Funding needs: " + ", ".join(map(str, profile.funding_needs)))
    return Result(content="\n".join(lines), refs=refs)


def org_lab_members(caller, lab=None):
    from apps.accounts.models import LabMembership

    from .. import permissions

    row = lab_arg(caller, lab)
    audience_lab_ok(caller, row)
    held = permissions.role_of(caller, "lab", row)
    if held not in ("member", "admin", "owner"):
        raise FunctionError(
            "role",
            "Listing a lab's members needs the member role there.",
            "Ask a lab admin to change your role.",
        )
    members = (
        LabMembership.objects.filter(lab=row)
        .select_related("user", "user__profile")
        .order_by("-is_lead", "user__username")
    )
    head = common.lab_info(row)
    refs, lines = [head], []
    for m in members:
        info = common.person_info(m.user, caller=caller)
        refs.append(info)
        profile = getattr(m.user, "profile", None)
        labels = interest_labels(getattr(profile, "interests", None))
        lead = ", PI" if m.is_lead else ""
        lines.append(
            f"- {{ref:{info.ref}}} {_name(m.user)} (@{m.user.username}) — {m.role}"
            f"{lead}"
            + (f"; declared interests: {', '.join(labels[:8])}" if labels else "")
        )
    return Result(
        content=f"Members of {{ref:{head.ref}}} {row.name} ({len(lines)}):\n"
        + "\n".join(lines),
        refs=refs,
    )


def org_department(caller, department=None):
    from apps.accounts.models import Department, DeptProfile
    from apps.accounts.services import effective_member_ids

    from .. import permissions

    if department:
        dept = Department.objects.filter(pk=common.ref_key(department)).first()
        if dept is None:
            raise FunctionError("not_visible", "That department is not available.")
    elif caller.scope.department is not None:
        dept = caller.scope.department
    else:
        raise FunctionError(
            "need_department",
            "Which department?",
            "Pass department='#n' (see me_profile for yours).",
        )
    audience_department_ok(caller, dept)
    info = common.department_info(dept)
    role = permissions.role_of(caller, "department", dept) or "not a member"
    if caller.is_guest:
        role = "a guest in its Discord server (no Mycelium account)"
    mine = common.member_lab_ids(caller)
    refs, lab_lines = [info], []
    for lab in dept.labs.order_by("name"):
        if lab.pk in mine:
            li = common.lab_info(lab)
            refs.append(li)
            lab_lines.append(f"- {{ref:{li.ref}}} {lab.name}")
        else:
            lab_lines.append(f"- {lab.name}")
    lines = [
        f"{{ref:{info.ref}}} {dept.name}"
        + (f" ({dept.institution})" if dept.institution else ""),
        f"Members (direct and through its labs): {len(effective_member_ids(dept))}",
        f"Your role: {role}",
        "Labs:\n" + ("\n".join(lab_lines) or "(none)"),
    ]
    profile = DeptProfile.objects.filter(department=dept).first()
    if profile is not None:
        if profile.statement:
            lines.append("Statement: " + common.clip(profile.statement, 600))
        clusters = _clusters(profile.interests)
        if clusters:
            lines.append("Profile clusters:\n" + "\n".join(clusters))
    return Result(content="\n".join(lines), refs=refs)


def org_person(caller, person):
    from apps.accounts.models import Lab, LabMembership

    from .kinds import visible_people_for

    user = visible_people_for(caller).filter(username=common.ref_key(person)).first()
    if user is None:  # the gate cleared it; this is a race
        raise FunctionError("not_visible", "That person is not available.")
    labs = list(
        Lab.objects.filter(
            pk__in=common.member_lab_ids(caller), memberships__user=user
        ).distinct()
    )
    own = caller.user is not None and user.pk == caller.user.pk
    if shared(caller) and not own:
        here = audience_lab(caller)
        if (
            here is None
            or not LabMembership.objects.filter(user=user, lab=here).exists()
        ):
            raise _not_here("Someone outside this lab")
        labs = [lab for lab in labs if lab.pk == here.pk]
    info = common.person_info(user, caller=caller)
    refs = [info]
    lines = [f"{{ref:{info.ref}}} {_name(user)} (@{user.username})"]
    if labs:
        parts = []
        for lab in labs:
            li = common.lab_info(lab)
            refs.append(li)
            parts.append(f"{{ref:{li.ref}}} {lab.name}")
        lines.append("Labs in common: " + "; ".join(parts))
    else:
        lines.append("Labs in common: none")
    profile = getattr(user, "profile", None)
    labels = interest_labels(getattr(profile, "interests", None))
    lines.append("Declared interests: " + (", ".join(labels[:12]) or "(none declared)"))
    lines.append("Only what they declared is shown; ask them for more.")
    return Result(content="\n".join(lines), refs=refs)

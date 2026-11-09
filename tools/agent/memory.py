"""What Mylo knows about who it is talking to.

* ``profile_block(caller)``: in every system prompt. Built only from stored,
  confirmed state (declared interests, confirmed understanding, confirmed
  conversational edges, projects with attention, labs and departments), with
  no "now" in it, so it changes only when memory does and the prefix cache
  holds. In a project thread that project's block comes first. Capped at
  3 000 characters, the project's part at 1 500.
* ``scope_block(caller)``: where the thread lives (project goals and state,
  lab profile), audience-filtered.
* ``recall(caller, thread, event)``: per message, see ``recall.py``.

In a reply seen by more than the caller (a lab channel), personal facts are
left out entirely: a model that has seen something can repeat it.
"""

from __future__ import annotations

from tools._framework.agentspec import width_rank

PROFILE_CAP = 3000
PROJECT_CAP = 1500


def _since(dt) -> str:
    return f" (since {dt:%Y-%m})" if dt else ""


def _clip(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    cut = text[:cap].rsplit("\n", 1)[0]
    return cut + "\n…"


def _interest_lines(user) -> list[str]:
    from tools.recommendation import understanding

    profile = getattr(user, "profile", None)
    interests = dict(getattr(profile, "interests", None) or {})
    out = []
    if understanding.lines(interests):
        out += understanding.lines(interests)
    clusters = interests.get("clusters") or []
    if clusters:
        out.append(
            "Declared interests: "
            + "; ".join(
                f"{c.get('label')} ({', '.join(c.get('areas', [])[:6])})"
                for c in clusters
                if isinstance(c, dict)
            )
        )
    elif interests.get("areas"):
        out.append("Declared interests: " + ", ".join(interests["areas"][:12]))
    return out


def _edge_lines(user) -> list[str]:
    from apps.knowledge import read as kread

    edges = [
        e
        for e in kread.own_edges(user)
        if e.tier == "conversational" and e.status == "confirmed"
    ]
    if not edges:
        return []
    edges.sort(key=lambda e: e.first_seen)
    return [
        "Confirmed in conversation: "
        + "; ".join(
            f"{e.relation.replace('_', ' ')} {e.label}{_since(e.first_seen)}"
            for e in edges[:12]
        )
    ]


def _org_lines(user) -> list[str]:
    from apps.accounts.models import DeptMembership, LabMembership

    out = []
    labs = (
        LabMembership.objects.filter(user=user)
        .select_related("lab")
        .order_by("lab__name")
    )
    if labs:
        out.append(
            "Labs: "
            + "; ".join(
                f"{m.lab.name} [{m.lab.slug}] as {m.role}{' (PI)' if m.is_lead else ''}"
                f"{_since(m.created_at)}"
                for m in labs
            )
        )
    depts = DeptMembership.objects.filter(user=user).select_related("department")
    owned = (
        list(user.owned_departments.all()) if hasattr(user, "owned_departments") else []
    )
    names = [f"{d.name} as owner" for d in owned]
    names += [
        f"{m.department.name} as {m.role}"
        for m in depts
        if m.department_id not in {d.pk for d in owned}
    ]
    if names:
        out.append("Departments: " + "; ".join(names))
    return out


def _project_lines(user) -> list[str]:
    from apps.ambient.read import attention_for
    from apps.research.models import Project

    projects = list(
        Project.objects.visible_to(user)
        .filter(is_archived=False, members=user)
        .order_by("name")[:12]
    )
    if not projects:
        return []
    attention = {}
    for row in attention_for(user):
        attention[str(row.project_id)] = row
    parts = []
    for p in projects:
        att = attention.get(str(p.pk))
        share = ""
        if att is not None:
            s7 = getattr(att, "share_7d", None)
            s28 = getattr(att, "share_28d", None)
            if s7 is not None or s28 is not None:
                week, month = round((s7 or 0) * 100), round((s28 or 0) * 100)
                share = f", attention 7d {week}% / 28d {month}%"
        parts.append(f"{p.name} [{p.scope}{share}]")
    return ["Their projects: " + "; ".join(parts)]


def project_block(project, *, reader) -> str:
    """Name, goals, aliases, confirmed state and developments in effect."""
    from apps.ambient.read import developments_in_effect

    lines = [f"Project: {project.name} (scope: {project.scope})"]
    goals = project.goals or {}
    if isinstance(goals, dict):
        for key in ("summary", "goals", "methods", "datasets", "deadlines", "needs"):
            value = goals.get(key)
            if value:
                text = value if isinstance(value, str) else "; ".join(map(str, value))
                lines.append(f"{key.title()}: {text}")
    if project.aliases:
        lines.append("Also called: " + ", ".join(map(str, project.aliases)))
    from apps.research.models import ProjectState

    state = ProjectState.objects.filter(project=project).first()
    if state is not None and state.state_version:
        slow, fast = state.slow or {}, state.fast or {}
        for key in ("problem", "claimed_contribution", "method"):
            if slow.get(key):
                lines.append(f"{key.replace('_', ' ').title()}: {slow[key]}")
        blockers = slow.get("blockers") or []
        if blockers:
            lines.append(
                "Blockers: "
                + "; ".join(
                    b.get("text", str(b)) if isinstance(b, dict) else str(b)
                    for b in blockers
                )
            )
        if fast.get("stage"):
            lines.append(f"Stage: {fast['stage']}")
        milestones = fast.get("milestones") or []
        if milestones:
            lines.append(
                "Milestones: "
                + "; ".join(
                    f"{m.get('text', m.get('name', ''))} ({m.get('due', '')})"
                    if isinstance(m, dict)
                    else str(m)
                    for m in milestones[:6]
                )
            )
        if state.confirmed_at:
            lines.append(f"State last confirmed {state.confirmed_at:%Y-%m-%d}.")
    devs = list(developments_in_effect(project, reader=reader)[:8])
    if devs:
        lines.append(
            "Developments in effect: "
            + "; ".join(f"{d.change}: {d.topic}" for d in devs)
        )
    members = list(project.members.all()[:12])
    if members:
        lines.append(
            "Members: " + ", ".join(m.get_full_name() or m.username for m in members)
        )
    return _clip("\n".join(lines), PROJECT_CAP)


def lab_block(lab) -> str:
    lines = [f"Lab: {lab.name} [{lab.slug}]"]
    profile = getattr(lab, "profile", None)
    interests = dict(getattr(profile, "interests", None) or {}) if profile else {}
    clusters = interests.get("clusters") or []
    if clusters:
        lines.append(
            "Lab interests: "
            + "; ".join(str(c.get("label")) for c in clusters if isinstance(c, dict))
        )
    count = lab.memberships.count()
    lines.append(f"Members: {count}")
    return "\n".join(lines)


def profile_block(caller) -> str:
    if width_rank(caller.audience.width) > width_rank("person"):
        # Seen by others: nothing personal goes in.
        return ""
    user = caller.user
    name = user.get_full_name() or user.username
    head = f"You are talking to {name} (@{user.username})."
    lines = [head]
    lines += _interest_lines(user)
    lines += _edge_lines(user)
    lines += _org_lines(user)
    lines += _project_lines(user)
    body = _clip("\n".join(lines), PROFILE_CAP)
    return "Who you are talking to:\n" + body


def scope_block(caller) -> str:
    scope = caller.scope
    if scope.kind == "personal" or scope.obj is None:
        return "This is a personal conversation, not tied to a project or lab."
    if scope.kind == "project":
        return (
            "This conversation belongs to a project; questions are about it unless "
            "the person says otherwise.\n"
            + project_block(scope.obj, reader=caller.user)
        )
    if scope.kind == "lab":
        return "This conversation belongs to a lab.\n" + lab_block(scope.obj)
    return f"This conversation belongs to the department {scope.obj.name}."


def profile_version(caller) -> str:
    """The cache key of the profile block: it changes only when memory does."""
    from tools.recommendation import understanding

    projects = [caller.scope.obj] if caller.scope.kind == "project" else []
    return understanding.context_version(user=caller.user, projects=projects)

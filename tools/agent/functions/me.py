"""The ``me`` group: the caller's own profile, interests and what Mylo has
understood about them. Personal output: never offered where others read."""

from __future__ import annotations

from tools._framework.agentspec import Result

from . import common


def me_profile(caller):
    from apps.accounts.models import LabMembership
    from apps.research.models import Project

    from .. import memory

    user = caller.user
    profile = getattr(user, "profile", None)
    lines = [
        f"Name: {user.get_full_name() or '(not set)'}",
        f"Username: @{user.username}",
    ]
    for attr in ("academic_title", "institution", "career_stage", "orcid"):
        value = getattr(profile, attr, "") if profile else ""
        if value:
            lines.append(f"{attr.replace('_', ' ').title()}: {value}")
    lines += memory._org_lines(user)
    lines += memory._project_lines(user)
    # The same labs and projects once more, one to a line with a reference, so
    # an answer that names one can cite it.
    refs = []
    labs = (
        LabMembership.objects.filter(user=user)
        .select_related("lab")
        .order_by("lab__name")
    )
    if labs:
        lines.append("Your labs, by reference:")
        for m in labs:
            info = common.lab_info(m.lab)
            refs.append(info)
            lines.append(f"- {{ref:{info.ref}}} {m.lab.name}")
    projects = list(
        Project.objects.visible_to(user)
        .filter(is_archived=False, members=user)
        .order_by("name")[:12]
    )
    if projects:
        lines.append("Your projects, by reference:")
        for project in projects:
            info = common.project_info(project)
            refs.append(info)
            lines.append(f"- {{ref:{info.ref}}} {project.name}")
    return Result(content="\n".join(lines), refs=refs)


def me_interests(caller):
    profile = getattr(caller.user, "profile", None)
    interests = dict(getattr(profile, "interests", None) or {})
    lines = []
    for c in interests.get("clusters") or []:
        if isinstance(c, dict):
            lines.append(f"- {c.get('label')}: {', '.join(c.get('areas', []))}")
    if not lines and interests.get("areas"):
        lines.append("- " + ", ".join(interests["areas"]))
    watch = getattr(caller.user, "watch", None)
    topics = list(getattr(watch, "topics", None) or []) if watch else []
    out = "Declared interest clusters:\n" + ("\n".join(lines) or "(none yet)")
    if topics:
        out += "\nWatch topics: " + ", ".join(map(str, topics))
    out += "\nThe person edits these in the app (Profile → Interests)."
    return Result(content=out)


def me_understanding(caller):
    from apps.ambient.read import observations_for
    from apps.knowledge import read as kread

    from tools.recommendation import understanding

    profile = getattr(caller.user, "profile", None)
    interests = dict(getattr(profile, "interests", None) or {})
    lines = ["Confirmed (the person said yes, or typed it):"]
    lines += [f"- {line}" for line in understanding.lines(interests)] or [
        "- (nothing yet)"
    ]
    edges = [e for e in kread.own_edges(caller.user) if e.tier == "conversational"]
    confirmed = [e for e in edges if e.status == "confirmed"]
    if confirmed:
        lines.append("Confirmed in conversation:")
        lines += [
            f"- {e.relation.replace('_', ' ')} {e.label} (since {e.first_seen:%Y-%m})"
            for e in confirmed[:20]
        ]
    pending = list(observations_for(caller.user)[:15])
    lines.append("Noticed but not confirmed (evidence only; changes nothing yet):")
    lines += [
        f"- {common.clip(o.text, 160)} ({o.observed_at:%Y-%m-%d})" for o in pending
    ] or ["- (nothing pending)"]
    lines.append(
        "The person reviews and corrects all of this in the app under "
        "“Mylo & you”; you cannot change it."
    )
    return Result(content="\n".join(lines))

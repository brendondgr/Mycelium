"""The ``projects`` group: the projects a person can see, one project's state,
and its current feed. Loaded by default in a project thread.

Mixed output: in a reply seen by a lab, only lab-shared projects appear and a
project's personal developments are left out — filtered here, before the
model reads anything.
"""

from __future__ import annotations

from tools._framework.agentspec import FunctionError, Result

from . import common


def _visible_projects(caller):
    from .kinds import visible_projects

    rows = visible_projects(caller).filter(is_archived=False)
    scope = caller.scope
    if scope.kind == "lab":
        rows = rows.filter(scope_lab=scope.obj)
    elif scope.kind == "department":
        rows = rows.filter(scope_department=scope.obj)
    elif scope.kind == "project":
        rows = rows.filter(pk=scope.obj.pk)
    return [
        p
        for p in rows.order_by("name")
        if common.audience_allows(caller, common.project_output(p))
    ]


def _check_audience(caller, project) -> None:
    """A project taken from the thread's scope skipped the gate's object
    check; hold it to the same audience rule here."""
    if not common.audience_allows(caller, common.project_output(project)):
        raise FunctionError(
            "audience",
            "This project can't be shown to everyone who will read this.",
            "Ask me in a DM.",
        )


def _project(caller, ref):
    from apps.research.models import Project

    if not ref:
        if caller.scope.kind == "project":
            return caller.scope.obj
        raise FunctionError(
            "need_project",
            "Which project?",
            "Pass project='#n' or call projects_list first.",
        )
    project = Project.objects.filter(pk=common.ref_key(ref)).first()
    if project is None:  # the gate already cleared it; this is a race
        raise FunctionError("not_visible", "That project is not available.")
    return project


def projects_list(caller):
    rows = _visible_projects(caller)
    if not rows:
        return Result(content="No projects visible here.")
    refs, lines = [], []
    for p in rows:
        info = common.project_info(p)
        refs.append(info)
        members = p.members.count()
        lines.append(
            f"- {{ref:{info.ref}}} {p.name} — {p.scope} project, {members} members"
        )
    return Result(content="Projects:\n" + "\n".join(lines), refs=refs)


def projects_get(caller, project=None):
    from apps.ambient.read import developments_in_effect

    from .. import memory

    p = _project(caller, project)
    _check_audience(caller, p)
    personal_ok = (
        common.audience_allows(caller, "person") and caller.audience.width == "person"
    )
    text = memory.project_block(p, reader=caller.user if personal_ok else None)
    if not personal_ok:
        lab_only = [d for d in developments_in_effect(p) if d.visibility == "lab"]
        text = "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith("Developments in effect")
        )
        if lab_only:
            text += "\nDevelopments in effect: " + "; ".join(
                f"{d.change}: {d.topic}" for d in lab_only[:8]
            )
    info = common.project_info(p)
    return Result(content=f"{{ref:{info.ref}}}\n{text}", refs=[info])


def _slate(target_kwargs: dict, types, limit: int):
    from tools.recommendation.read import RelevanceScore, order_by_slate

    rows = RelevanceScore.objects.filter(
        **target_kwargs, content__type__in=types
    ).select_related("content")
    return order_by_slate(rows)[:limit]


def slate_lines(rows, *, since_label: str = ""):
    refs, lines = [], []
    for score in rows:
        item = score.content
        info = common.item_info(item)
        refs.append(info)
        sig = score.signals or {}
        why = sig.get("headline") or sig.get("reason") or sig.get("verdict") or ""
        new = " (new)" if sig.get("entered_top_on") and sig.get("is_new_top") else ""
        entered = sig.get("entered_top_on")
        when = f", in slate since {entered}" if entered else ""
        lines.append(
            f"- {{ref:{info.ref}}} {common.item_title(item)} [{item.type}{when}]{new}"
            + (f" — {common.clip(why, 200)}" if why else "")
        )
    return refs, lines


def projects_feed(caller, project=None, types=None, limit=10):
    p = _project(caller, project)
    _check_audience(caller, p)
    types = [
        t
        for t in (types or ["paper", "grant", "fellowship", "conference"])
        if t in ("paper", "grant", "fellowship", "conference")
    ]
    limit = max(1, min(int(limit or 10), 25))
    rows = _slate({"target_project": p}, types, limit)
    if not rows:
        return Result(
            content=f"{p.name} has nothing in its current slate yet "
            "(the nightly run fills it)."
        )
    refs, lines = slate_lines(rows)
    head = common.project_info(p)
    return Result(
        content=f"Current slate of {{ref:{head.ref}}} {p.name}, in rank order:\n"
        + "\n".join(lines),
        refs=[head, *refs],
    )

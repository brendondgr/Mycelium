"""The ``projects`` group: the projects a person can see, one project's state,
and its current feed. Loaded by default in a project thread.

Mixed output: in a reply seen by a lab, only lab-shared projects appear and a
project's personal developments are left out — filtered here, before the
model reads anything.
"""

from __future__ import annotations

from tools._framework.agentspec import FunctionError, Result

from . import common, lists


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
    from django.core.exceptions import ValidationError

    if not ref:
        if caller.scope.kind == "project":
            return caller.scope.obj
        raise FunctionError(
            "need_project",
            "Which project?",
            "Pass project='#n' or call projects_list first.",
        )
    try:
        project = Project.objects.filter(pk=common.ref_key(ref)).first()
    except (ValueError, ValidationError):  # not an id: never an internal error (Q-069)
        project = None
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
    text = memory.project_block(
        p, reader=caller.user if personal_ok else None, cap=memory.PROJECT_READ_CAP
    )
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
    # Members one to a line, each with a reference, so an answer that names a
    # member can cite them; the block's own line gives names only.
    people, member_lines = common.people_lines(caller, p.members.all()[:12])
    if member_lines:
        text = "\n".join(
            line for line in text.splitlines() if not line.startswith("Members: ")
        )
        text += "\nMembers:\n" + "\n".join(f"- {line}" for line in member_lines)
    return Result(content=f"{{ref:{info.ref}}} {p.name}\n{text}", refs=[info, *people])


def _slate(target_kwargs: dict, types, limit=None):
    """A target's slate in rank order, cut to ``limit``. The reader itself is
    :func:`lists.slate`; this name stays because the evaluation harnesses
    build their gold answers with it (``EXP-2026-11-018``)."""
    return lists.slate(target_kwargs, types)[:limit]


#: Kept importable from here for the same reason.
slate_lines = lists.slate_lines


def projects_feed(
    caller,
    project=None,
    types=None,
    limit=None,
    offset=None,
    due_from=None,
    due_to=None,
    deadline=None,
):
    p = _project(caller, project)
    _check_audience(caller, p)
    head = common.project_info(p)
    return lists.slate_view(
        {"target_project": p},
        title=f"{{ref:{head.ref}}} {p.name}",
        head=head,
        types=types,
        limit=limit,
        offset=offset,
        due_from=due_from,
        due_to=due_to,
        deadline=deadline,
        default_limit=10,
    )

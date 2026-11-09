"""Shared helpers for the agent's own functions: object → reference, and the
small text shapes results use. A result names each object it surfaces as
``{ref:kind:key}``; dispatch replaces that with the thread's ``#n``."""

from __future__ import annotations

from tools._framework.agentspec import FunctionError, RefInfo, width_rank


def item_title(item) -> str:
    meta = item.metadata or {}
    return str(meta.get("title") or meta.get("name") or item.external_id or item.pk)[
        :200
    ]


def item_info(item) -> RefInfo:
    meta = item.metadata or {}
    bits = [item.type]
    for key in ("venue", "sponsor", "agency", "year", "published", "deadline"):
        if meta.get(key):
            bits.append(str(meta[key])[:60])
    read = "corpus_item(item='{ref}')"
    return RefInfo(
        kind="item",
        key=str(item.pk),
        title=f"[{item.type}] {item_title(item)}",
        card=" · ".join(bits),
        output="instance",
        read_with=read,
        untrusted=True,
    )


def project_output(project) -> str:
    if project.scope_user_id is not None:
        return "person"
    if project.scope_lab_id is not None and project.share_in_lab_reports:
        return "lab"
    return "project"


def project_info(project) -> RefInfo:
    return RefInfo(
        kind="project",
        key=str(project.pk),
        title=project.name,
        card=f"{project.scope} project"
        + (" (archived)" if project.is_archived else ""),
        output=project_output(project),
        read_with="projects_get(project='{ref}')",
    )


def lab_info(lab) -> RefInfo:
    return RefInfo(
        kind="lab",
        key=lab.slug,
        title=lab.name,
        card=f"lab [{lab.slug}]",
        output="lab",
        read_with="org_lab(lab='{ref}')",
    )


def department_info(dept) -> RefInfo:
    return RefInfo(
        kind="department",
        key=str(dept.pk),
        title=dept.name,
        card="department",
        output="department",
        read_with="org_department(department='{ref}')",
    )


def place_lab_ids(caller) -> set:
    """The labs a guest stands in: the place's lab, or a department place's
    labs. Empty for anyone with an account (they stand in their own)."""
    from apps.accounts.models import Lab

    if not getattr(caller, "is_guest", False):
        return set()
    scope = caller.scope
    if scope.kind == "lab" and scope.obj is not None:
        return {scope.obj.pk}
    if scope.kind == "department" and scope.obj is not None:
        return set(
            Lab.objects.filter(department=scope.obj).values_list("pk", flat=True)
        )
    return set()


def member_lab_ids(caller):
    """The labs the caller counts as a member of (a guest: the place's)."""
    from apps.accounts.models import LabMembership

    if caller.user is None:
        return place_lab_ids(caller)
    return set(
        LabMembership.objects.filter(user=caller.user).values_list("lab_id", flat=True)
    )


def person_info(user, *, caller) -> RefInfo:
    """Another person is shown to a lab audience only if they share a lab
    with the caller; someone seen through a department or a project only is
    shown to the caller alone. A guest shares the place's lab."""
    from apps.accounts.models import LabMembership

    name = user.get_full_name() or user.username
    own = caller.user is not None and user.pk == caller.user.pk
    shares_lab = (
        not own
        and LabMembership.objects.filter(
            user=user, lab_id__in=member_lab_ids(caller)
        ).exists()
    )
    return RefInfo(
        kind="person",
        key=user.username,
        title=f"{name} (@{user.username})",
        card="you" if own else "",
        output="lab" if shares_lab else "person",
        read_with="org_person(person='{ref}')",
    )


def ref_key(token: str) -> str:
    """``kind:key`` (as dispatch passes cleared references) → ``key``."""
    return str(token).split(":", 1)[1] if ":" in str(token) else str(token)


def audience_allows(caller, width: str) -> bool:
    return width_rank(width) >= width_rank(caller.audience.width)


def need_thread(caller):
    thread = caller.thread
    if thread is None:
        raise FunctionError("no_thread", "This needs a conversation.", "")
    return thread


def clip(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def schema(properties: dict | None = None, required=()) -> dict:
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
    }


def ref_param(kind: str, description: str) -> dict:
    return {"type": "string", "description": description, "x-ref": kind}

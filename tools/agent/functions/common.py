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


def item_amount(item) -> tuple[float | None, str, str]:
    """``(the most it pays, currency code, the amount as its source states
    it)`` for a grant or fellowship. The number is ``None`` when the source
    states none ("Varies", "Stipend + tuition"); all three are empty for an
    item that states no amount at all."""
    meta = item.metadata or {}
    if item.type == "fellowship":
        low, top = meta.get("amount_min"), meta.get("amount_max")
        code, text = meta.get("amount_currency"), meta.get("amount_raw")
    elif item.type == "grant":
        low, top = meta.get("award_floor"), meta.get("award_ceiling")
        code, text = meta.get("currency"), meta.get("amount")
    else:
        return None, "", ""
    most = top if top is not None else low
    try:
        most = None if most is None else float(most)
    except (TypeError, ValueError):
        most = None
    text = clip(text or "", 60)
    if most is None and not text:
        return None, "", ""
    return most, str(code or "").upper() if most is not None else "", text


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
    """The widest agent audience a project may be shown to, from its scope."""
    from apps.research import visibility

    return visibility.output_width(project)


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


def people_lines(caller, users) -> tuple[list, list[str]]:
    """``(refs, lines)``: one line per person, carrying their reference number
    wherever the caller may open that person (so a name in an answer can be
    cited), and the bare name otherwise. A guest gets names only, as before."""
    from .kinds import visible_people_for

    users = list(users)
    if not users:
        return [], []
    seen = set()
    if not getattr(caller, "is_guest", False):
        seen = set(
            visible_people_for(caller)
            .filter(pk__in=[u.pk for u in users])
            .values_list("pk", flat=True)
        )
        if caller.user is not None:
            seen.add(caller.user.pk)
    refs, lines = [], []
    for user in users:
        name = user.get_full_name() or user.username
        info = person_info(user, caller=caller) if user.pk in seen else None
        if info is not None and audience_allows(caller, info.output):
            refs.append(info)
            lines.append(f"{{ref:{info.ref}}} {name} (@{user.username})")
        else:
            lines.append(name)
    return refs, lines


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


def save_setting(thread, key: str, change):
    """One key of the thread's settings, changed under the row's lock
    (:func:`tools.agent.store.save_setting`)."""
    from .. import store

    return store.save_setting(thread, key, change)


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

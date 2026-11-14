"""The ``feeds`` group: the current slates, the latest report, saves and the
deadlines coming up across them.

Mixed output: ``feeds_slate``, ``feeds_briefing`` and ``feeds_deadlines`` are
declared ``lab`` wide, and decide per call what the audience may see. In a
reply others read, the person's own slate, report and personal saves are left
out (or refused) and only the audience's own lab, and lab-shared projects in
it, are read — filtered here, before the model reads anything.
"""

from __future__ import annotations

from datetime import timedelta

from tools._framework.agentspec import FunctionError, Result

from . import common
from .org import audience_lab_ok, lab_arg, shared
from .projects import _project, _slate, slate_lines

TYPES = ("paper", "grant", "fellowship", "conference")
DATED = ("grant", "fellowship", "conference")


def _types(types, allowed=TYPES) -> list[str]:
    return [t for t in (types or allowed) if t in allowed] or list(allowed)


def _limit(limit, default: int, top: int) -> int:
    try:
        return max(1, min(int(limit or default), top))
    except (TypeError, ValueError):
        return default


def _project_ok(caller, p) -> None:
    """A project's rows, only where its own width reaches the audience."""
    if not common.audience_allows(caller, common.project_output(p)):
        raise FunctionError(
            "audience",
            f"{p.name} isn't shared with everyone who will read this.",
            "Ask me in a DM.",
        )
    if shared(caller) and p.scope_lab_id is not None:
        audience_lab_ok(caller, p.scope_lab)


def _target(caller, lab=None, project=None):
    """``(persist kwargs, label, head RefInfo or None)`` for the slate asked for."""
    if project:
        p = _project(caller, project)
        _project_ok(caller, p)
        return {"target_project": p}, p.name, common.project_info(p)
    if lab:
        row = lab_arg(caller, lab)
        audience_lab_ok(caller, row)
        return {"target_lab": row}, row.name, common.lab_info(row)
    scope = caller.scope
    if scope.kind == "project":
        p = scope.obj
        _project_ok(caller, p)
        return {"target_project": p}, p.name, common.project_info(p)
    if scope.kind == "lab":
        return {"target_lab": scope.obj}, scope.obj.name, common.lab_info(scope.obj)
    if scope.kind == "department":
        return (
            {"target_department": scope.obj},
            scope.obj.name,
            common.department_info(scope.obj),
        )
    if shared(caller):
        raise FunctionError(
            "audience",
            "Your own feed isn't shown where others read.",
            "Ask me in a DM, or name the lab.",
        )
    return {"target_user": caller.user}, "your feed", None


def _fit_usernames(score) -> list[str]:
    fits = (score.signals or {}).get("member_fit") or []
    return [f["username"] for f in fits if isinstance(f, dict) and f.get("username")]


def _display_names(rows) -> dict[str, str]:
    """Full names for the members named in these rows' ``member_fit``. Mylo
    repeats what it reads, so a bare ``@demo.tomas`` here reached answers."""
    from django.contrib.auth import get_user_model

    usernames = {u for s in rows for u in _fit_usernames(s)}
    if not usernames:
        return {}
    users = get_user_model().objects.filter(username__in=usernames)
    return {u.username: u.get_full_name() or f"@{u.username}" for u in users}


def _who_should_look(score, names: dict[str, str]) -> str:
    shown = [names.get(u, f"@{u}") for u in _fit_usernames(score)]
    return f" · who should look: {', '.join(shown[:4])}" if shown else ""


def feeds_slate(caller, lab=None, project=None, types=None, limit=8):
    kwargs, label, head = _target(caller, lab, project)
    limit = _limit(limit, 8, 25)
    refs = [head] if head else []
    sections = []
    for t in _types(types):
        rows = _slate(kwargs, [t], limit)
        if not rows:
            continue
        item_refs, lines = slate_lines(rows)
        if "target_user" not in kwargs:
            names = _display_names(rows)
            lines = [
                line + _who_should_look(s, names)
                for line, s in zip(lines, rows, strict=True)
            ]
        refs += item_refs
        sections.append(f"{t.title()}s (rank order):\n" + "\n".join(lines))
    title = f"{{ref:{head.ref}}} {label}" if head else label.capitalize()
    if not sections:
        return Result(
            content=f"{title}: nothing in the current slate yet "
            "(the nightly run fills it).",
            refs=refs,
        )
    return Result(
        content=f"Current slate of {title}:\n" + "\n\n".join(sections), refs=refs
    )


def feeds_briefing(caller, kind="daily", lab=None):
    from tools.delivery.read import DailyBriefing

    kind = "weekly" if kind == "weekly" else "daily"
    if lab or (shared(caller) and caller.scope.lab is not None):
        row_lab = lab_arg(caller, lab)
        audience_lab_ok(caller, row_lab)
        row = DailyBriefing.latest_for(kind, lab=row_lab)
        info = common.lab_info(row_lab)
        whose, refs = f"{{ref:{info.ref}}} {row_lab.name}'s", [info]
    elif shared(caller):
        raise FunctionError(
            "audience",
            "Your own report isn't shown where others read.",
            "Ask me in a DM.",
        )
    else:
        row = DailyBriefing.latest_for(kind, user=caller.user)
        whose, refs = "Your", []
    if row is None:
        return Result(
            content=f"{whose} {kind} report has not been written yet.", refs=refs
        )
    lines = [
        f"{whose} latest {kind} report, {row.generated_on:%Y-%m-%d}"
        + (" (carried forward: nothing new entered)" if row.origin == "carried" else "")
    ]
    if row.new_counts:
        lines.append(
            "New in the Top-25: "
            + ", ".join(f"{k} {v}" for k, v in sorted(row.new_counts.items()))
        )
    if row.counts:
        lines.append(
            "Matched: " + ", ".join(f"{k} {v}" for k, v in sorted(row.counts.items()))
        )
    body = (row.body or "").strip()
    lead = (row.narrative or {}).get("lead") if isinstance(row.narrative, dict) else ""
    lines.append("Report:\n" + (body[:6000] if body else (lead or "(no prose)")))
    return Result(content="\n".join(lines), refs=refs, untrusted=True)


def _save_line(save, refs) -> str:
    when = f", due {save.deadline_date:%Y-%m-%d}" if save.deadline_date else ""
    note = f" — note: {common.clip(save.note, 160)}" if save.note else ""
    if save.content_id and save.content is not None:
        info = common.item_info(save.content)
        refs.append(info)
        title = common.clip(save.title, 160)
        return f"- {{ref:{info.ref}}} [{save.area}] {title}{when}{note}"
    title = common.clip(save.title, 160)
    return f"- [{save.area}] {title}{when} (no longer in the corpus){note}"


def feeds_saved(caller, types=None, limit=20):
    from tools.delivery.read import SavedOpportunity

    types = _types(types)
    limit = _limit(limit, 20, 50)
    refs, out = [], []
    mine = (
        SavedOpportunity.objects.filter(
            user=caller.user, target_lab__isnull=True, area__in=types
        )
        .select_related("content")
        .order_by("deadline_date", "-created_at")[:limit]
    )
    out.append(
        "Your saves:\n" + ("\n".join(_save_line(s, refs) for s in mine) or "(none)")
    )
    lab = caller.scope.lab
    if lab is not None:
        rows = (
            SavedOpportunity.objects.filter(target_lab=lab, area__in=types)
            .select_related("content")
            .order_by("deadline_date", "-created_at")[:limit]
        )
        out.append(
            f"{lab.name}'s saves:\n"
            + ("\n".join(_save_line(s, refs) for s in rows) or "(none)")
        )
    return Result(content="\n\n".join(out), refs=refs)


def _slate_ids(kwargs: dict) -> set:
    from tools.recommendation.read import RelevanceScore, in_slate

    rows = RelevanceScore.objects.filter(**kwargs, content__type__in=DATED).only(
        "content_id", "signals"
    )
    return {r.content_id for r in rows if in_slate(r.signals or {})}


def feeds_deadlines(caller, days=60, limit=20):
    from django.utils import timezone

    from tools.delivery.read import SavedOpportunity
    from tools.retrieval.read import ContentDeadline

    days = _limit(days, 60, 366)
    limit = _limit(limit, 20, 50)
    today = timezone.localdate()
    until = today + timedelta(days=days)
    origin: dict = {}  # content id -> where it came from

    def add(ids, label):
        for cid in ids:
            origin.setdefault(cid, label)

    loose = []  # personal saves whose item has left the corpus: the snapshot date
    lab = caller.scope.lab
    if not shared(caller):
        mine = SavedOpportunity.objects.filter(
            user=caller.user, target_lab__isnull=True
        )
        add(
            mine.filter(content__isnull=False).values_list("content_id", flat=True),
            "your saves",
        )
        loose = list(
            mine.filter(
                content__isnull=True, deadline_date__gte=today, deadline_date__lte=until
            )
        )
        add(_slate_ids({"target_user": caller.user}), "your feed")
    else:
        from .org import audience_lab

        lab = audience_lab(caller)
    if lab is not None:
        add(
            SavedOpportunity.objects.filter(
                target_lab=lab, content__isnull=False
            ).values_list("content_id", flat=True),
            f"{lab.name}'s saves",
        )
        add(_slate_ids({"target_lab": lab}), f"{lab.name}'s feed")
    p = caller.scope.project
    if p is not None and common.audience_allows(caller, common.project_output(p)):
        add(_slate_ids({"target_project": p}), f"{p.name}'s feed")
    rows = (
        ContentDeadline.objects.filter(
            content_id__in=list(origin), due_date__gte=today, due_date__lte=until
        )
        .select_related("content")
        .order_by("due_date", "kind")[:limit]
    )
    refs, lines = [], []
    for d in rows:
        info = common.item_info(d.content)
        refs.append(info)
        what = d.get_kind_display().lower() + (
            f" ({d.round_label})" if d.round_label else ""
        )
        sure = "" if d.confidence == "confirmed" else f", {d.confidence}"
        lines.append(
            f"- {d.due_date:%Y-%m-%d} (in {(d.due_date - today).days} days) "
            f"{{ref:{info.ref}}} {common.item_title(d.content)} — {what}{sure}; "
            f"from {origin[d.content_id]}"
        )
    for s in loose:
        lines.append(
            f"- {s.deadline_date:%Y-%m-%d} (in {(s.deadline_date - today).days} days) "
            f"{common.clip(s.title, 160)} — saved date (item left the corpus); "
            "from your saves"
        )
    if not lines:
        return Result(
            content=f"No deadlines in the next {days} days among the saved and "
            "slate items read here."
        )
    return Result(
        content=f"Deadlines in the next {days} days:\n" + "\n".join(lines), refs=refs
    )

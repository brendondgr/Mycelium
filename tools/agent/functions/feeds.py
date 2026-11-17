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

from . import common, lists
from .org import audience_lab_ok, lab_arg, shared
from .projects import _project

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


def _who_should_look(caller, rows, people: list) -> list[str]:
    """Per row, ``" · who should look: #4 Ana Ruiz, …"`` for the members the
    nightly ranking named, each with a reference where the caller may open
    them (appended to ``people``), so an answer that names one can cite them.
    Mylo repeats what it reads, so a bare ``@demo.tomas`` here reached answers."""
    from django.contrib.auth import get_user_model

    usernames = {u for s in rows for u in _fit_usernames(s)}
    if not usernames:
        return ["" for _ in rows]
    users = {
        u.username: u for u in get_user_model().objects.filter(username__in=usernames)
    }
    refs, lines = common.people_lines(caller, users.values())
    shown = {}
    for user, line in zip(users.values(), lines, strict=True):
        # In a slate line the name is enough; the username stays in the card.
        shown[user.username] = line.rsplit(" (@", 1)[0]
    used = set()
    out = []
    for s in rows:
        names = _fit_usernames(s)[:4]
        used.update(names)
        text = ", ".join(shown.get(u, f"@{u}") for u in names)
        out.append(f" · who should look: {text}" if text else "")
    for info in refs:
        if info.key in used and info not in people:
            people.append(info)
    return out


def feeds_slate(
    caller,
    lab=None,
    project=None,
    types=None,
    limit=None,
    offset=None,
    due_from=None,
    due_to=None,
    deadline=None,
):
    kwargs, label, head = _target(caller, lab, project)

    people: list = []

    def who(lines, rows):
        tails = _who_should_look(caller, rows, people)
        return [line + tail for line, tail in zip(lines, tails, strict=True)]

    return lists.slate_view(
        kwargs,
        title=f"{{ref:{head.ref}}} {label}" if head else label,
        head=head,
        types=types,
        limit=limit,
        offset=offset,
        due_from=due_from,
        due_to=due_to,
        deadline=deadline,
        default_limit=8,
        decorate=None if "target_user" in kwargs else who,
        more_refs=people,
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


def feeds_saved(
    caller, types=None, limit=None, offset=None, due_from=None, due_to=None
):
    from tools.delivery.read import SavedOpportunity

    types = _types(types)
    limit = _limit(limit, 20, 50)
    start = lists.int_arg(offset, 0, 0, 10**6)
    lo, hi = lists.date_arg(due_from, "due_from"), lists.date_arg(due_to, "due_to")
    asked = ""
    if lo or hi:
        asked = " due " + (
            lists.window_text(lo, hi) if lo else f"up to {hi:%Y-%m-%d}"
        )

    def section(whose, rows_all):
        if lo:
            rows_all = rows_all.filter(deadline_date__gte=lo)
        if hi:
            rows_all = rows_all.filter(deadline_date__lte=hi)
        total = rows_all.count()
        rows = list(
            rows_all.select_related("content").order_by("deadline_date", "-created_at")[
                start : start + limit
            ]
        )
        found = []
        for save in rows:
            own: list = []
            found.append((_save_line(save, own), own))
        lines = [line for line, _ in found]
        keep = lists.fit(lines, lists.budget() // 2)
        for _, own in found[:keep]:
            refs.extend(own)
        return (
            f"{whose}{asked}:\n"
            + ("\n".join(lines[:keep]) or "(none)")
            + "\n"
            + lists.closing(start, keep, total, "saves")
        )

    refs, out = [], []
    out.append(
        section(
            "Your saves",
            SavedOpportunity.objects.filter(
                user=caller.user, target_lab__isnull=True, area__in=types
            ),
        )
    )
    lab = caller.scope.lab
    if lab is not None:
        out.append(
            section(
                f"{lab.name}'s saves",
                SavedOpportunity.objects.filter(target_lab=lab, area__in=types),
            )
        )
    return Result(content="\n\n".join(out), refs=refs)


def _slate_ids(kwargs: dict) -> set:
    from tools.recommendation.read import RelevanceScore, in_slate

    rows = RelevanceScore.objects.filter(**kwargs, content__type__in=DATED).only(
        "content_id", "signals"
    )
    return {r.content_id for r in rows if in_slate(r.signals or {})}


def feeds_deadlines(
    caller,
    days=None,
    limit=None,
    offset=None,
    types=None,
    due_from=None,
    due_to=None,
    deadline=None,
):
    from django.utils import timezone

    from tools.delivery.read import SavedOpportunity
    from tools.retrieval.read import ContentDeadline

    types = _types(types, DATED)
    kinds = lists.kinds_arg(deadline, lists.DEADLINES)
    start = lists.int_arg(offset, 0, 0, 10**6)
    today = timezone.localdate()
    window = lists.window_arg(due_from, due_to)
    if window is None:
        days = _limit(days, 60, 366)
        since, until = today, today + timedelta(days=days)
        span = f"in the next {days} days"
    else:
        since, until = window
        span = lists.window_text(since, until)
    if len(kinds) == 1:
        only = "event dates" if kinds[0] == "event" else f"{kinds[0]} deadlines"
        span += f" ({only} only)"
    if set(types) != set(DATED):
        span += f" ({', '.join(types)} only)"
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
        gone = mine.filter(
            content__isnull=True, deadline_date__gte=since, area__in=types
        )
        if until is not None:
            gone = gone.filter(deadline_date__lte=until)
        loose = list(gone) if start == 0 else []
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
    # The filter runs in the database over everything read; the cut comes after.
    ahead = ContentDeadline.objects.filter(
        content_id__in=list(origin),
        due_date__gte=since,
        kind__in=list(kinds),
        content__type__in=types,
    )
    in_window = ahead if until is None else ahead.filter(due_date__lte=until)
    total = in_window.count()
    later = 0 if until is None else ahead.filter(due_date__gt=until).count()
    page = in_window.select_related("content").order_by("due_date", "kind")
    stop = None if limit in (None, "") else start + lists.int_arg(limit, 20, 1, 200)
    rows = list(page[start:stop])
    lines = []
    for d in rows:
        info = common.item_info(d.content)
        what = d.get_kind_display().lower() + (
            f" ({d.round_label})" if d.round_label else ""
        )
        sure = "" if d.confidence == "confirmed" else f", {d.confidence}"
        lines.append(
            f"- {d.due_date:%Y-%m-%d} (in {(d.due_date - today).days} days) "
            f"{{ref:{info.ref}}} {common.item_title(d.content)} — {what}{sure}; "
            f"from {origin[d.content_id]}"
        )
    keep = lists.fit(lines)
    refs = [common.item_info(d.content) for d in rows[:keep]]
    lines = lines[:keep]
    for s in loose:
        lines.append(
            f"- {s.deadline_date:%Y-%m-%d} (in {(s.deadline_date - today).days} days) "
            f"{common.clip(s.title, 160)} — saved date (item left the corpus); "
            "from your saves"
        )
    after = (
        f"\n{later} more deadline{'s fall' if later != 1 else ' falls'} after "
        f"{until:%Y-%m-%d}; pass days (at most 366) or due_to to see them."
        if later
        else ""
    )
    last = "\n" + lists.closing(start, keep, total, f"deadlines {span}")
    if not lines:
        return Result(
            content=f"No deadlines {span} among the saved and slate items read here."
            + last
            + after
        )
    return Result(
        content=f"Deadlines {span}:\n" + "\n".join(lines) + last + after,
        refs=refs,
    )

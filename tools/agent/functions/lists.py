"""What the feed functions share: the filters a list takes, applied in the
database before anything is cut; paging; and the closing line that says
whether a list is the whole of it (Q-079).

A person asks "which grants in the feed are due in March?". Answered from a
view cut to the first few rows, the answer is wrong and reads as complete. So
a list function here takes the filter, returns every match that fits the
result budget, and always ends by saying either that this is all of it or how
to get the rest. Nothing here ranks: a slate is read in the order the nightly
run gave it.
"""

from __future__ import annotations

from datetime import date

from tools._framework.agentspec import FunctionError, Result

from . import common

TYPES = ("paper", "grant", "fellowship", "conference")
#: The types that carry deadlines.
DATED = ("grant", "fellowship", "conference")
DEADLINES = ("application", "abstract", "manuscript", "event", "other")
#: What "a deadline" means when none is named: a date to apply or submit by,
#: not the dates an event is held on.
SUBMISSION = ("application", "abstract", "manuscript", "other")
#: Room kept under the result cap for the heading and the closing line.
RESERVE = 600


def types_arg(types, allowed=TYPES) -> list[str]:
    return [t for t in (types or allowed) if t in allowed] or list(allowed)


def int_arg(value, default: int, low: int, top: int) -> int:
    try:
        return max(low, min(int(default if value in (None, "") else value), top))
    except (TypeError, ValueError):
        return default


def date_arg(value, name: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise FunctionError(
            "bad_arguments",
            f"{name} must be a date written as YYYY-MM-DD.",
            f"Pass {name}='2027-03-31', for example.",
        ) from None


def window_arg(due_from, due_to, deadline=None):
    """``(first day, last day or None)`` when a deadline filter was asked
    for, else ``None``. With no first day the window opens today: a deadline
    that has passed is only listed when asked for by date."""
    from django.utils import timezone

    lo, hi = date_arg(due_from, "due_from"), date_arg(due_to, "due_to")
    if lo is None and hi is None and not deadline:
        return None
    lo = lo or timezone.localdate()
    if hi is not None and hi < lo:
        raise FunctionError(
            "bad_arguments",
            f"due_to ({hi}) is before due_from ({lo}).",
            "Pass the earlier date as due_from.",
        )
    return lo, hi


def kinds_arg(deadline, default=SUBMISSION) -> tuple[str, ...]:
    if deadline in (None, ""):
        return tuple(default)
    kind = str(deadline).strip().lower()
    if kind == "any":
        return DEADLINES
    if kind not in DEADLINES:
        raise FunctionError(
            "bad_arguments",
            f"deadline must be one of: {', '.join(DEADLINES)}, any.",
            "Leave it out for any date to apply or submit by.",
        )
    return (kind,)


def budget() -> int:
    """Characters of rows one result may carry and still be shown whole."""
    from ..rebuild import cap_chars

    return max(1000, cap_chars() - RESERVE)


def fit(lines: list[str], room: int | None = None) -> int:
    """How many of ``lines``, from the first, fit the result budget."""
    room = budget() if room is None else room
    used = 0
    for n, line in enumerate(lines):
        used += len(line) + 1
        if used > room and n:
            return n
    return len(lines)


def closing(start: int, shown: int, total: int, noun: str = "items") -> str:
    """The last line of every list: all of it, or how to get the rest."""
    end = start + shown
    if total == 0:
        return f"This is the complete list: 0 {noun}."
    if end >= total:
        if start == 0:
            return f"This is the complete list: all {total} of {total} {noun}."
        return (
            f"This is the end of the list: {noun} {start + 1} to {total} of "
            f"{total} (the earlier ones came with a smaller offset)."
        )
    part = (
        f"only the first {end} of {total}"
        if start == 0
        else f"only {start + 1} to {end} of {total}"
    )
    return (
        f"This is not the complete list: {part} {noun}; pass offset={end} for the rest."
    )


def _plural(type_: str) -> str:
    return f"{type_}s"


def _joined(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def slate(target_kwargs: dict, types) -> list:
    """The target's current slate for these types, in rank order."""
    from tools.recommendation.read import RelevanceScore, order_by_slate

    rows = RelevanceScore.objects.filter(
        **target_kwargs, content__type__in=types
    ).select_related("content")
    return order_by_slate(rows)


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


def deadline_text(d) -> str:
    """``application deadline 2027-03-14, anticipated`` for one deadline row."""
    what = d.get_kind_display().lower()
    what = "event date" if d.kind == "event" else f"{what} deadline"
    if d.round_label:
        what += f" ({d.round_label})"
    sure = "" if d.confidence == "confirmed" else f", {d.confidence}"
    return f"{what} {d.due_date:%Y-%m-%d}{sure}"


def window_text(lo: date, hi: date | None) -> str:
    return f"from {lo:%Y-%m-%d} to {hi:%Y-%m-%d}" if hi else f"from {lo:%Y-%m-%d} on"


def kinds_text(kinds) -> str:
    kinds = tuple(kinds)
    if kinds == tuple(DEADLINES):
        return "a deadline or event date"
    if kinds == tuple(SUBMISSION):
        return "a deadline to apply or submit by"
    if kinds == ("event",):
        return "an event date"
    article = "an" if kinds[0][0] in "aeiou" else "a"
    return f"{article} {kinds[0]} deadline"


def due_in_window(content_ids, lo: date, hi: date | None, kinds) -> dict:
    """content id → its deadline rows inside the window, earliest first.
    Filtered in the database, over every id given: nothing is cut first."""
    from tools.retrieval.read import ContentDeadline

    rows = ContentDeadline.objects.filter(
        content_id__in=list(content_ids), kind__in=list(kinds), due_date__gte=lo
    )
    if hi is not None:
        rows = rows.filter(due_date__lte=hi)
    found: dict = {}
    for d in rows.order_by("due_date", "kind", "round_key"):
        found.setdefault(d.content_id, []).append(d)
    return found


def slate_view(
    target_kwargs: dict,
    *,
    title: str,
    head=None,
    types=None,
    limit=None,
    offset=None,
    due_from=None,
    due_to=None,
    deadline=None,
    default_limit: int = 8,
    decorate=None,
    more_refs=None,
) -> Result:
    """One target's slate as a result: in rank order, or — when a deadline
    window is asked for — every slate item with a deadline inside it.

    ``decorate(lines, rows)`` may add to each rank-order line (who in a lab
    should look) and fill ``more_refs`` with what it referred to; ``title`` is
    how the slate's owner reads in the heading.
    """
    types = types_arg(types)
    start = int_arg(offset, 0, 0, 10**6)
    window = window_arg(due_from, due_to, deadline)
    refs = [head] if head else []
    if window is not None:
        return _due_view(
            target_kwargs,
            title,
            refs,
            types,
            limit,
            start,
            window,
            deadline,
            decorate,
            more_refs,
        )
    limit = int_arg(limit, default_limit, 1, 25)
    sections, cut, shown_all, total_all = [], [], 0, 0
    room = budget()
    for t in types:
        ranked = slate(target_kwargs, [t])
        total_all += len(ranked)
        rows = ranked[start : start + limit]
        if not rows:
            if ranked:  # everything of this type came before the offset
                shown_all += len(ranked)
            continue
        item_refs, lines = slate_lines(rows)
        if decorate is not None:
            lines = decorate(lines, rows)
        keep = fit(lines, room)
        rows, lines, item_refs = rows[:keep], lines[:keep], item_refs[:keep]
        room = max(0, room - sum(len(line) + 1 for line in lines))
        refs += item_refs
        end = start + len(rows)
        shown_all += end
        whole = start == 0 and end >= len(ranked)
        if end < len(ranked):
            lead = "only the first " if start == 0 else f"only {start + 1} to "
            cut.append(f"{_plural(t)} {lead}{end} of {len(ranked)}")
        span = (
            f"all {len(ranked)}" if whole else f"{start + 1} to {end} of {len(ranked)}"
        )
        sections.append(f"{t.title()}s (rank order, {span}):\n" + "\n".join(lines))
    if not sections:
        if total_all and start:
            return Result(
                content=f"Current slate of {title}: nothing past offset {start}. "
                f"This is the end of the list ({total_all} items in all).",
                refs=refs,
            )
        return Result(
            content=f"{title[:1].upper()}{title[1:]}: nothing in the current "
            "slate yet (the nightly run fills it). This is the complete list: 0 items.",
            refs=refs,
        )
    refs += [info for info in (more_refs or []) if info not in refs]
    if cut:
        nxt = start + limit
        last = (
            f"This is not the complete slate: {'; '.join(cut)}. Pass offset={nxt} "
            "for the next ones (limit: at most 25 per category), or due_from and "
            "due_to to list only the items with a deadline between two dates."
        )
    elif start:
        last = (
            "This is the end of the slate (the earlier items came with a smaller "
            "offset)."
        )
    else:
        last = f"This is the complete slate: all {total_all} of {total_all} items."
    return Result(
        content=f"Current slate of {title}:\n" + "\n\n".join(sections) + "\n\n" + last,
        refs=refs,
    )


def _due_view(
    target_kwargs,
    title,
    refs,
    types,
    limit,
    start,
    window,
    deadline,
    decorate=None,
    more_refs=None,
):
    lo, hi = window
    kinds = kinds_arg(deadline)
    dated = [t for t in types if t in DATED] or list(DATED)
    ranked = [s for t in dated for s in slate(target_kwargs, [t])]
    due = due_in_window([s.content_id for s in ranked], lo, hi, kinds)
    matched = [s for s in ranked if s.content_id in due]
    noun = _joined([_plural(t) for t in dated])
    asked = f"{kinds_text(kinds)} {window_text(lo, hi)}"
    if not matched:
        return Result(
            content=f"None of the {len(ranked)} {noun} in the current slate of "
            f"{title} has {asked}. This is the complete list: 0 matching items.",
            refs=refs,
        )
    page = (
        matched[start:]
        if limit in (None, "")
        else matched[start : start + int_arg(limit, len(matched), 1, 10**6)]
    )
    lines = []
    for s in page:
        info = common.item_info(s.content)
        lines.append(
            f"- {{ref:{info.ref}}} {common.item_title(s.content)} [{s.content.type}] — "
            + "; ".join(deadline_text(d) for d in due[s.content_id])
        )
    keep = fit(lines)
    if decorate is not None:  # who should look, as the rank-order view has it
        lines = decorate(lines[:keep], page[:keep])
        keep = fit(lines)
    refs = refs + [common.item_info(s.content) for s in page[:keep]]
    refs += [info for info in (more_refs or []) if info not in refs]
    return Result(
        content=f"In the current slate of {title}, the {noun} with {asked} "
        f"(checked all {len(ranked)}; slate rank order):\n"
        + "\n".join(lines[:keep])
        + "\n"
        + closing(start, keep, len(matched), "matching items"),
        refs=refs,
    )

"""The facts an announcement showed, and how to tell when they changed.

An announcement's thread is updated in place when its call changes (plan D9). What
counts as a change is decided here, against a snapshot of exactly the facts the
post displayed: the next deadline and every round, the status, the award range,
and who may apply. A nightly re-scrape that returns the same record produces the
same snapshot and the same fingerprint, so nothing is posted; a moved date does
not.

The closing-soon list (plan D11) is composed here too, because it reads the same
deadlines.

Pure functions over a :class:`~apps.content.models.ContentItem`; no writes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta

from apps.content.deadlines_projection import deadline_specs_for
from apps.content.models import ContentItem, SavedOpportunity

#: The fields a change is reported for, in the order a "What changed" list shows.
_FIELD_LABELS = {
    "deadline": "Deadline",
    "rounds": "Rounds",
    "status": "Status",
    "award": "Award",
    "applicants": "Who may apply",
    "eligibility": "Eligibility text",
}


def facts_for(item: ContentItem, today: date) -> dict:
    """The snapshot of what a post about ``item`` shows today."""
    meta = item.metadata or {}
    specs = [
        s
        for s in deadline_specs_for(item, today.isoformat())
        if s.kind != SavedOpportunity.DeadlineKind.EVENT and s.due_date is not None
    ]
    future = sorted(s.due_date for s in specs if s.due_date >= today)
    rounds = {s.due_date.isoformat() for s in specs}
    if item.type == ContentItem.Type.CONFERENCE:
        # The projection keeps only future rounds; the record keeps them all, and a
        # conference whose last round passed must still read as finished.
        for entry in meta.get("deadlines_structured") or []:
            instant = str((entry or {}).get("instant") or "")[:10]
            if instant and (entry or {}).get("kind") in ("abstract", "submission"):
                rounds.add(instant)
    rounds = sorted(rounds)
    eligibility = meta.get("eligibility")
    if isinstance(eligibility, list):
        eligibility = "\n".join(str(x) for x in eligibility)
    return {
        "deadline": future[0].isoformat() if future else "",
        "rounds": rounds,
        "status": (meta.get("status") or "").strip().lower(),
        "award": _award(meta),
        "applicants": sorted(str(t) for t in meta.get("applicant_types") or []),
        "eligibility": _digest(eligibility or ""),
    }


def fingerprint(facts: dict) -> str:
    payload = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Change:
    field: str
    label: str
    old: str
    new: str

    def as_dict(self) -> dict:
        return {
            "field": self.field,
            "label": self.label,
            "old": self.old,
            "new": self.new,
        }

    def line(self) -> str:
        """``~~old~~ → **new**`` for a field with readable values, else a plain note."""
        if self.field == "eligibility":
            return "The eligibility text changed. Read the call again before applying"
        if self.field == "rounds":
            return f"{self.label}: {self.new or 'none listed'}"
        old = self.old or "not listed"
        new = self.new or "not listed"
        return f"{self.label}: ~~{old}~~ → **{new}**"


def changes(old: dict, new: dict) -> list[Change]:
    """What differs between two snapshots, in display order. Empty when identical.

    A deadline passing on its own is not a change: the next round moving forward
    because today moved past one is time, not news, so ``deadline`` and ``rounds``
    are compared only over dates both snapshots consider future.
    """
    if not old or fingerprint(old) == fingerprint(new):
        return []
    out: list[Change] = []
    for field_name, label in _FIELD_LABELS.items():
        before, after = old.get(field_name), new.get(field_name)
        if field_name == "rounds":
            horizon = new.get("deadline") or ""
            before = [d for d in before or [] if d >= horizon]
            after = [d for d in after or [] if d >= horizon]
        if field_name == "deadline" and before and after and before < after:
            # Past rounds drop away on their own; only call it a move when the
            # earlier date is not simply behind us.
            if before in (old.get("rounds") or []) and before in (
                new.get("rounds") or []
            ):
                continue
        if before == after:
            continue
        out.append(
            Change(
                field_name, label, _show(field_name, before), _show(field_name, after)
            )
        )
    # A deadline move already says the rounds changed; don't say it twice.
    if any(c.field == "deadline" for c in out):
        out = [c for c in out if c.field != "rounds"]
    return out


def headline(change_list: list[Change]) -> str:
    """The one-line summary a tagging reply leads with."""
    if not change_list:
        return ""
    first = change_list[0]
    if first.field == "deadline" and first.old and first.new:
        text = f"the deadline moved from {first.old} to **{first.new}**"
    elif first.field == "status":
        text = f"the call is now **{first.new or 'unlisted'}**"
    elif first.field == "award":
        text = f"the award is now **{first.new or 'not listed'}**"
    else:
        text = f"{first.label.lower()} changed"
    more = len(change_list) - 1
    return text + (
        f" (and {more} more change{'s' if more > 1 else ''})" if more else ""
    )


# --------------------------------------------------------------------------- #
# Closing soon
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClosingSoon:
    content_id: str
    kind: str
    title: str
    url: str
    funder: str
    due: date
    days: int


def closing_soon(items, today: date, *, window_days: int = 14) -> list[ClosingSoon]:
    """Grants and fellowships whose next deadline falls within ``window_days``,
    soonest first. ``items`` is whatever the target's list holds."""
    horizon = today + timedelta(days=window_days)
    out: list[ClosingSoon] = []
    seen: set[str] = set()
    for item in items:
        if item.type not in (ContentItem.Type.GRANT, ContentItem.Type.FELLOWSHIP):
            continue
        if str(item.id) in seen:
            continue
        seen.add(str(item.id))
        due = facts_for(item, today)["deadline"]
        if not due:
            continue
        when = date.fromisoformat(due)
        if today <= when <= horizon:
            meta = item.metadata or {}
            out.append(
                ClosingSoon(
                    content_id=str(item.id),
                    kind=item.type,
                    title=meta.get("title") or "Untitled",
                    url=item.source_url
                    or meta.get("source_url")
                    or meta.get("external_url")
                    or "",
                    funder=meta.get("funder") or meta.get("sponsor") or "",
                    due=when,
                    days=(when - today).days,
                )
            )
    out.sort(key=lambda row: (row.due, row.title))
    return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _award(meta: dict) -> str:
    floor, ceiling = meta.get("award_floor"), meta.get("award_ceiling")
    if floor is None and ceiling is None:
        low, high = meta.get("amount_min"), meta.get("amount_max")
        floor, ceiling = low, high
    if floor is None and ceiling is None:
        return (meta.get("amount") or meta.get("amount_raw") or "").strip()
    currency = (meta.get("currency") or meta.get("amount_currency") or "").upper()
    return f"{_num(floor)}–{_num(ceiling)} {currency}".strip()


def _num(value) -> str:
    if value is None:
        return "?"
    return f"{float(value):,.0f}"


def _digest(text: str) -> str:
    normal = " ".join(text.split()).casefold()
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()[:16] if normal else ""


def _show(field_name: str, value) -> str:
    if field_name in ("deadline",) and value:
        d = date.fromisoformat(value)
        return f"{d:%a}, {d:%b} {d.day}, {d.year}"
    if isinstance(value, list):
        return ", ".join(value)
    return str(value or "")

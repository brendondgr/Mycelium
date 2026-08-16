"""Rebuild the :class:`ContentDeadline` projection from opportunity metadata (R0).

Pure derivation plus a thin persistence step. The derivation reuses the *same*
status functions the feed already uses (:mod:`apps.scraper.pivot.deadlines` /
``.status``) — no new parsing — so the addressable deadlines never drift from what
the cards show. The persistence step upserts one row per ``(content, kind)``,
detects when a ``due_date`` moved (the DEADLINE_MOVED signal for R6), records
``changed_at`` + ``previous_due_date`` + an ``AuditEvent``, and deletes rows for a
kind a re-scrape dropped.

Derivation, per type (metadata shapes verified in ``pivot/records.py``):

* **Grant** → one APPLICATION row from ``metadata.deadline_date``.
* **Fellowship** → one APPLICATION row; confidence from ``metadata.deadline.type``
  (all seven observed values); rolling / continuous / varies / suspended / unknown
  carry no date.
* **Conference** → up to three rows (ABSTRACT / MANUSCRIPT / EVENT), one per date
  the ``deadlines`` string + ``event_date`` actually yield.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from apps.content.models import ContentDeadline, ContentItem, SavedOpportunity

_Kind = SavedOpportunity.DeadlineKind
_Confidence = ContentDeadline.Confidence

# Fellowship deadline.type -> confidence. All seven values the parser emits
# (see apps/scraper/eligibility/parsers.py + apps/scraper/pivot/records.py) are
# mapped so an unrecognised type can never silently become a remindable date.
_FELLOWSHIP_CONFIDENCE = {
    "true": _Confidence.CONFIRMED,
    "anticipated": _Confidence.ANTICIPATED,
    "continuous": _Confidence.ROLLING,
    "rolling": _Confidence.ROLLING,
    "varies": _Confidence.UNKNOWN,
    "suspended": _Confidence.UNKNOWN,
    "unknown": _Confidence.UNKNOWN,
}

_OPPORTUNITY_TYPES = frozenset(
    {
        ContentItem.Type.GRANT,
        ContentItem.Type.CONFERENCE,
        ContentItem.Type.FELLOWSHIP,
    }
)


@dataclass(frozen=True)
class DeadlineSpec:
    """One derived deadline before it touches the database."""

    kind: str
    due_date: date | None
    label: str
    confidence: str


@dataclass(frozen=True)
class DeadlineChange:
    """A deadline that changed on an existing row (the R6 announcement signal).

    Fires when the ``due_date`` moved, or when an anticipated deadline was confirmed.
    """

    content_id: str
    kind: str
    old: date | None
    new: date | None
    confidence: str
    previous_confidence: str = ""


def _to_date(value: str | None) -> date | None:
    """Parse an ISO date; coerce ``YYYY-MM`` to the 1st of the month; else None."""
    if not value:
        return None
    text = str(value).strip()
    if len(text) == 7:  # YYYY-MM (fellowship month-only)
        text = text + "-01"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def deadline_specs_for(item: ContentItem, today: str) -> list[DeadlineSpec]:
    """Derive the addressable deadlines for one opportunity item (pure, no DB)."""
    meta = item.metadata or {}
    if item.type == ContentItem.Type.GRANT:
        return _grant_specs(meta)
    if item.type == ContentItem.Type.FELLOWSHIP:
        return _fellowship_specs(meta)
    if item.type == ContentItem.Type.CONFERENCE:
        return _conference_specs(meta, today)
    return []


def _grant_specs(meta: dict) -> list[DeadlineSpec]:
    due = _to_date(meta.get("deadline_date"))
    return [
        DeadlineSpec(
            kind=_Kind.APPLICATION,
            due_date=due,
            label="Application deadline",
            confidence=_Confidence.CONFIRMED if due else _Confidence.UNKNOWN,
        )
    ]


def _fellowship_specs(meta: dict) -> list[DeadlineSpec]:
    deadline = meta.get("deadline") or {}
    dtype = (
        deadline.get("type") or meta.get("deadline_type") or "unknown"
    ).strip().lower()
    confidence = _FELLOWSHIP_CONFIDENCE.get(dtype, _Confidence.UNKNOWN)
    due: date | None = None
    if confidence in (_Confidence.CONFIRMED, _Confidence.ANTICIPATED):
        due = _to_date(meta.get("deadline_date") or deadline.get("date"))
        if due is None:  # typed as dated but no parseable date — demote honestly
            confidence = _Confidence.UNKNOWN
    return [
        DeadlineSpec(
            kind=_Kind.APPLICATION,
            due_date=due,
            label="Application deadline",
            confidence=confidence,
        )
    ]


def _conference_specs(meta: dict, today: str) -> list[DeadlineSpec]:
    # Lazy import: keeps the scraper package out of the module import graph until
    # a conference is actually projected (mirrors the codebase's lazy-import style).
    from apps.scraper.pivot.deadlines import parse_deadlines, submission_status

    deadlines = parse_deadlines(meta.get("deadlines") or "")
    event_date = meta.get("event_date") or ""
    status = submission_status(deadlines, event_date, today)
    candidates = (
        (_Kind.ABSTRACT, status.get("abstract_deadline"), "Abstract deadline"),
        (_Kind.MANUSCRIPT, status.get("manuscript_deadline"), "Manuscript deadline"),
        (_Kind.EVENT, event_date, "Event date"),
    )
    specs: list[DeadlineSpec] = []
    for kind, raw, label in candidates:
        due = _to_date(raw)
        if due is None:
            continue  # no date for this kind → no row (a conference has 0–3 rows)
        specs.append(
            DeadlineSpec(
                kind=kind,
                due_date=due,
                label=label,
                confidence=_Confidence.CONFIRMED,
            )
        )
    return specs


def rebuild_deadlines_for(
    item: ContentItem,
    today: str,
    *,
    detect_changes: bool = True,
) -> list[DeadlineChange]:
    """Upsert the ``ContentDeadline`` rows for one item; return the date moves.

    ``detect_changes=False`` (backfill) skips ``changed_at`` / ``previous_due_date``
    / ``AuditEvent`` bookkeeping so a rebuild over historical data does not manufacture
    a wave of phantom "moved" signals.
    """
    specs_by_kind = {s.kind: s for s in deadline_specs_for(item, today)}
    existing = {row.kind: row for row in item.deadline_rows.all()}
    now = timezone.now()
    changes: list[DeadlineChange] = []

    # Drop rows for kinds a re-scrape no longer produces.
    for kind, row in existing.items():
        if kind not in specs_by_kind:
            row.delete()

    for kind, spec in specs_by_kind.items():
        row = existing.get(kind)
        if row is None:
            ContentDeadline.objects.create(
                content=item,
                kind=spec.kind,
                due_date=spec.due_date,
                label=spec.label,
                confidence=spec.confidence,
            )
            continue

        fields: list[str] = []
        if row.label != spec.label:
            row.label = spec.label
            fields.append("label")

        old_confidence = row.confidence
        old_due = row.due_date
        date_moved = old_due != spec.due_date
        # An anticipated deadline becoming confirmed is worth announcing even when
        # the date is unchanged (the highest-value change variant).
        confirmed = (
            spec.confidence == _Confidence.CONFIRMED
            and old_confidence == _Confidence.ANTICIPATED
        )

        if row.confidence != spec.confidence:
            row.confidence = spec.confidence
            fields.append("confidence")
        if date_moved:
            row.previous_due_date = old_due
            row.due_date = spec.due_date
            fields += ["previous_due_date", "due_date"]

        if detect_changes and (date_moved or confirmed):
            row.previous_confidence = old_confidence
            row.changed_at = now
            fields += ["previous_confidence", "changed_at"]
            changes.append(
                DeadlineChange(
                    content_id=str(item.id),
                    kind=kind,
                    old=old_due,
                    new=spec.due_date,
                    confidence=spec.confidence,
                    previous_confidence=old_confidence,
                )
            )
        if fields:
            row.save(update_fields=[*fields, "updated_at"])

    if detect_changes and changes:
        _audit_changes(item, changes)
    return changes


def rebuild_all(today: str, *, detect_changes: bool = False) -> int:
    """Rebuild every opportunity's projection (the backfill). Returns item count."""
    count = 0
    qs = ContentItem.objects.filter(type__in=_OPPORTUNITY_TYPES)
    for item in qs.iterator():
        rebuild_deadlines_for(item, today, detect_changes=detect_changes)
        count += 1
    return count


def _audit_changes(item: ContentItem, changes: list[DeadlineChange]) -> None:
    # Lazy import: accounts.services pulls model code; keep it out of import time.
    from apps.accounts.services import record_audit_event

    for change in changes:
        record_audit_event(
            actor=None,
            action="opportunity.deadline.moved",
            target_type="content_deadline",
            target_id=str(item.id),
            metadata={
                "kind": change.kind,
                "old_due_date": change.old.isoformat() if change.old else None,
                "new_due_date": change.new.isoformat() if change.new else None,
                "confidence": change.confidence,
                "previous_confidence": change.previous_confidence,
                "content_type": item.type,
            },
        )

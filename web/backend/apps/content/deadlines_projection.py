"""Rebuild the :class:`ContentDeadline` projection from opportunity metadata (R0).

Pure derivation plus a thin persistence step. The persistence step upserts one row
per ``(content, kind)``, detects when a ``due_date`` moved (the DEADLINE_MOVED
signal for R6), records ``changed_at`` + ``previous_due_date`` + an
``AuditEvent``, and deletes rows for a kind a re-scrape dropped. **Do not widen
that unique key** (plan D1) — a specific non-next round is never individually
remindable; the full array lives in metadata and drives display instead (see
:mod:`apps.scraper.collect.mapping`, ``deadlines_structured`` / ``due_dates``).

Derivation, per type:

* **Grant** → one APPLICATION row from ``metadata["deadline_date"]``. Since plan
  Phase 3, that key is no longer "the one deadline the record has" — it is
  ``select_next_due(rounds, today)``, computed once in
  ``apps.scraper.collect.mapping._grant_deadlines``: the next *future* round, or
  the latest round if every round has already passed. This module trusts that
  value rather than re-deriving it from ``metadata["due_dates"]`` — the round
  selection has exactly one owner.
* **Fellowship** → one APPLICATION row; confidence from ``metadata.deadline.type``
  (all seven observed values, see the seven-value map below); rolling /
  continuous / varies / suspended / unknown carry no date. **Untouched by this
  phase** — plan Phase 5 is a conference/grant change only.
* **Conference** → up to three rows, one per *mapped* kind
  (ABSTRACT / MANUSCRIPT / OTHER — no EVENT; see the kind-mapping note on
  ``_conference_specs``), each holding the **next future occurrence**
  of that kind. The full ordered array — every round, past and future — stays in
  ``metadata["deadlines_structured"]`` and drives the hover; this module only
  ever picks the single date a reminder can point at.

The conference path, post-Phase-6
------------------------------------------------------------------------------
``_conference_specs`` reads ``metadata["deadlines_structured"]`` unconditionally
— the array :func:`apps.scraper.collect.mapping.map_conference` always sets, even
to ``[]`` for a conference the collector found genuinely no dated deadlines for.
An empty list and an absent key are treated identically (both yield zero rows):
there is no longer a second, Pivot-era shape to fall back to.

Before Phase 6 (Pivot-RP's deletion) this function dispatched on whether that key
was present at all, falling back to a lazy import of
:mod:`apps.scraper.pivot.deadlines` to re-parse Pivot's free-text ``deadlines``
string for every Pivot-sourced conference still in the table. That branch —
``_legacy_conference_specs`` — and its import were deleted in Phase 6, once
Pivot's own conference ingest (the only writer of that free-text shape) stopped
running. Its two-line rationale here, for anyone diffing against an older
version of this file: keeping both paths was deliberate *until* Pivot's ingest
was gone, not a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from django.utils import timezone

from apps.content.models import ContentDeadline, ContentItem, SavedOpportunity

_Kind = SavedOpportunity.DeadlineKind
_Confidence = ContentDeadline.Confidence

# Fellowship deadline.type -> confidence. All seven values the parser emits
# (see apps/scraper/eligibility/parsers.py + apps/scraper/fellowships/records.py)
# are mapped so an unrecognised type can never silently become a remindable date.
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

# The open collector's conference deadline vocabulary (nine values — see
# ``apps.scraper.collect.conferences.record.DEADLINE_TYPES``) collapses to the
# three kinds a conference ``ContentDeadline`` row may carry. Only ``abstract``
# and ``submission`` get a dedicated row; everything else — including any
# collector kind this module has never seen — falls through to OTHER via
# ``dict.get``'s default, deliberately, so a new adapter-invented kind degrades
# to "shown, unremindable-as-itself" rather than being silently dropped.
_STRUCTURED_KIND_MAP: dict[str, str] = {
    "abstract": _Kind.ABSTRACT,
    "submission": _Kind.MANUSCRIPT,
}

# Human labels per *collector* kind (not per ``ContentDeadline`` kind) — several
# collector kinds share the OTHER row, and which one currently holds it should
# still read as what it is ("Notification date"), not a flat "Other deadline"
# every time. Keyed by the winning entry's own ``kind``, so ABSTRACT/MANUSCRIPT
# get their entries here too rather than a separate table.
_STRUCTURED_LABELS: dict[str, str] = {
    "abstract": "Abstract deadline",
    "submission": "Manuscript deadline",
    "supplementary": "Supplementary materials deadline",
    "rebuttal_open": "Rebuttal window opens",
    "rebuttal_close": "Rebuttal deadline",
    "notification": "Notification date",
    "camera_ready": "Camera-ready deadline",
    "registration": "Registration deadline",
    "unknown": "Other deadline",
}


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
    """One APPLICATION row, from the *next future* round (plan Phase 5).

    ``metadata["deadline_date"]`` already carries that selection — plan Phase 3's
    ``apps.scraper.collect.mapping._grant_deadlines`` computes it once via
    ``select_next_due(rounds, today)`` and this function only reads it, rather
    than re-deriving "next future" from ``metadata["due_dates"]`` itself. That
    keeps the round-selection rule owned in exactly one place; a grant on its
    tenth round (``num:PAR25144``) projects round ten's *next* date here, never
    its last, without this module needing to know rounds exist at all.

    Confidence:

    * an empty ``deadline_date`` means the grant carries no round at all — a
      genuinely rolling opportunity, not a parsing gap (mapping.py's own rule:
      ``prune_after = ... else "" # "" = rolling, never expires``) — so it gets
      ROLLING with a null ``due_date`` rather than being silently downgraded to
      UNKNOWN. This matches the convention the reminders stack already uses for
      a dateless grant elsewhere (see
      ``apps.content.tests.test_reminders_tick._content_with_deadline``).
    * ``metadata["dates_inferred"]`` marks a projected date the source never
      stated outright (a cycle inferred from a publication pattern rather than
      read) — ANTICIPATED, the word the fellowship map already uses for "this
      could still move".
    * otherwise CONFIRMED.
    """
    due_text = meta.get("deadline_date") or ""
    due = _to_date(due_text)
    if not due_text:
        confidence = _Confidence.ROLLING
    elif meta.get("dates_inferred"):
        confidence = _Confidence.ANTICIPATED
    else:
        confidence = _Confidence.CONFIRMED
    return [
        DeadlineSpec(
            kind=_Kind.APPLICATION,
            due_date=due,
            label="Application deadline",
            confidence=confidence,
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
    """Project ``metadata["deadlines_structured"]`` (plan Phase 5, the only path
    since Phase 6 deleted the legacy Pivot free-text parser this used to fall
    back to for a record missing that key).

    Kind mapping (plan Phase 5): collector ``abstract`` → ABSTRACT; collector
    ``submission`` → MANUSCRIPT — semantically the full-paper deadline, despite
    the name change, which is why the label table above still calls it
    "Manuscript deadline"; every other collector kind (``notification``,
    ``registration``, both ``rebuttal_*``, ``camera_ready``, ``supplementary``,
    ``unknown``, and anything future) → OTHER. There is deliberately **no EVENT
    row** here — unlike the legacy Pivot path, the collector's deadline array
    never contains an event-date entry (event dates live in
    ``metadata["event_start"]``/``["event_end"]`` instead, outside this array),
    so there is nothing to map to it.

    Per plan D1, each of the (at most three) rows holds the **next future**
    occurrence of its mapped kind — past-dated and unparseable (``instant`` is
    ``None``, TBD) entries are never candidates, and a mapped kind with no future
    entry at all simply gets no row (a conference may again yield 0–3 rows, same
    as the legacy path, just a different three). **OTHER must never be read as
    "still open for submission"** — that gate is computed once, independently,
    over ``abstract``/``submission`` alone, in
    ``apps.scraper.collect.mapping._conference_deadlines`` /
    ``SUBMISSION_TYPES``; this function does not compute openness at all, and a
    conference whose only future date is a ``notification`` correctly yields an
    OTHER row here while ``metadata["open"]`` stays ``False``.

    Confidence: the winning entry's own ``is_estimated`` (plan Phase 5) → is a
    projected, not sourced, date → ANTICIPATED; otherwise CONFIRMED. A "rolling"
    reading does not apply to conferences the way it does to grants — a null
    ``instant`` here means TBD/unparseable, not "genuinely dateless by design",
    so such entries are excluded rather than kept as a dateless row.
    """
    entries = meta.get("deadlines_structured") or []
    today_date = date.fromisoformat(today)

    # mapped kind -> (due_date, is_estimated, collector kind) of the earliest
    # future occurrence seen so far for that mapped kind.
    winners: dict[str, tuple[date, bool, str]] = {}
    for entry in entries:
        due = _parse_structured_instant(entry.get("instant"))
        if due is None or due < today_date:
            continue  # TBD/unparseable, or already passed — never "the next one"
        collector_kind = entry.get("kind") or "unknown"
        mapped = _STRUCTURED_KIND_MAP.get(collector_kind, _Kind.OTHER)
        current = winners.get(mapped)
        if current is None or due < current[0]:
            winners[mapped] = (due, bool(entry.get("is_estimated")), collector_kind)

    return [
        DeadlineSpec(
            kind=mapped,
            due_date=due,
            label=_STRUCTURED_LABELS.get(collector_kind, "Other deadline"),
            confidence=(
                _Confidence.ANTICIPATED if is_estimated else _Confidence.CONFIRMED
            ),
        )
        for mapped, (due, is_estimated, collector_kind) in winners.items()
    ]


def _parse_structured_instant(value: str | None) -> date | None:
    """Parse a collector deadline's UTC instant string to a plain ``date``.

    Same tolerant approach as
    ``apps.scraper.collect.mapping._parse_instant`` (deliberately not imported
    from there — this module needs only the *date*, to compare against a
    caller-supplied ``today`` date, not the full instant): swap a trailing ``Z``
    for an explicit offset before ``datetime.fromisoformat``, which — unlike
    ``strptime("%Y-%m-%dT%H:%M:%SZ")`` — also accepts the microsecond-precision
    instants 24 of the 3,196 live deadlines carry.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


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

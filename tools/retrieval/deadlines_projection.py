"""Rebuild the :class:`ContentDeadline` projection from opportunity metadata (R0).

Pure derivation plus a thin persistence step. The persistence step upserts one row
per ``(content, kind)``, detects when a ``due_date`` moved (the DEADLINE_MOVED
signal for R6), records ``changed_at`` + ``previous_due_date`` + an
``AuditEvent``, and deletes rows for a kind a re-scrape dropped. **Do not widen
that unique key** (plan D1) — a specific non-next round is never individually
remindable; the full array lives in metadata and drives display instead (see
:mod:`tools.retrieval.collect.mapping`, ``deadlines_structured`` / ``due_dates``).

Derivation, per type:

* **Grant** → one APPLICATION row from ``metadata["deadline_date"]``. Since plan
  Phase 3, that key is no longer "the one deadline the record has" — it is
  ``select_next_due(rounds, today)``, computed once in
  ``tools.retrieval.collect.mapping._grant_deadlines``: the next *future* round, or
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
— the array :func:`tools.retrieval.collect.mapping.map_conference` always sets, even
to ``[]`` for a conference the collector found genuinely no dated deadlines for.
An empty list and an absent key are treated identically (both yield zero rows):
there is no second, legacy shape to fall back to.

Before Phase 6 this function dispatched on whether that key was present at all,
re-parsing a legacy free-text ``deadlines`` string for conferences from an
earlier source. That branch — ``_legacy_conference_specs`` — was deleted once
the only writer of that free-text shape stopped running.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

from django.utils import timezone

from tools.retrieval.models import ContentDeadline, ContentItem, DeadlineKind

_Kind = DeadlineKind
_Confidence = ContentDeadline.Confidence

# Fellowship deadline.type -> confidence. All seven values the parser emits
# (see tools/retrieval/eligibility/parsers.py + tools/retrieval/fellowships/records.py)
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
# ``tools.retrieval.collect.conferences.record.DEADLINE_TYPES``) collapses to the
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
    #: Stable identity of this round within its item — see ``ContentDeadline``.
    #: Empty for a single-round deadline (grant, fellowship, conference event).
    round_key: str = ""
    #: The source's own round wording, verbatim, for display and message copy.
    round_label: str = ""
    #: Earliest future row of its kind: the one a card's headline reads.
    is_next: bool = True


def round_key_for(collector_kind: str, round_label: str) -> str:
    """The collector's own deadline identity, as a projection key.

    ``tools.retrieval.collect.conferences.record.Deadline.identity`` is
    ``(kind, round_label.strip().lower())`` — deliberately *not* the date, so
    an extension updates an entry in place instead of appending a duplicate.
    Reusing it here is what makes ``round_key`` stable across re-scrapes: the
    row a reminder points at survives its own deadline moving, which is the
    entire premise of ``changed_at`` and the DEADLINE_MOVED announcement.

    Measured over the live corpus (2026-08-17): 1,120 dated entries, zero
    collisions. The collector's merge step is *why* — two entries that would
    collide here are the same entry to it and were merged before this ever
    ran. Nothing in the schema *guarantees* that, though, so
    :func:`_conference_specs` disambiguates a repeat by appending the date; see
    the note there on why that is the right degenerate case rather than
    something to prevent up front.
    """
    return f"{collector_kind}:{(round_label or '').strip().lower()}"


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
    #: Which round moved — the announcement must name it when there are several.
    round_key: str = ""


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
    ``tools.retrieval.collect.mapping._grant_deadlines`` computes it once via
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
      ``tools.delivery.tests.test_reminders_tick._content_with_deadline``).
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
    """One row per **future dated round**, plus the event itself.

    This is the per-round rewrite. The previous version kept only the single
    next future occurrence per mapped kind, at most three rows, and the module
    said outright that "a specific non-next round is never individually
    remindable". That is precisely the thing conferences need: 150 of 912 live
    conferences carry more than one dated deadline, and a venue with a workshop
    deadline plus two full-paper rounds cannot be served by one row per kind.

    Kind mapping is unchanged: collector ``abstract`` -> ABSTRACT, collector
    ``submission`` -> MANUSCRIPT (semantically the full-paper deadline, which is
    why its label still reads "Manuscript deadline"), everything else — and
    anything an adapter invents later — -> OTHER via ``dict.get``'s default, so
    a new kind degrades to "shown, remindable, labelled by its own name" rather
    than being dropped.

    What each row now carries is its **own** date rather than its kind's next
    one, identified by :func:`round_key_for`. Because that key includes the
    collector kind, the several collector kinds that share the OTHER row
    (notification, camera-ready, registration, both rebuttal ends, …) no longer
    contend for one row — each keeps its own, labelled as what it is.

    ``is_next`` marks the earliest future row per mapped kind, so a card can
    render its headline deadline without re-deriving the selection here.

    **The event row is new.** The collector's deadline array never contains an
    event entry (event dates live in ``metadata["event_start"]``/``["event_end"]``
    instead), so before this there was nothing an "remind me about the
    conference itself" alert could point at — the requirement that an alert be
    able to concern the event rather than a submission. It is derived from
    ``event_start`` and is deliberately **not** part of the openness
    computation, which stays over ``abstract``/``submission`` alone in
    ``tools.retrieval.collect.mapping._conference_deadlines``.

    Past-dated and unparseable (``instant is None``, TBD) entries are never
    candidates, so a conference may yield zero rows. Confidence follows the
    entry's own ``is_estimated``: a projected date is ANTICIPATED, a sourced one
    CONFIRMED. "Rolling" does not apply to a conference the way it does to a
    grant — a null ``instant`` here means TBD, not "dateless by design".
    """
    entries = meta.get("deadlines_structured") or []
    today_date = date.fromisoformat(today)

    specs: list[DeadlineSpec] = []
    seen: set[str] = set()
    for entry in entries:
        due = _parse_structured_instant(entry.get("instant"))
        if due is None or due < today_date:
            continue  # TBD/unparseable, or already passed
        collector_kind = entry.get("kind") or "unknown"
        round_label = (entry.get("round_label") or "").strip()
        base_label = _STRUCTURED_LABELS.get(collector_kind, "Other deadline")

        # Two entries of one kind, both unlabelled, are the degenerate case:
        # the collector treats them as *one* entry (``Deadline.identity``) and
        # merges them, so this never fires on real data. When it does, the date
        # is the only thing left that distinguishes them, so it becomes the
        # tie-break. That trades away key stability for the second row — a
        # reminder on it would not survive its date moving — which is the
        # correct trade: the alternative is silently dropping the round
        # entirely, and a reader who can see only one of two paper deadlines is
        # worse off than one whose reminder needs re-setting after a change.
        key = round_key_for(collector_kind, round_label)
        if key in seen:
            key = f"{key}:{due.isoformat()}"
        seen.add(key)

        specs.append(
            DeadlineSpec(
                kind=_STRUCTURED_KIND_MAP.get(collector_kind, _Kind.OTHER),
                due_date=due,
                label=f"{base_label} — {round_label}" if round_label else base_label,
                confidence=(
                    _Confidence.ANTICIPATED
                    if entry.get("is_estimated")
                    else _Confidence.CONFIRMED
                ),
                round_key=key,
                round_label=round_label,
            )
        )

    event = _to_date(meta.get("event_start"))
    if event is not None and event >= today_date:
        specs.append(
            DeadlineSpec(
                kind=_Kind.EVENT,
                due_date=event,
                label="Conference starts",
                confidence=_Confidence.CONFIRMED,
            )
        )

    return _mark_next(specs)


def _mark_next(specs: list[DeadlineSpec]) -> list[DeadlineSpec]:
    """Set ``is_next`` on the earliest dated spec of each kind, clear the rest.

    Computed over the derived specs rather than read off any one entry, because
    "next" is a fact about the *set* and only becomes true once every sibling is
    known. Ties (two rounds of one kind on the same day) resolve on ``round_key``
    so the choice is deterministic rather than dependent on source order.
    """
    winners: dict[str, tuple[date, str]] = {}
    for spec in specs:
        if spec.due_date is None:
            continue
        current = winners.get(spec.kind)
        candidate = (spec.due_date, spec.round_key)
        if current is None or candidate < current:
            winners[spec.kind] = candidate
    return [
        replace(
            spec,
            is_next=(
                spec.due_date is None
                or winners.get(spec.kind) == (spec.due_date, spec.round_key)
            ),
        )
        for spec in specs
    ]


def _parse_structured_instant(value: str | None) -> date | None:
    """Parse a collector deadline's UTC instant string to a plain ``date``.

    Same tolerant approach as
    ``tools.retrieval.collect.mapping._parse_instant`` (deliberately not imported
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
    # Keyed on (kind, round_key), matching the unique constraint: a conference
    # now yields one row per dated round, so keying on kind alone would collapse
    # every round of a kind onto one another and delete the rest on every
    # rebuild.
    specs_by_key = {(s.kind, s.round_key): s for s in deadline_specs_for(item, today)}
    existing = {(row.kind, row.round_key): row for row in item.deadline_rows.all()}
    now = timezone.now()
    changes: list[DeadlineChange] = []

    # Drop rows for rounds a re-scrape no longer produces — including a round
    # that has simply passed, since specs only ever cover future dates.
    for key, row in existing.items():
        if key not in specs_by_key:
            row.delete()

    for (kind, _round_key), spec in specs_by_key.items():
        row = existing.get((kind, spec.round_key))
        if row is None:
            ContentDeadline.objects.create(
                content=item,
                kind=spec.kind,
                round_key=spec.round_key,
                round_label=spec.round_label,
                is_next=spec.is_next,
                due_date=spec.due_date,
                label=spec.label,
                confidence=spec.confidence,
            )
            continue

        fields: list[str] = []
        if row.label != spec.label:
            row.label = spec.label
            fields.append("label")
        if row.round_label != spec.round_label:
            row.round_label = spec.round_label
            fields.append("round_label")
        if row.is_next != spec.is_next:
            row.is_next = spec.is_next
            fields.append("is_next")

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
                    round_key=spec.round_key,
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
                "round_key": change.round_key,
                "old_due_date": change.old.isoformat() if change.old else None,
                "new_due_date": change.new.isoformat() if change.new else None,
                "confidence": change.confidence,
                "previous_confidence": change.previous_confidence,
                "content_type": item.type,
            },
        )

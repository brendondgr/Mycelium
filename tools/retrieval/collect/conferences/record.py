"""The canonical conference records every adapter emits.

Three levels, and keeping them apart is the design decision everything else rests
on:

* **Series** — the recurring venue. Persistent across years. Carries acronym,
  full name, discipline, rankings, and registry identity.
* **Instance** — one year's edition. Carries all dates, location, website, and
  the CFP text.
* **Track / workshop** — a sub-event with its own deadline, usually earlier than
  the parent's and often on a different topic. Co-located with a parent instance
  but a separate record, pointing at it.

Quality signals and identity attach to the **series**; deadlines and CFP text
attach to the **instance**. Collapsing the two is what makes it impossible to
filter on rank and surface on deadline at the same time — which is the whole
product.

The other non-negotiable is that ``Deadline`` is an *ordered list of typed dated
entries*, never a set of columns. 278 of 1,161 instances in the structured corpus
already carry more than one round and VLDB carries twelve, so a schema with one
``deadline`` field is wrong on a quarter of the data before anything is scraped.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

# --- vocabularies --------------------------------------------------------

RecordKind = Literal["conference", "workshop", "track"]
RECORD_KINDS: tuple[RecordKind, ...] = ("conference", "workshop", "track")

#: A conference has many dates, not one. Only the *submission* types below drive
#: the "currently relevant" filter; the rest are shown but never used to decide
#: whether a record is actionable.
DeadlineType = Literal[
    "abstract",
    "submission",
    "supplementary",
    "rebuttal_open",
    "rebuttal_close",
    "notification",
    "camera_ready",
    "registration",
    "unknown",
]
DEADLINE_TYPES: tuple[DeadlineType, ...] = (
    "abstract",
    "submission",
    "supplementary",
    "rebuttal_open",
    "rebuttal_close",
    "notification",
    "camera_ready",
    "registration",
    "unknown",
)

#: Missing one of these disqualifies a submission even if the paper is ready, so
#: both count as "the venue is still open to me".
SUBMISSION_TYPES: frozenset[str] = frozenset({"abstract", "submission"})

#: None of these is conclusive alone. Stored per record so the threshold can be
#: tuned later instead of hard-coded now.
RED_FLAGS: tuple[str, ...] = (
    "multi_discipline_title",
    "short_cfp_window",
    "no_publisher",
    "fees_prominent",
    "no_committee",
    "repeated_extensions",
)


@dataclass
class Deadline:
    """One dated entry in an instance's ordered deadline list."""

    kind: DeadlineType = "unknown"
    #: Verbatim, exactly as the source wrote it. Never reconstructed.
    raw: str = ""
    #: ISO 8601 UTC instant, or None for TBD/unparseable entries.
    instant: str | None = None
    #: The label that converted raw to instant ("AoE", "UTC-8", "PT"), or an
    #: "inferred:..." marker where the source published no zone at all.
    basis: str = ""
    #: Free-text round label from the source ("round 2", "full paper deadline").
    #: There is no typed round vocabulary anywhere in the wild; 287 distinct
    #: values appear in the structured corpus alone.
    round_label: str = ""
    source: str = ""
    #: True only for dates this system projected. Never let a projection be
    #: indistinguishable from a confirmed date.
    is_estimated: bool = False
    #: Incremented when an upsert moves an existing deadline later. Repeated
    #: extensions are a predatory red flag, so the count is the signal.
    extension_count: int = 0

    def __post_init__(self) -> None:
        if self.kind not in DEADLINE_TYPES:
            raise ValueError(f"unknown deadline type: {self.kind!r}")

    @property
    def is_submission(self) -> bool:
        return self.kind in SUBMISSION_TYPES

    @property
    def identity(self) -> tuple[str, str]:
        """What makes two deadlines "the same entry" across runs.

        Type plus round label, deliberately *not* the date — an extension changes
        the date and must update this entry rather than append a duplicate.
        """
        return (self.kind, self.round_label.strip().lower())

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> Deadline:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class ConferenceSeries:
    """The recurring venue. Identity and quality live here, dates never do."""

    #: dblp venue key where available ("conf/sac"); otherwise a generated stable
    #: key from normalized acronym plus discipline.
    series_key: str
    acronym: str = ""
    #: Venues rename, merge and restyle, and the registry records former names.
    acronym_variants: list[str] = field(default_factory=list)
    full_name: str = ""
    name_variants: list[str] = field(default_factory=list)
    #: Field-of-research or sub-field codes, whichever the source supplies.
    field_codes: list[str] = field(default_factory=list)

    #: {"core": {"rank": "A*", "edition": "ICORE2026"}, "ccf": {...}}. Keyed by
    #: system because CCF, CORE and THCPL arrive from different places and must
    #: never overwrite each other.
    rankings: dict[str, dict[str, str]] = field(default_factory=dict)

    #: Registry presence — how many proceedings years the venue is indexed for.
    dblp_key: str = ""
    dblp_found: bool = False
    indexed_years: int = 0
    first_year: int | None = None
    last_year: int | None = None
    #: Populated when an acronym resolved to more than one registry venue. The
    #: resolver refuses to pick; these are recorded for a human instead.
    dblp_candidates: list[str] = field(default_factory=list)

    red_flags: list[str] = field(default_factory=list)
    contributing_sources: list[str] = field(default_factory=list)
    license: str = ""

    def to_row(self) -> dict[str, Any]:
        return {
            "series_key": self.series_key,
            "acronym": self.acronym,
            "acronym_variants": json.dumps(sorted(set(self.acronym_variants))),
            "full_name": self.full_name,
            "name_variants": json.dumps(sorted(set(self.name_variants))),
            "field_codes": json.dumps(self.field_codes),
            "rankings": json.dumps(self.rankings, sort_keys=True),
            "dblp_key": self.dblp_key,
            "dblp_found": int(self.dblp_found),
            "indexed_years": self.indexed_years,
            "first_year": self.first_year,
            "last_year": self.last_year,
            "dblp_candidates": json.dumps(sorted(set(self.dblp_candidates))),
            "red_flags": json.dumps(sorted(set(self.red_flags))),
            "contributing_sources": json.dumps(sorted(set(self.contributing_sources))),
            "license": self.license,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ConferenceSeries:
        return cls(
            series_key=row["series_key"],
            acronym=row["acronym"] or "",
            acronym_variants=json.loads(row["acronym_variants"] or "[]"),
            full_name=row["full_name"] or "",
            name_variants=json.loads(row["name_variants"] or "[]"),
            field_codes=json.loads(row["field_codes"] or "[]"),
            rankings=json.loads(row["rankings"] or "{}"),
            dblp_key=row["dblp_key"] or "",
            dblp_found=bool(row["dblp_found"]),
            indexed_years=row["indexed_years"] or 0,
            first_year=row["first_year"],
            last_year=row["last_year"],
            dblp_candidates=json.loads(row["dblp_candidates"] or "[]"),
            red_flags=json.loads(row["red_flags"] or "[]"),
            contributing_sources=json.loads(row["contributing_sources"] or "[]"),
            license=row["license"] or "",
        )

    def copy(self, **changes: Any) -> ConferenceSeries:
        return replace(self, **changes)


@dataclass
class ConferenceInstance:
    """One edition. Dates and CFP text live here, quality signals never do."""

    source: str
    source_record_id: str
    series_key: str = ""
    #: Populated for workshops and tracks; None for a main conference.
    parent_instance_key: str | None = None
    record_kind: RecordKind = "conference"

    title: str = ""
    acronym: str = ""
    #: The label the source gives the edition. Kept *separately* from the event
    #: dates because they disagree more often than you would expect: an edition
    #: labelled 2026 can be held in December 2025 or January 2027.
    year_label: str = ""
    #: Stripped from the title for matching, retained for display.
    ordinal: str = ""

    event_start: str | None = None
    event_end: str | None = None
    #: Free text, as written ("February 22 - March 1, 2022"). 131 distinct format
    #: skeletons appear in one source alone, so the verbatim string is the truth.
    event_dates_text: str = ""

    city: str = ""
    country_code: str = ""
    place_text: str = ""
    is_virtual: bool = False
    is_hybrid: bool = False

    url: str = ""
    cfp_text: str = ""
    topics: list[str] = field(default_factory=list)

    #: The ordered list. Never collapse to a single field.
    deadlines: list[Deadline] = field(default_factory=list)

    #: Written by the enrichment layer from the venue's own website, never by an
    #: adapter. Kept apart from ``cfp_text`` so generated prose and published
    #: prose can always be told apart — by a reader, by the embedder, and by the
    #: validation stage that measures how much of each we actually have.
    generated_summary: str = ""
    generated_topics: list[str] = field(default_factory=list)
    #: One of ``enrich.STATUSES``; empty when the record was never a candidate.
    enrichment_status: str = ""

    source_url: str = ""
    first_seen: str | None = None
    last_fetched: str | None = None
    contributing_sources: list[str] = field(default_factory=list)
    #: Set by dedupe layer 4. A fuzzy match never merges; it records that a human
    #: should look.
    review_candidates: list[str] = field(default_factory=list)
    #: Data-quality warnings found at parse time (inverted deadlines, a deadline
    #: after the event starts). Surfaced, never silently dropped.
    quality_warnings: list[str] = field(default_factory=list)
    unresolved_parent: bool = False
    #: False once every submission deadline has passed. The record is retained,
    #: not deleted — past instances feed the longevity signal and next year's
    #: deadline prediction.
    active: bool = True
    license: str = ""

    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.record_kind not in RECORD_KINDS:
            raise ValueError(f"unknown record kind: {self.record_kind!r}")
        if not self.contributing_sources:
            self.contributing_sources = [self.source]

    # -- keys -------------------------------------------------------------

    @property
    def source_key(self) -> tuple[str, str]:
        """Dedupe layer 1 key: the same record arriving twice from one source."""
        return (self.source, self.source_record_id)

    @property
    def instance_key(self) -> str:
        """The upsert key. Stable across runs and across sources where possible."""
        if self.series_key and self.year_label:
            return f"{self.series_key}|{self.year_label}|{self.record_kind}"
        return f"src:{self.source}:{self.source_record_id}"

    # -- deadline access --------------------------------------------------

    @property
    def submission_deadlines(self) -> list[Deadline]:
        return [d for d in self.deadlines if d.is_submission]

    def next_submission_deadline(self, now) -> Deadline | None:
        """The soonest future submission deadline, or None.

        This is what the surfacing layer sorts and filters on. Never the event
        date: a conference in June with a January deadline is worthless to show
        in March, even though the event is still upcoming.
        """
        from tools.retrieval.collect.conferences.timezones import is_future

        future = [d for d in self.submission_deadlines if is_future(d.instant, now)]
        return min(future, key=lambda d: d.instant or "") if future else None

    def is_relevant(self, now) -> bool:
        return self.next_submission_deadline(now) is not None

    def to_row(self) -> dict[str, Any]:
        return {
            "instance_key": self.instance_key,
            "source": self.source,
            "source_record_id": self.source_record_id,
            "series_key": self.series_key,
            "parent_instance_key": self.parent_instance_key,
            "record_kind": self.record_kind,
            "title": self.title,
            "acronym": self.acronym,
            "year_label": self.year_label,
            "ordinal": self.ordinal,
            "event_start": self.event_start,
            "event_end": self.event_end,
            "event_dates_text": self.event_dates_text,
            "city": self.city,
            "country_code": self.country_code,
            "place_text": self.place_text,
            "is_virtual": int(self.is_virtual),
            "is_hybrid": int(self.is_hybrid),
            "url": self.url,
            "cfp_text": self.cfp_text,
            "topics": json.dumps(self.topics, ensure_ascii=False),
            "deadlines": json.dumps([d.to_json() for d in self.deadlines], ensure_ascii=False),
            "generated_summary": self.generated_summary,
            "generated_topics": json.dumps(self.generated_topics, ensure_ascii=False),
            "enrichment_status": self.enrichment_status,
            "source_url": self.source_url,
            "first_seen": self.first_seen,
            "last_fetched": self.last_fetched,
            "contributing_sources": json.dumps(sorted(set(self.contributing_sources))),
            "review_candidates": json.dumps(sorted(set(self.review_candidates))),
            "quality_warnings": json.dumps(sorted(set(self.quality_warnings))),
            "unresolved_parent": int(self.unresolved_parent),
            "active": int(self.active),
            "license": self.license,
            "raw": json.dumps(self.raw, ensure_ascii=False, sort_keys=True),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ConferenceInstance:
        return cls(
            source=row["source"],
            source_record_id=row["source_record_id"],
            series_key=row["series_key"] or "",
            parent_instance_key=row["parent_instance_key"],
            record_kind=row["record_kind"],
            title=row["title"] or "",
            acronym=row["acronym"] or "",
            year_label=row["year_label"] or "",
            ordinal=row["ordinal"] or "",
            event_start=row["event_start"],
            event_end=row["event_end"],
            event_dates_text=row["event_dates_text"] or "",
            city=row["city"] or "",
            country_code=row["country_code"] or "",
            place_text=row["place_text"] or "",
            is_virtual=bool(row["is_virtual"]),
            is_hybrid=bool(row["is_hybrid"]),
            url=row["url"] or "",
            cfp_text=row["cfp_text"] or "",
            topics=json.loads(row["topics"] or "[]"),
            deadlines=[Deadline.from_json(d) for d in json.loads(row["deadlines"] or "[]")],
            generated_summary=row["generated_summary"] or "",
            generated_topics=json.loads(row["generated_topics"] or "[]"),
            enrichment_status=row["enrichment_status"] or "",
            source_url=row["source_url"] or "",
            first_seen=row["first_seen"],
            last_fetched=row["last_fetched"],
            contributing_sources=json.loads(row["contributing_sources"] or "[]"),
            review_candidates=json.loads(row["review_candidates"] or "[]"),
            quality_warnings=json.loads(row["quality_warnings"] or "[]"),
            unresolved_parent=bool(row["unresolved_parent"]),
            active=bool(row["active"]),
            license=row["license"] or "",
            raw=json.loads(row["raw"] or "{}"),
        )

    def copy(self, **changes: Any) -> ConferenceInstance:
        return replace(self, **changes)


#: Columns that never come from an adapter, so "did the source actually change?"
#: must ignore them. ``active`` is here because it is computed from the clock,
#: not from the payload — including it would make every run after a deadline
#: passes look like a source change and break the idempotency check.
BOOKKEEPING_COLUMNS = frozenset({"first_seen", "last_fetched", "active"})

#: Store-owned columns carried forward on update unless the incoming record
#: actually has a value. Without this the next ordinary collection run would
#: overwrite every generated summary with an empty string — the enrichment would
#: survive exactly until the next fetch.
#:
#: These are deliberately *not* in ``BOOKKEEPING_COLUMNS``, and the distinction
#: is the difference between the feature working and silently not. Ignoring them
#: in the change comparison neutralises the adapter re-emit, but it also makes a
#: genuine enrichment write invisible: a record that gained only a summary and
#: topics compares equal to its stored self, the store reports "unchanged", and
#: nothing is written. Measured: 5 of 9 generated summaries vanished that way —
#: exactly the four that also gained a deadline survived, because the deadline
#: change is what made the row look different.
#:
#: Carry-forward already handles the re-emit case, because it rewrites the empty
#: incoming value to the stored one *before* the comparison runs.
CARRY_FORWARD_COLUMNS = ("generated_summary", "generated_topics", "enrichment_status")

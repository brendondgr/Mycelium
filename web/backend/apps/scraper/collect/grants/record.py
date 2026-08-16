"""The canonical opportunity record every adapter emits.

Briefing section 4 defines this shape; section 1 defines the three record kinds it
has to carry. The kinds matter more than they look: a ``topic`` or ``overlay`` is a
first-class record that *points at* a parent rather than being folded into it,
because the parent is administrative boilerplate and the child is where the actual
research subject text lives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date as date_type
from typing import Any, Literal

RecordKind = Literal["standalone", "topic", "overlay"]

#: Every kind we accept. Anything else is a parse bug, not a new category.
RECORD_KINDS: tuple[RecordKind, ...] = ("standalone", "topic", "overlay")

#: Only these two statuses may enter the store (briefing section 6).
Status = Literal["open", "forecasted"]
STATUSES: tuple[Status, ...] = ("open", "forecasted")


@dataclass
class Opportunity:
    """One funding opportunity, normalized across every source.

    ``first_seen`` and ``contributing_sources`` are the two fields the store owns
    rather than the adapter: the first is set once and never overwritten, the
    second is unioned on every merge.
    """

    # --- identity ---
    source: str
    source_record_id: str
    source_url: str = ""
    opportunity_number: str = ""
    parent_opportunity_number: str | None = None
    record_kind: RecordKind = "standalone"

    # --- descriptive ---
    title: str = ""
    funder: str = ""
    funder_subunit: str = ""
    description: str = ""
    categories: list[str] = field(default_factory=list)

    # --- temporal ---
    status: Status = "open"
    posted_date: str | None = None
    open_date: str | None = None
    close_date: str | None = None
    #: Verbatim deadline string. Federal deadlines are often "5 p.m. submitter's
    #: local time", which is not a single instant, so we keep the words as given
    #: instead of inventing a timezone (briefing section 7, normalization notes).
    close_date_text: str = ""
    additional_due_dates: list[str] = field(default_factory=list)
    expiration_date: str | None = None
    #: Letter-of-intent deadline. Falls *before* the application deadline and
    #: missing it is disqualifying, so it is tracked separately rather than left
    #: buried in the announcement text.
    intent_date: str | None = None
    #: The LOI requirement as written. Frequently relative ("30 days prior to the
    #: application due date") or a plain "Not applicable", neither of which is a
    #: date but both of which the applicant needs to read.
    intent_date_text: str = ""
    #: The deadline before the funder moved it, where the source says so. The
    #: history table can only see changes after we start watching; this is the
    #: source telling us about an extension that already happened.
    original_close_date: str | None = None
    #: True when some of ``additional_due_dates`` was derived from a published
    #: cycle rather than read from the source. Inference that cannot be told apart
    #: from source data is inference nobody can check.
    dates_inferred: bool = False

    # --- financial ---
    award_floor: float | None = None
    award_ceiling: float | None = None
    total_program_funding: float | None = None
    expected_awards: int | None = None
    currency: str = "USD"

    # --- structured facets ---
    #
    # Every one of these was already present in the raw payloads and reachable
    # only by reading JSON at query time, which meant no filter could use them.
    # They are lists or nullable scalars rather than free text so that "unknown"
    # stays distinguishable from "no" — a filter that silently treats a missing
    # value as an exclusion drops records that may well qualify.

    #: Who may apply. The single most decision-relevant fact after the deadline.
    applicant_types: list[str] = field(default_factory=list)
    #: Grant, cooperative agreement, procurement contract, other.
    funding_instruments: list[str] = field(default_factory=list)
    #: NIH activity codes (R01, R21, K99, T32...). An R01 and an R21 are entirely
    #: different propositions and were previously indistinguishable.
    activity_codes: list[str] = field(default_factory=list)
    #: Assistance Listing / CFDA numbers — the stable federal programme taxonomy.
    assistance_listings: list[str] = field(default_factory=list)
    #: True when cost sharing is required, False when explicitly not, None when
    #: the source did not say. Often disqualifying, so the three states matter.
    cost_sharing: bool | None = None
    #: Canonical top-level agency code, which is stable where agency *names* are not.
    agency_code: str = ""
    #: The operating unit's name reconciled across sources. NSF arrived under two
    #: different strings, so a filter on either lost part of it.
    funder_canonical: str = ""
    #: Discretionary, mandatory, continuation, earmark.
    opportunity_category: str = ""
    #: EU action types (RIA, IA, CSA...) — the EU's equivalent of an activity code.
    action_types: list[str] = field(default_factory=list)
    #: single-stage / two-stage. Changes what a submission actually involves.
    deadline_model: str = ""
    #: Source-assigned keywords and cross-cutting priority tags.
    topic_keywords: list[str] = field(default_factory=list)
    #: Sub-units participating in but not leading the opportunity (NIH PartIC).
    participating_units: list[str] = field(default_factory=list)
    #: Other announcement numbers this record points at — an overlay's second and
    #: subsequent parents, a reissue chain. ``parent_opportunity_number`` holds
    #: only the primary link, and these references were previously kept as
    #: pseudo-categories, which is how a subject field ends up holding identifiers.
    related_numbers: list[str] = field(default_factory=list)

    # --- other ---
    eligibility: str = ""
    first_seen: str | None = None
    last_fetched: str | None = None
    contributing_sources: list[str] = field(default_factory=list)

    #: Set by dedupe layer 3. A fuzzy match never merges; it only records that a
    #: human should look (briefing section 5, critical rule).
    review_candidates: list[str] = field(default_factory=list)
    #: True when an overlay names a parent we could not resolve to a stored record.
    unresolved_parent: bool = False

    #: The source payload, verbatim. Retained always — the first parse pass will be
    #: wrong somewhere and re-fetching five APIs to fix it is not acceptable.
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.record_kind not in RECORD_KINDS:
            raise ValueError(f"unknown record kind: {self.record_kind!r}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status: {self.status!r}")
        if not self.contributing_sources:
            self.contributing_sources = [self.source]

    # -- dates ------------------------------------------------------------

    @property
    def all_due_dates(self) -> list[str]:
        """Every known application round, deduplicated and in order.

        A recurring opportunity has several; a one-shot has one; a rolling one
        has none. Callers that need "the whole picture" use this rather than
        reassembling ``close_date`` and ``additional_due_dates`` themselves and
        getting the union subtly wrong.
        """
        return sorted({value for value in [self.close_date, *self.additional_due_dates] if value})

    def due_on(self, today: date_type | None = None) -> str | None:
        """The round a reader should be shown as of ``today``.

        Derived rather than stored, so it cannot go stale between collection
        runs — a store left untouched for a month would otherwise keep
        advertising a round that passed three weeks ago.
        """
        from apps.scraper.collect.grants.normalize import select_next_due

        return select_next_due(list(self.all_due_dates), today or date_type.today())

    @property
    def effective_due_date(self) -> str | None:
        """The single date a reader is shown, and sorts and counts down against.

        Distinct from ``close_date``, which is the last date the opportunity is
        alive and therefore what pruning keys on. For a recurring opportunity the
        two differ, and conflating them is exactly the bug that showed a 2021
        deadline for a call whose next round was five weeks away.
        """
        return self.due_on()

    # -- keys -------------------------------------------------------------

    @property
    def source_key(self) -> tuple[str, str]:
        """Dedupe layer 1 key: the same record arriving twice from one source."""
        return (self.source, self.source_record_id)

    @property
    def stable_key(self) -> str:
        """The upsert key. Stable across runs and across sources when possible.

        Prefers the funder-assigned number (which is what makes cross-source
        merging work at all) and falls back to the source-local id for records
        that never got one.
        """
        from apps.scraper.collect.grants.normalize import normalize_opportunity_number

        number = normalize_opportunity_number(self.opportunity_number)
        if number:
            # Topics and overlays keep their own identity even when they share a
            # normalized number stem with the parent.
            if self.record_kind == "standalone":
                return f"num:{number}"
            return f"num:{number}:{self.record_kind}"
        return f"src:{self.source}:{self.source_record_id}"

    # -- serialization ----------------------------------------------------

    def to_row(self) -> dict[str, Any]:
        """Flatten to the SQLite column set. Lists become JSON, not delimiters."""
        return {
            "stable_key": self.stable_key,
            "source": self.source,
            "source_record_id": self.source_record_id,
            "source_url": self.source_url,
            "opportunity_number": self.opportunity_number,
            "parent_opportunity_number": self.parent_opportunity_number,
            "record_kind": self.record_kind,
            "title": self.title,
            "funder": self.funder,
            "funder_subunit": self.funder_subunit,
            "description": self.description,
            "categories": json.dumps(self.categories, ensure_ascii=False),
            "status": self.status,
            "posted_date": self.posted_date,
            "open_date": self.open_date,
            "close_date": self.close_date,
            "close_date_text": self.close_date_text,
            "additional_due_dates": json.dumps(self.additional_due_dates),
            "expiration_date": self.expiration_date,
            "original_close_date": self.original_close_date,
            "intent_date": self.intent_date,
            "intent_date_text": self.intent_date_text,
            "dates_inferred": int(self.dates_inferred),
            "award_floor": self.award_floor,
            "award_ceiling": self.award_ceiling,
            "total_program_funding": self.total_program_funding,
            "expected_awards": self.expected_awards,
            "currency": self.currency,
            "applicant_types": json.dumps(self.applicant_types, ensure_ascii=False),
            "funding_instruments": json.dumps(self.funding_instruments, ensure_ascii=False),
            "activity_codes": json.dumps(self.activity_codes, ensure_ascii=False),
            "assistance_listings": json.dumps(self.assistance_listings, ensure_ascii=False),
            "cost_sharing": None if self.cost_sharing is None else int(self.cost_sharing),
            "agency_code": self.agency_code,
            "funder_canonical": self.funder_canonical,
            "opportunity_category": self.opportunity_category,
            "action_types": json.dumps(self.action_types, ensure_ascii=False),
            "deadline_model": self.deadline_model,
            "topic_keywords": json.dumps(self.topic_keywords, ensure_ascii=False),
            "participating_units": json.dumps(self.participating_units, ensure_ascii=False),
            "related_numbers": json.dumps(self.related_numbers, ensure_ascii=False),
            "eligibility": self.eligibility,
            "first_seen": self.first_seen,
            "last_fetched": self.last_fetched,
            "contributing_sources": json.dumps(sorted(set(self.contributing_sources))),
            "review_candidates": json.dumps(sorted(set(self.review_candidates))),
            "unresolved_parent": int(self.unresolved_parent),
            "raw": json.dumps(self.raw, ensure_ascii=False, sort_keys=True),
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Opportunity:
        return cls(
            source=row["source"],
            source_record_id=row["source_record_id"],
            source_url=row["source_url"] or "",
            opportunity_number=row["opportunity_number"] or "",
            parent_opportunity_number=row["parent_opportunity_number"],
            record_kind=row["record_kind"],
            title=row["title"] or "",
            funder=row["funder"] or "",
            funder_subunit=row["funder_subunit"] or "",
            description=row["description"] or "",
            categories=json.loads(row["categories"] or "[]"),
            status=row["status"],
            posted_date=row["posted_date"],
            open_date=row["open_date"],
            close_date=row["close_date"],
            close_date_text=row["close_date_text"] or "",
            additional_due_dates=json.loads(row["additional_due_dates"] or "[]"),
            expiration_date=row["expiration_date"],
            original_close_date=row["original_close_date"],
            intent_date=row["intent_date"],
            intent_date_text=row["intent_date_text"] or "",
            dates_inferred=bool(row["dates_inferred"]),
            award_floor=row["award_floor"],
            award_ceiling=row["award_ceiling"],
            total_program_funding=row["total_program_funding"],
            expected_awards=row["expected_awards"],
            currency=row["currency"] or "USD",
            applicant_types=json.loads(row["applicant_types"] or "[]"),
            funding_instruments=json.loads(row["funding_instruments"] or "[]"),
            activity_codes=json.loads(row["activity_codes"] or "[]"),
            assistance_listings=json.loads(row["assistance_listings"] or "[]"),
            cost_sharing=None if row["cost_sharing"] is None else bool(row["cost_sharing"]),
            agency_code=row["agency_code"] or "",
            funder_canonical=row["funder_canonical"] or "",
            opportunity_category=row["opportunity_category"] or "",
            action_types=json.loads(row["action_types"] or "[]"),
            deadline_model=row["deadline_model"] or "",
            topic_keywords=json.loads(row["topic_keywords"] or "[]"),
            participating_units=json.loads(row["participating_units"] or "[]"),
            related_numbers=json.loads(row["related_numbers"] or "[]"),
            eligibility=row["eligibility"] or "",
            first_seen=row["first_seen"],
            last_fetched=row["last_fetched"],
            contributing_sources=json.loads(row["contributing_sources"] or "[]"),
            review_candidates=json.loads(row["review_candidates"] or "[]"),
            unresolved_parent=bool(row["unresolved_parent"]),
            raw=json.loads(row["raw"] or "{}"),
        )

    def copy(self, **changes: Any) -> Opportunity:
        return replace(self, **changes)


#: Columns that never come from an adapter, so comparisons that ask "did the
#: source actually change?" must ignore them.
BOOKKEEPING_COLUMNS = frozenset({"first_seen", "last_fetched"})

"""Map a raw Illinois Fellowship Finder record to a ``ContentItem``-shaped payload.

Every record this module sees is a fellowship, always, so it takes no area
parameter.

Deadlines are normalized through :mod:`tools.retrieval.eligibility.parsers` so a
single ``prune_after`` date drives the daily expiry, and ``deadline_date`` /
``next_kind`` drive the "New"/deadline UI and the save snapshot — exactly the
contract the pre-Phase-6 module documented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FELLOWSHIP_SOURCE = "illinois-fellowship-finder"


def _join(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())


def record_text(rec: dict) -> str:
    """The searchable document text: title/blurb/description + facets + eligibility.

    Facet strings add discriminating vocabulary for vector/BM25 search.
    """
    facets = rec.get("facets") or {}
    facet_parts = []
    for bucket in ("field", "citizenship", "stage", "award_type", "limits"):
        facet_parts.extend(facets.get(bucket) or [])
    eligibility = rec.get("eligibility") or []
    eligibility_text = (
        " ".join(eligibility) if isinstance(eligibility, list) else str(eligibility)
    )
    return _join(
        rec.get("title"),
        rec.get("blurb"),
        rec.get("description"),
        " ".join(facet_parts),
        eligibility_text,
    )


@dataclass
class FellowshipItem:
    """A normalized fellowship record ready to upsert into ``ContentItem``."""

    external_id: str
    source_url: str
    title: str  # display title
    subtitle: str  # award_class title-cased ("Scholarship", "Fellowship", ...)
    text: str  # embedding + BM25 document text
    metadata: dict = field(default_factory=dict)
    source: str = FELLOWSHIP_SOURCE
    type: str = "fellowship"

    @property
    def prune_after(self) -> str:
        """ISO date after which this item is expired (``""`` = never/unknown)."""
        return self.metadata.get("prune_after", "")

    @property
    def deadline_date(self) -> str:
        return self.metadata.get("deadline_date", "")


def _coerce_deadline_date(date: str) -> str:
    """Coerce a YYYY-MM deadline date to the first of that month (YYYY-MM-01).

    A full YYYY-MM-DD value is returned unchanged; an empty string is returned
    as-is; rolling/continuous/varies/suspended/unknown => "".
    """
    if not date:
        return ""
    if len(date) == 7:  # YYYY-MM
        return date + "-01"
    return date  # already YYYY-MM-DD


def build_fellowship_item(rec: dict, *, today: str) -> FellowshipItem | None:
    """Build a :class:`FellowshipItem` from one raw Illinois Fellowship Finder record.

    Returns ``None`` for a record missing a stable id (can't dedup it) or whose
    ``award_class`` is "grant" — the Illinois site lists some grants alongside its
    fellowships/scholarships; Mycelium's grant feed comes from the open collector,
    not this source, so those rows are excluded here rather than double-counted.
    """
    external_id = str(rec.get("id") or "").strip()
    if not external_id:
        return None
    if (rec.get("award_class") or "").strip().lower() == "grant":
        return None

    # Lazy imports keep this module's import graph clean of the eligibility
    # engine until a fellowship is actually built. Both live under
    # tools.retrieval.eligibility.
    from tools.retrieval.eligibility.constraints import extract_by_pattern
    from tools.retrieval.eligibility.parsers import deadline_status, facets_incomplete

    title = (rec.get("title") or "").strip()
    award_class = (rec.get("award_class") or "fellowship").strip()
    subtitle = award_class.title()  # e.g. "Scholarship", "Fellowship"

    # Deadline: structured dict from the record.
    deadline = rec.get("deadline") or {}
    deadline_raw_date = (deadline.get("date") or "").strip()
    deadline_type = (deadline.get("type") or "unknown").strip()

    # Coerce YYYY-MM to YYYY-MM-01 for database sorting; keep "" for dateless types.
    deadline_date = _coerce_deadline_date(deadline_raw_date)

    # prune_after: only for "true" deadlines with a full YYYY-MM-DD.
    prune_after = ""
    if deadline_type == "true" and len(deadline_raw_date) == 10:
        prune_after = deadline_raw_date

    next_kind = "application" if deadline_date else ""

    ds = deadline_status(deadline, today)

    # A record whose facet buckets are *all* empty told us nothing about who may
    # apply — a failed detail render or a missed selector looks exactly like an
    # award with no restrictions, and the matcher would otherwise read it as a
    # clean match for everybody. Flag it so eligibility can label it unverified.
    facets = rec.get("facets") or {}
    flags = dict(rec.get("flags") or {})
    flags["facets_incomplete"] = facets_incomplete(facets)

    # Amount.
    award_amount = rec.get("award_amount") or {}
    external_url = (rec.get("external_url") or "").strip()

    metadata = {
        "title": title,
        "blurb": (rec.get("blurb") or "").strip(),
        "description": (rec.get("description") or "").strip(),
        "award_class": award_class,
        "deadline": deadline,
        "deadline_date": deadline_date,
        "deadline_type": deadline_type,
        "amount_kind": (award_amount.get("kind") or ""),
        "amount_currency": (award_amount.get("currency") or ""),
        "amount_min": award_amount.get("min"),
        "amount_max": award_amount.get("max"),
        "amount_raw": (award_amount.get("raw") or ""),
        "amount_note": (award_amount.get("note") or ""),
        "facets": rec.get("facets") or {},
        "flags": flags,
        "eligibility": rec.get("eligibility") or [],
        # What the facets cannot say — read from the eligibility prose. The
        # pattern layer is free and runs on every build; the model layer runs
        # once per record at ingest for what the patterns did not resolve.
        "constraints": extract_by_pattern(
            rec.get("eligibility") or [], (rec.get("note") or "")
        ),
        "external_url": external_url,
        "contact_email": (rec.get("contact_email") or "").strip(),
        "note": (rec.get("note") or "").strip(),
        "website": external_url,  # SavedOpportunity compatibility
        "next_kind": next_kind,
        "status": ds["status"],
        "status_summary": ds["summary"],
        "prune_after": prune_after,
    }

    rec_source = (rec.get("source") or FELLOWSHIP_SOURCE).strip()
    source_url = (rec.get("source_url") or "").strip()

    return FellowshipItem(
        external_id=external_id,
        source_url=source_url,
        title=title,
        subtitle=subtitle,
        text=record_text(rec),
        metadata=metadata,
        source=rec_source,
    )

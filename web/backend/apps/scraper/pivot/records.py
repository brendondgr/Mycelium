"""Map a raw scraped/imported Pivot record to a ``ContentItem``-shaped payload.

This is the **port contract** between the ProQuest record schema and Mycelium's
unified :class:`~apps.content.models.ContentItem`. A grant/conference dict (either
freshly scraped or read from the tool's JSON/SQLite output) becomes a
:class:`PivotItem` describing the upsert: the dedup key, the searchable text (used
for both the embedding and BM25, matching the tool's ``documents.record_text``),
and a normalized ``metadata`` blob the API serializers read back.

Deadlines are normalized through the shared :mod:`.status` logic so a single
``prune_after`` date drives the daily expiry, and ``deadline_date`` / ``next_kind``
drive the "New"/deadline UI and the save snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import normalize_amount
from .status import opportunity_status

PIVOT_SOURCE = "pivot"

# Fellowships are never ingested under PIVOT_SOURCE — Pivot owns grants and
# conferences only; every fellowship carries the Illinois Fellowship Finder's own
# source id. Defined here (alongside PIVOT_SOURCE) rather than in ``.ingest`` so
# both this module and ``.ingest`` — which already imports from here — can share
# one definition without an import cycle. Drifting the two apart is exactly the
# failure mode that made ``extract_fellowship_constraints`` iterate an
# always-empty queryset (see Phase 2 of the migration plan).
FELLOWSHIP_SOURCE = "illinois-fellowship-finder"

# Area label (plural, as the tool uses it) -> ContentItem.type value.
AREA_TO_TYPE = {
    "grants": "grant",
    "conferences": "conference",
    "fellowships": "fellowship",
}


def _join(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())


def record_text(rec: dict, area: str) -> str:
    """The searchable document text (title/scope + context), per the tool."""
    if area == "grants":
        return _join(
            rec.get("title"),
            rec.get("sponsor"),
            rec.get("abstract"),
            rec.get("ai_summary"),
            rec.get("amount"),
            rec.get("matched_topics"),
        )
    if area == "fellowships":
        # Facet strings add discriminating vocabulary for vector/BM25 search.
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
    return _join(
        rec.get("name"),
        rec.get("scope"),
        rec.get("keywords"),
        rec.get("location"),
        rec.get("country"),
        rec.get("organizers"),
        rec.get("matched_subjects"),
    )


@dataclass
class PivotItem:
    """A normalized Pivot record ready to upsert into ``ContentItem``."""

    type: str  # "grant" | "conference" | "fellowship"
    external_id: str
    source_url: str
    title: str  # display title
    subtitle: str  # sponsor / "location, country" / award_class title-cased
    text: str  # embedding + BM25 document text
    metadata: dict = field(default_factory=dict)
    # "pivot" for grants/conferences; rec["source"] for fellowships
    source: str = PIVOT_SOURCE

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


def build_pivot_item(area: str, rec: dict, *, today: str) -> PivotItem | None:
    """Build a :class:`PivotItem` from a raw grant/conference/fellowship record.

    ``area`` is the tool's plural label ("grants" / "conferences" / "fellowships").
    Returns ``None`` for a record missing a stable id (can't dedup it) or for a
    fellowship record whose award_class is "grant" (the Pivot funding feed owns grants).
    """
    kind = AREA_TO_TYPE.get(area)
    if kind is None:
        raise ValueError(f"unknown Pivot area {area!r}")
    external_id = str(rec.get("id") or "").strip()
    if not external_id:
        return None

    if kind == "fellowship":
        # The Illinois site includes some grants; exclude them — Pivot owns grants.
        if (rec.get("award_class") or "").strip().lower() == "grant":
            return None
        return _build_fellowship_item(rec, external_id, today)

    status = opportunity_status(rec, area, today)

    if kind == "grant":
        title = (rec.get("title") or "").strip()
        subtitle = (rec.get("sponsor") or "").strip()
        deadline_date = status.get("apply_deadline") or ""
        prune_after = deadline_date  # a grant expires at its application deadline
        next_kind = "application" if deadline_date else ""
        # Some grants dump a budget paragraph into Amount; distill it to a concise
        # figure/range and feed the clean value to both metadata and record_text.
        amount = normalize_amount(rec.get("amount") or "")
        rec = {**rec, "amount": amount}
        metadata = {
            "title": title,
            "sponsor": subtitle,
            "amount": amount,
            "website": (rec.get("website") or "").strip(),
            "deadline": (rec.get("deadline") or "").strip(),
            "deadline_date": deadline_date,
            "matched_topics": (rec.get("matched_topics") or "").strip(),
            "ai_summary": (rec.get("ai_summary") or "").strip(),
            "abstract": (rec.get("abstract") or "").strip(),
        }
    else:  # conference
        location = (rec.get("location") or "").strip()
        country = (rec.get("country") or "").strip()
        title = (rec.get("name") or "").strip()
        subtitle = ", ".join(p for p in (location, country) if p)
        # Actionable submission deadline for display; event date drives expiry.
        deadline_date = status.get("next_deadline") or ""
        event_date = status.get("event_date") or ""
        next_kind = status.get("next_kind") or ("event" if event_date else "")
        prune_after = event_date
        metadata = {
            "name": title,
            "location": location,
            "country": country,
            "event_dates": (rec.get("event_dates") or "").strip(),
            "event_date": event_date,
            "deadlines": (rec.get("deadlines") or "").strip(),
            "deadline_date": deadline_date,
            "scope": (rec.get("scope") or "").strip(),
            "website": (rec.get("website") or "").strip(),
            "keywords": (rec.get("keywords") or "").strip(),
            "organizers": (rec.get("organizers") or "").strip(),
            "eligibility": (rec.get("eligibility") or "").strip(),
            "matched_subjects": (rec.get("matched_subjects") or "").strip(),
            "timeline": rec.get("timeline") or [],
            "abstract_open": status.get("abstract_open", False),
            "manuscript_open": status.get("manuscript_open", False),
        }

    metadata.update(
        {
            "prune_after": prune_after,
            "next_kind": next_kind,
            "status": status.get("status", "unknown"),
            "status_summary": status.get("summary", ""),
        }
    )
    return PivotItem(
        type=kind,
        external_id=external_id,
        source_url=(rec.get("url") or "").strip(),
        title=title,
        subtitle=subtitle,
        text=record_text(rec, area),
        metadata=metadata,
    )


def _build_fellowship_item(rec: dict, external_id: str, today: str) -> PivotItem:
    """Build a :class:`PivotItem` for one fellowship record.

    Called exclusively from :func:`build_pivot_item` when ``area == "fellowships"``.
    Grant exclusion is already done by the caller.
    """
    # Lazy imports keep the package import clean. Both modules live under
    # apps.scraper.eligibility (Phase 2 lifted them out of pivot/fellowships/,
    # which had nothing to do with Pivot).
    from apps.scraper.eligibility.constraints import extract_by_pattern
    from apps.scraper.eligibility.parsers import deadline_status, facets_incomplete

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

    return PivotItem(
        type="fellowship",
        external_id=external_id,
        source_url=source_url,
        title=title,
        subtitle=subtitle,
        text=record_text(rec, "fellowships"),
        metadata=metadata,
        source=rec_source,
    )

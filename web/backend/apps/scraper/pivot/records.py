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

from .status import opportunity_status

PIVOT_SOURCE = "pivot"

# Area label (plural, as the tool uses it) -> ContentItem.type value.
AREA_TO_TYPE = {"grants": "grant", "conferences": "conference"}


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

    type: str  # "grant" | "conference"
    external_id: str
    source_url: str
    title: str  # display title (grant title / conference name)
    subtitle: str  # sponsor (grant) / "location, country" (conference)
    text: str  # embedding + BM25 document text
    metadata: dict = field(default_factory=dict)

    @property
    def prune_after(self) -> str:
        """ISO date after which this item is expired (``""`` = never/unknown)."""
        return self.metadata.get("prune_after", "")

    @property
    def deadline_date(self) -> str:
        return self.metadata.get("deadline_date", "")


def build_pivot_item(area: str, rec: dict, *, today: str) -> PivotItem | None:
    """Build a :class:`PivotItem` from a raw grant/conference record.

    ``area`` is the tool's plural label ("grants" / "conferences"). Returns
    ``None`` for a record missing a stable id (can't dedup it).
    """
    kind = AREA_TO_TYPE.get(area)
    if kind is None:
        raise ValueError(f"unknown Pivot area {area!r}")
    external_id = str(rec.get("id") or "").strip()
    if not external_id:
        return None

    status = opportunity_status(rec, area, today)

    if kind == "grant":
        title = (rec.get("title") or "").strip()
        subtitle = (rec.get("sponsor") or "").strip()
        deadline_date = status.get("apply_deadline") or ""
        prune_after = deadline_date  # a grant expires at its application deadline
        next_kind = "application" if deadline_date else ""
        metadata = {
            "title": title,
            "sponsor": subtitle,
            "amount": (rec.get("amount") or "").strip(),
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

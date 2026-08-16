"""NSF funding feeds.

Worth a separate adapter despite the overlap, for a structural reason: NSF's own
policy framework recognizes four categories of funding opportunity — Dear
Colleague Letters, program descriptions, program announcements, and program
solicitations — and only *solicitations* reliably behave like a cross-posted
federal grant posting. The other three regularly carry real deadlines and real
money (supplements, fellowship pathways, rapid-response and exploratory
mechanisms) while never appearing on the anchor source at all. Program
descriptions in particular are often published only on a division page.

Two feeds are read:

* ``rss_www_funding_upcoming.xml`` — opportunities with an approaching due date,
  which is where the deadline lives;
* ``rss_www_funding_pgm_annc_inf.xml`` — newly published announcements.

The same opportunity appears in both, so they are merged on the publication
number before anything downstream sees them.

The briefing calls this the weakest of the US sources by volume and asks whether
the added records justify the adapter. ``collect delta --source nsf`` answers that
with a number rather than an opinion.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from apps.scraper.collect.core.http import FetchError, PoliteClient
from apps.scraper.collect.core.rawstore import RawBundle, new_run_id, utc_now
from apps.scraper.collect.grants.adapters.base import BaseAdapter
from apps.scraper.collect.grants.normalize import (
    clean_text,
    dedupe_preserving_order,
    html_to_text,
    to_iso_date,
)
from apps.scraper.collect.grants.record import Opportunity

UPCOMING_FEED = "https://www.nsf.gov/rss/rss_www_funding_upcoming.xml"
ANNOUNCEMENT_FEED = "https://www.nsf.gov/rss/rss_www_funding_pgm_annc_inf.xml"
FEEDS = {"upcoming": UPCOMING_FEED, "announcements": ANNOUNCEMENT_FEED}

#: A bare ``&`` that is not already the start of an entity. NSF's own feed ships
#: these — "Computational and Data-Enabled Science and Engineering (CDS&E)" — and
#: a bare ampersand is invalid XML, so a strict parser rejects the whole document
#: over one program title and the source contributes nothing at all.
_BARE_AMPERSAND = re.compile(rb"&(?!#?\w+;)")


def _repair_xml(payload: bytes) -> bytes:
    """Escape bare ampersands so one malformed title cannot cost the whole feed.

    Deliberately the narrowest possible repair: it fixes the single error this
    publisher actually makes and leaves every other malformation to fail loudly,
    because a parser that accepts anything tells you nothing about what it read.
    """
    return _BARE_AMPERSAND.sub(b"&amp;", payload)


#: Publication numbers follow a year-and-sequence pattern and are the dedupe key:
#: "PD 23-1650", "NSF 24-123", and the URL-slug form "pd23-1650".
PUB_NUMBER = re.compile(r"\b(NSF|PD|DCL)\s*[- ]?\s*(\d{2})-(\d{3,4})\b", re.IGNORECASE)

#: Every date label NSF puts in front of a deadline. They are not interchangeable
#: — a target date is advisory and a deadline is not — so the label is preserved
#: verbatim alongside the parsed date.
DATE_LABELS = (
    "Full Proposal Deadline",
    "Full Proposal Target Date",
    "Full Proposal Accepted Anytime",
    "Preliminary Proposal Deadline",
    "Letter of Intent Deadline",
    "Proposal Deadline",
    "Due Date",
)
_DATE_LINE = re.compile(
    r"(" + "|".join(re.escape(label) for label in DATE_LABELS) + r")\s*(?:\(s\))?\s*:?\s*"
    r"([A-Z][a-z]+ \d{1,2},\s*\d{4})",
    re.IGNORECASE,
)
_CATEGORY = re.compile(
    r"This is an NSF\s+(Program Announcement|Program Description|Program Solicitation|Dear Colleague Letter)",
    re.IGNORECASE,
)
#: "Accepted Anytime" is NSF's rolling mechanism. It must survive the prune, so it
#: has to be recognised rather than falling through as a missing date.
_ROLLING = re.compile(r"Accepted\s+Anytime", re.IGNORECASE)


class NSFAdapter(BaseAdapter):
    name = "nsf"
    funder_native = True
    phase = 4

    # -- stage 1 ----------------------------------------------------------

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        run_id = new_run_id()
        records: list[dict[str, Any]] = []
        errors: dict[str, str] = {}

        for feed_name, url in FEEDS.items():
            try:
                response = client.get(url)
            except FetchError as exc:
                errors[feed_name] = str(exc)
                continue
            try:
                root = ET.fromstring(_repair_xml(response.body))
            except ET.ParseError as exc:
                # One feed is not the source. NSF serves two, and losing both
                # because one is malformed is a bigger loss than the bad feed.
                errors[feed_name] = f"malformed XML: {exc}"
                continue
            for item in root.findall(".//item"):
                records.append(
                    {
                        "feed": feed_name,
                        "title": (item.findtext("title") or "").strip(),
                        "link": (item.findtext("link") or "").strip(),
                        "guid": (item.findtext("guid") or "").strip(),
                        "description": item.findtext("description") or "",
                        "pubDate": (item.findtext("pubDate") or "").strip(),
                    }
                )

        if limit:
            records = records[:limit]
        return self.bundle(self.name, run_id, utc_now(), records, feed_errors=errors)

    # -- stage 2 ----------------------------------------------------------

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        by_key: dict[str, Opportunity] = {}
        for row in bundle.records:
            if not isinstance(row, dict):
                continue
            record = self._parse_item(row)
            if record is None:
                continue
            existing = by_key.get(record.source_record_id)
            by_key[record.source_record_id] = (
                record if existing is None else _merge_feeds(existing, record)
            )
        return list(by_key.values())

    def _parse_item(self, row: dict[str, Any]) -> Opportunity | None:
        link = clean_text(row.get("link") or row.get("guid"))
        body = html_to_text(row.get("description"))
        number = _publication_number(row.get("description"), link)
        if not link:
            return None

        dates = _labelled_dates(body)
        rolling = bool(_ROLLING.search(body))
        parsed = dedupe_preserving_order([iso for _, iso in dates])
        close_date = None if rolling else (parsed[0] if parsed else None)

        return Opportunity(
            source=self.name,
            # Fall back to the URL when NSF omits the number: a program
            # description with no publication number is still a real opportunity.
            source_record_id=number or link,
            source_url=link,
            # An empty number means the record falls back to a source-local key
            # and can never merge with the same opportunity from anywhere else.
            # It was empty on 7 of 24 NSF records — and specifically on the
            # program descriptions that are the structural argument for having
            # this adapter at all. The URL slug is NSF's own stable identifier
            # for the programme, so it becomes the number rather than nothing.
            opportunity_number=number or _slug_identifier(link),
            record_kind="standalone",
            title=clean_text(row.get("title")),
            funder="National Science Foundation",
            funder_subunit=_directorate(body),
            description=body,
            # The directorate is the only subject signal NSF's feed carries; the
            # document kind and the date labels are metadata and have their own
            # homes, so they no longer masquerade as subjects here.
            categories=dedupe_preserving_order([_directorate(body)]),
            status="open",
            posted_date=to_iso_date(row.get("pubDate")),
            close_date=close_date,
            # For a rolling opportunity this is the only place the *reason* for a
            # null close date survives. "Accepted Anytime" is a deliberate NSF
            # mechanism, and losing the phrase makes it indistinguishable from a
            # date we simply failed to parse.
            close_date_text=(
                "Full Proposal Accepted Anytime"
                if rolling
                else "; ".join(f"{label}: {iso}" for label, iso in dates)
            ),
            additional_due_dates=[iso for iso in parsed if iso != close_date],
            currency="USD",
            agency_code="NSF",
            opportunity_category=_category(body),
            raw=row,
        )


# --- helpers -------------------------------------------------------------


def _merge_feeds(left: Opportunity, right: Opportunity) -> Opportunity:
    """Same opportunity seen in both feeds. Keep the richer half of each field."""
    merged = left.copy()
    if len(right.description) > len(merged.description):
        merged.description = right.description
    merged.close_date = merged.close_date or right.close_date
    merged.close_date_text = merged.close_date_text or right.close_date_text
    merged.opportunity_number = merged.opportunity_number or right.opportunity_number
    merged.posted_date = merged.posted_date or right.posted_date
    merged.additional_due_dates = dedupe_preserving_order(
        [*merged.additional_due_dates, *right.additional_due_dates, *([right.close_date] if right.close_date else [])]
    )
    merged.additional_due_dates = [d for d in merged.additional_due_dates if d != merged.close_date]
    merged.categories = dedupe_preserving_order([*merged.categories, *right.categories])
    merged.raw = {"feeds": [merged.raw, right.raw]}
    return merged


def _slug_identifier(link: str) -> str:
    """NSF's own programme slug, from the opportunity URL.

    ``.../opportunities/transport-phenomena/`` becomes ``NSF-TRANSPORT-PHENOMENA``.
    Prefixed so it is never mistaken for a publication number the funder issued,
    and uppercased so it normalizes the same way real numbers do.
    """
    path = [part for part in clean_text(link).rstrip("/").split("/") if part]
    if not path:
        return ""
    slug = path[-1]
    # The last segment is sometimes the publication id (pd23-1650); in that case
    # the programme slug is the segment before it.
    if re.fullmatch(r"(pd|nsf)?\d{2}-?\d{3,4}", slug, re.IGNORECASE) and len(path) > 1:
        slug = path[-2]
    return f"NSF-{slug.upper()}" if slug else ""


def _publication_number(*values: object) -> str:
    for value in values:
        if not value:
            continue
        match = PUB_NUMBER.search(str(value))
        if match:
            return f"{match.group(1).upper()} {match.group(2)}-{match.group(3)}"
    return ""


def _labelled_dates(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for match in _DATE_LINE.finditer(text):
        iso = to_iso_date(match.group(2))
        if iso:
            out.append((clean_text(match.group(1)), iso))
    return out


def _category(text: str) -> str:
    match = _CATEGORY.search(text)
    return clean_text(match.group(1)) if match else ""


def _directorate(text: str) -> str:
    match = re.search(r"Directorate for ([A-Za-z ,&]+)", text)
    return clean_text(f"Directorate for {match.group(1)}") if match else ""

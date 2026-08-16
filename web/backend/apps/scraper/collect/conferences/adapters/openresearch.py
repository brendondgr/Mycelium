"""openresearch: OpenResearch.org's forward-looking conference wiki, one request.

The cheapest source in the whole conferences briefing: a Semantic MediaWiki
``action=ask`` query against ``[[Submission deadline::>{cutoff}]]`` returns every
future-deadline record in one JSON response, fully populated, no auth, no key.
Measured 2026-08-16: 342 records, 409 KB, 2.6 seconds.

**The cost is what is missing, not what it takes to fetch.** No descriptions, no
timezone (every date is a bare calendar date at midnight UTC), no quality
signals (CORE rank, acceptance rate, attendee count are all 0% populated on
future records). This is a deadline-and-location spine, not a standalone
source — ``venue_native`` is False because the wikitext's own ``=== Sources
===`` sections cite OpenReview and dblp, so it is a transcription and must lose
to organiser-native text on descriptive fields at merge time.

**Geographic skew is a legitimacy signal, not a quirk.** Of the 342 records at
recon time, 166 (China 95 + Japan 71) came from those two countries alone — the
classic footprint of an aggregated Asia-Pacific CFP feed. That is exactly what
the trust layer downstream exists to weigh; this adapter's job is to transcribe
what the wiki says, flag what looks wrong (gotcha 6 below), and hand the rest
on rather than pre-judging it.

See ``docs/conferences/recon/scholarly_event_metadata.md`` for the full recon.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from apps.scraper.collect.conferences.adapters.base import BaseConferenceAdapter
from apps.scraper.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from apps.scraper.collect.conferences.timezones import to_iso_instant
from apps.scraper.collect.core.http import PoliteClient
from apps.scraper.collect.core.rawstore import RawBundle, new_run_id, utc_now
from apps.scraper.collect.core.text import clean_text

#: The script path is ``/mediawiki``, not ``/w`` and not the root -- the root
#: ``api.php`` 404s with a plain-text "File not found." body, not JSON, so a
#: JSON-decoding adapter dies with a confusing JSONDecodeError instead of a
#: clean, catchable error.
ASK_URL = "https://www.openresearch.org/mediawiki/api.php"

#: The printouts the pipeline needs, in query order. Anything added here shows
#: up in every record's ``printouts`` dict for free.
PRINTOUTS = (
    "Title",
    "Acronym",
    "Start date",
    "End date",
    "Submission deadline",
    "Abstract deadline",
    "Notification",
    "Camera ready due",
    "Has location city",
    "Has location country",
    "Homepage",
    "Event type",
    "Event in series",
    "Modification date",
)

#: How many days before "today" the query still reaches, so a deadline that
#: passed yesterday still arrives once and can be marked inactive downstream
#: instead of vanishing from the feed with no trace it ever existed.
GRACE_DAYS = 3

#: Measured 342 rows for the forward window -- comfortably under this in one
#: page. The server hard-caps at 10,000 rows per request regardless of what a
#: caller asks for, so the offset loop below is defensive: it will not fire at
#: current volume, which is exactly why it has to be written now rather than
#: discovered the day it does.
PAGE_LIMIT = 5000
HARD_CAP = 10_000

LICENSE_URL = "https://creativecommons.org/licenses/by-sa/2.0/de/"

_CATEGORY_PREFIX = re.compile(r"^Category:", re.IGNORECASE)
_YEAR_IN_TEXT = re.compile(r"\b(19|20)\d{2}\b")

#: Best-effort free-text country name -> ISO alpha-2, covering the countries
#: seen in the future-deadline cohort at recon time. OpenResearch publishes no
#: ISO code at all (recon gotcha 7) -- an unmapped name is left blank rather
#: than guessed, never invented.
_COUNTRY_NAME_TO_ISO: dict[str, str] = {
    "china": "CN", "japan": "JP", "vietnam": "VN", "usa": "US",
    "united states": "US", "united states of america": "US",
    "portugal": "PT", "france": "FR", "germany": "DE", "thailand": "TH",
    "south korea": "KR", "korea": "KR", "spain": "ES", "italy": "IT",
    "united kingdom": "GB", "uk": "GB", "canada": "CA", "india": "IN",
    "australia": "AU", "singapore": "SG", "malaysia": "MY", "indonesia": "ID",
    "brazil": "BR", "netherlands": "NL", "poland": "PL", "austria": "AT",
    "switzerland": "CH", "belgium": "BE", "greece": "GR", "turkey": "TR",
    "taiwan": "TW", "hong kong": "HK", "finland": "FI", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "ireland": "IE", "israel": "IL",
    "mexico": "MX", "new zealand": "NZ", "south africa": "ZA", "egypt": "EG",
    "saudi arabia": "SA", "united arab emirates": "AE", "russia": "RU",
    "czech republic": "CZ", "hungary": "HU", "romania": "RO",
}

#: Four fixed columns, submission-first because that is the one field the
#: whole "is this still open" filter reads (``record.py``'s SUBMISSION_TYPES).
_DEADLINE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("submission", "Submission deadline"),
    ("abstract", "Abstract deadline"),
    ("notification", "Notification"),
    ("camera_ready", "Camera ready due"),
)


class OpenResearchAdapter(BaseConferenceAdapter):
    name = "openresearch"
    # The wikitext's own "=== Sources ===" section cites OpenReview and dblp on
    # every record sampled -- this is a transcription of someone else's CFP
    # text, not the organisers' own words.
    venue_native = False
    phase = 3
    license = "CC-BY-SA-2.0-DE"

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        """One request in the common case; a defensive offset loop for the day
        the forward window exceeds 5000 rows."""
        cutoff = (datetime.now(UTC).date() - timedelta(days=GRACE_DAYS)).isoformat()

        records: list[dict[str, Any]] = []
        offset = 0
        pages = 0
        while True:
            response = client.get(_ask_url(cutoff, PAGE_LIMIT, offset))
            payload = response.json()
            results = ((payload or {}).get("query") or {}).get("results") or {}
            records.extend(_unwrap(results))
            pages += 1

            # meta.count is the number *returned*, never the number matched --
            # there is no total-results field anywhere in the ask response. A
            # full page is the only safe signal that more rows might exist.
            if len(results) < PAGE_LIMIT or offset + PAGE_LIMIT >= HARD_CAP:
                break
            offset += PAGE_LIMIT
            if limit is not None and len(records) >= limit:
                break

        if limit is not None:
            records = records[:limit]

        return self.bundle(
            self.name,
            new_run_id(),
            utc_now(),
            records,
            url=ASK_URL,
            cutoff=cutoff,
            pages=pages,
            license_url=LICENSE_URL,
        )

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        series_out: list[ConferenceSeries] = []
        instances_out: list[ConferenceInstance] = []
        for record in bundle.records:
            if not isinstance(record, dict):
                continue
            parsed = self._parse_record(record)
            if parsed is None:
                continue
            series, instance = parsed
            series_out.append(series)
            instances_out.append(instance)
        return series_out, instances_out

    # -- internals ----------------------------------------------------------

    def _parse_record(
        self, record: dict[str, Any]
    ) -> tuple[ConferenceSeries, ConferenceInstance] | None:
        printouts = record.get("printouts") or {}
        subject = clean_text(record.get("subject"))
        title = clean_text(_first(printouts.get("Title")))
        acronym = clean_text(_first(printouts.get("Acronym"))) or subject
        if not title and not acronym:
            return None  # nothing to key a record on

        start_date = _timestamp_to_date(_first(printouts.get("Start date")))
        end_date = _timestamp_to_date(_first(printouts.get("End date")))

        deadlines, warnings = _build_deadlines(printouts, start_date, self.name)

        series_ref = _first(printouts.get("Event in series"))
        series_name = (
            clean_text(series_ref.get("fulltext")) if isinstance(series_ref, dict) else ""
        )
        series_basis = series_name or acronym or title
        series_key = f"gen:openresearch:{series_basis.lower().replace(' ', '-')}"

        city = _first_fulltext(printouts.get("Has location city"))
        country_name = _CATEGORY_PREFIX.sub("", _first_fulltext(printouts.get("Has location country"))).strip()
        country_code = _COUNTRY_NAME_TO_ISO.get(country_name.lower(), "")

        event_type = clean_text(_first(printouts.get("Event type"))).lower()
        record_kind = "workshop" if event_type == "workshop" else "conference"

        year_label = _year_from(acronym) or _year_from(subject) or (start_date[:4] if start_date else "")

        series = ConferenceSeries(
            series_key=series_key,
            acronym=series_name or acronym,
            full_name=title,
            contributing_sources=[self.name],
            license=self.license,
        )

        instance = ConferenceInstance(
            source=self.name,
            source_record_id=subject,
            series_key=series_key,
            record_kind=record_kind,
            title=title,
            acronym=acronym,
            year_label=year_label,
            event_start=start_date,
            event_end=end_date,
            event_dates_text=_dates_text(start_date, end_date),
            city=city,
            country_code=country_code,
            place_text=", ".join(p for p in (city, country_name) if p),
            # `Homepage` is populated on only ~19% of records, and a record with
            # no link at all cannot be spot-checked against anything. The wiki
            # page always exists and is a real, resolvable page about this
            # venue, so it stands in — the conference's own site when we have
            # it, our provenance for it when we do not.
            url=clean_text(_first(printouts.get("Homepage")))
            or clean_text(record.get("fullurl")),
            source_url=clean_text(record.get("fullurl")),
            deadlines=deadlines,
            quality_warnings=warnings,
            contributing_sources=[self.name],
            license=self.license,
            raw=record,
        )
        return series, instance


# --- helpers ---------------------------------------------------------------


def _ask_url(cutoff: str, limit: int, offset: int = 0) -> str:
    """Build the ``action=ask`` URL with ``urlencode``, never string concat.

    A literal ``+`` reaching the server decodes as a space, turning
    ``[[X::+]]`` into "equals empty" and silently returning zero results at
    HTTP 200 -- verified live. ``urlencode`` is what keeps every special
    character in the query (``[``, ``]``, ``:``, ``|``, ``>``) honest.
    """
    parts = [f"[[Submission deadline::>{cutoff}]]"]
    parts.extend(f"?{name}" for name in PRINTOUTS)
    parts.append(f"limit={limit}")
    if offset:
        parts.append(f"offset={offset}")
    params = {"action": "ask", "format": "json", "query": "|".join(parts)}
    return f"{ASK_URL}?{urlencode(params)}"


def _unwrap(results: dict[str, Any]) -> list[dict[str, Any]]:
    """SMW's ``query.results`` is an object keyed by page title, not an array.

    Lift it into a list the same way ``eu_portal`` unwraps ``payload["results"]``
    -- ``{"subject": title, **value}`` for every row, no more.
    """
    return [{"subject": key, **value} for key, value in results.items() if isinstance(value, dict)]


def _first(values: Any) -> Any:
    """Every SMW printout value is a list, even single-valued ones."""
    if isinstance(values, list) and values:
        return values[0]
    return None


def _first_fulltext(values: Any) -> str:
    value = _first(values)
    if isinstance(value, dict):
        return clean_text(value.get("fulltext"))
    return ""


def _timestamp_to_moment(value: Any) -> datetime | None:
    """Unix epoch seconds -> UTC datetime. Never the ``raw`` field.

    ``raw`` is ``<calendar-model>/YYYY/M/D`` -- ``"1/2026/8/31"`` -- and
    splitting on ``/`` after dropping the leading ``1`` yields a plausible,
    wrong date the moment the calendar model field is anything but 1.
    ``timestamp`` is verified to decode to exact midnight UTC.
    """
    if not isinstance(value, dict):
        return None
    timestamp = value.get("timestamp")
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _timestamp_to_date(value: Any) -> str | None:
    moment = _timestamp_to_moment(value)
    return moment.date().isoformat() if moment else None


def _build_deadlines(
    printouts: dict[str, Any], start_date: str | None, source: str
) -> tuple[list[Deadline], list[str]]:
    deadlines: list[Deadline] = []
    warnings: list[str] = []

    for kind, field in _DEADLINE_COLUMNS:
        value = _first(printouts.get(field))
        if not isinstance(value, dict):
            continue
        moment = _timestamp_to_moment(value)
        deadline_date = moment.date().isoformat() if moment else None
        instant = to_iso_instant(moment)
        deadlines.append(
            Deadline(
                kind=kind,
                raw=str(value.get("raw", "")),
                instant=instant,
                # No timezone information exists anywhere in this source --
                # every date is a bare calendar date at midnight UTC. Never
                # asserted as a real basis, always flagged as our assumption.
                basis="inferred:date-only-utc",
                source=source,
            )
        )
        # Real records genuinely have a submission deadline months after the
        # event started (recon gotcha 6, verified: CARDIS 2026 deadline
        # 2026-12-12, start 2026-03-30). Flag rather than trust either field.
        if kind == "submission" and deadline_date and start_date and deadline_date > start_date:
            warnings.append(
                f"submission deadline {deadline_date} falls after the event start date {start_date}"
            )

    deadlines.sort(key=lambda d: d.instant or "9999")
    return deadlines, warnings


def _year_from(text: str) -> str:
    match = _YEAR_IN_TEXT.search(text or "")
    return match.group(0) if match else ""


def _dates_text(start: str | None, end: str | None) -> str:
    if start and end and start != end:
        return f"{start} to {end}"
    return start or end or ""

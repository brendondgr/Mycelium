"""ccf-deadlines: hand-curated CS conference deadlines, one HTTP request.

The best structured free deadline data available: explicit timezones, multi-round
already modelled correctly, three ranking systems attached, and a dblp venue key
on every single venue — which solves identity resolution for this source at zero
cost.

**Access.** A GitHub Actions job concatenates all 353 per-venue YAML files into
one published aggregate on every push, so the whole dataset is one GET of ~365 KB
in under a second, with ``ETag``/``Last-Modified`` giving a free 304.

Two dead ends worth recording so nobody re-discovers them:
``raw.githubusercontent.com/.../main/conference/allconf.yml`` is a **404** (the
aggregate is built onto a different repo's pages branch, never committed to
``main``), and ``ccfddl.top`` is an **unrelated login page**, not this project.

Per-file fetching is rejected outright: 354 requests, a dependency on the
60-request/hour unauthenticated GitHub API just to enumerate the files, and a
live risk of silently dropping ``conference/DB/pods/pods.yml``, which sits one
level deeper than the other 352 — deep enough that the project's own validator
has never checked it.

**Scope.** Narrow and CS-only: ten sub-fields, all computing. It will not cover
oceanography or clinical medicine. It is also far more valuable as a venue and
cadence reference than as a live CFP feed — 353 venues, but typically only
60–120 with a live deadline, swinging seasonally with the CS conference cycle.
"""

from __future__ import annotations

import re
from typing import Any

from apps.scraper.collect.conferences.adapters.base import BaseConferenceAdapter
from apps.scraper.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from apps.scraper.collect.conferences.timezones import (
    TimezoneBasisError,
    parse_basis,
    resolve_instant,
    to_iso_instant,
)
from apps.scraper.collect.core.http import PoliteClient
from apps.scraper.collect.core.rawstore import RawBundle, new_run_id, utc_now
from apps.scraper.collect.core.text import clean_text, dedupe_preserving_order

#: Everything that could change lives here, so a URL rename is a one-line fix.
BASE = "https://ccfddl.com/conference"
ALLCONF_URL = f"{BASE}/allconf.yml"
TYPES_URL = f"{BASE}/types.yml"
ACCEPT_RATES_URL = f"{BASE}/allacc.yml"

#: Failover, verified byte-identical to the primary.
ALLCONF_MIRROR = (
    "https://raw.githubusercontent.com/ccfddl/ccfddl.github.io/page/conference/allconf.yml"
)

#: The aggregate is ~365 KB. Anything dramatically smaller is an error page, not
#: data — GitHub Pages serves its 404 with HTTP 200 in some configurations.
MIN_ALLCONF_BYTES = 50_000

#: Sub-field codes, vendored from ``conference/types.yml``. Ten codes, all CS,
#: and the file is 905 bytes — small and stable enough that vendoring beats
#: spending a request on it. Refreshed if the fetch of TYPES_URL succeeds.
SUBFIELDS: dict[str, str] = {
    "DS": "Computer Architecture/Parallel Programming/Storage Technology",
    "NW": "Network System",
    "SC": "Network and System Security",
    "SE": "Software Engineering/Operating System/Programming Language Design",
    "DB": "Database/Data Mining/Information Retrieval",
    "CT": "Computing Theory",
    "CG": "Graphics",
    "AI": "Artificial Intelligence",
    "HI": "Computer-Human Interaction",
    "MX": "Interdiscipline/Mixture/Emerging",
}

#: Ranking systems the file carries. None of them records an edition year — the
#: schema has no version field at all — so the edition is left empty rather than
#: invented. A dated CORE rank comes from CORE's own portal instead.
RANK_SYSTEMS = ("ccf", "core", "thcpl")

#: Keys we understand inside a timeline row. Anything else is logged rather than
#: dropped: the upstream schema sets no ``additionalProperties``, so a typo'd
#: ``abstract deadline`` (space, not underscore) already passes validation
#: upstream and is silently ignored by every consumer.
KNOWN_TIMELINE_KEYS = frozenset({"deadline", "abstract_deadline", "comment"})

_ORDINAL = re.compile(r"^\s*(\d+(?:st|nd|rd|th))\s+", re.IGNORECASE)
_YEAR_IN_TEXT = re.compile(r"\b(19|20)\d{2}\b")
_VIRTUAL = re.compile(r"\b(virtual|online)\b", re.IGNORECASE)
_HYBRID = re.compile(r"\bhybrid\b", re.IGNORECASE)


class CCFDeadlinesAdapter(BaseConferenceAdapter):
    name = "ccf_deadlines"
    #: Hand-curated from each venue's own CFP by contributors who read it. Not
    #: the organisers themselves, but far closer to the source than a scrape.
    venue_native = True
    phase = 0
    license = "MIT"

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        """One request for everything, with a mirror as failover."""
        from apps.scraper.collect.core.http import FetchError

        try:
            response = client.get(ALLCONF_URL, min_bytes=MIN_ALLCONF_BYTES)
            url = ALLCONF_URL
        except FetchError:
            response = client.get(ALLCONF_MIRROR, min_bytes=MIN_ALLCONF_BYTES)
            url = ALLCONF_MIRROR

        venues = _load_yaml(response.text())
        if not isinstance(venues, list):
            raise ValueError(f"{url}: expected a YAML sequence of venues")

        # Optional, and never fatal: a failure here costs sub-field labels and
        # acceptance rates, not deadlines.
        subfields: dict[str, str] = {}
        try:
            types = _load_yaml(client.get(TYPES_URL).text())
            subfields = {
                row["sub"]: row.get("name_en") or row.get("name") or ""
                for row in types or []
                if isinstance(row, dict) and row.get("sub")
            }
        except Exception:  # noqa: BLE001 - a labels miss must not sink the run
            subfields = {}

        if limit is not None:
            venues = venues[:limit]

        return self.bundle(
            self.name,
            new_run_id(),
            utc_now(),
            venues,
            url=url,
            venue_count=len(venues),
            subfields=subfields or SUBFIELDS,
        )

    def parse(
        self, bundle: RawBundle
    ) -> tuple[list[ConferenceSeries], list[ConferenceInstance]]:
        subfields = bundle.meta.get("subfields") or SUBFIELDS
        venues = [
            venue
            for venue in bundle.records
            if isinstance(venue, dict) and venue.get("title")
        ]

        # The dblp key is a good join key but NOT a primary key: ccs.yml and
        # asiaccs.yml both declare `dblp: ccs` upstream. Keying on it alone
        # merges CCS and AsiaCCS into one series — two real venues silently
        # collapsed, which is the exact failure this system exists to prevent.
        # So a key shared by more than one title gets disambiguated by acronym.
        shared = _shared_dblp_keys(venues)

        series_out: list[ConferenceSeries] = []
        instances_out: list[ConferenceInstance] = []
        for venue in venues:
            series, instances = self._parse_venue(venue, subfields, shared)
            series_out.append(series)
            instances_out.extend(instances)

        return series_out, instances_out

    # -- internals --------------------------------------------------------

    def _parse_venue(
        self,
        venue: dict[str, Any],
        subfields: dict[str, str],
        shared_keys: frozenset[str] = frozenset(),
    ) -> tuple[ConferenceSeries, list[ConferenceInstance]]:
        title = clean_text(venue.get("title"))
        dblp_key = clean_text(venue.get("dblp"))
        sub = clean_text(venue.get("sub"))

        # (title, dblp) rather than either alone. `title` collides twice — two
        # SEC, two FSE (Fast Software Encryption vs Foundations of Software
        # Engineering) — and `dblp` collides once, with ccs/asiaccs both
        # claiming `ccs`. The pair is unique across all 353 venues.
        series_key = _series_key(title, dblp_key, shared_keys)

        rankings: dict[str, dict[str, str]] = {}
        for system in RANK_SYSTEMS:
            value = clean_text((venue.get("rank") or {}).get(system))
            # "N" means "not ranked by this system", which is a real statement
            # and different from the field being absent.
            if value:
                rankings[system] = {"rank": value, "edition": ""}

        series = ConferenceSeries(
            series_key=series_key,
            acronym=title,
            full_name=clean_text(venue.get("description")),
            field_codes=[sub] if sub else [],
            rankings=rankings,
            # The dblp key is published directly, so no acronym matching is
            # needed for this source at all. `dblp_found` stays False until the
            # registry stage confirms the key actually resolves.
            dblp_key=f"conf/{dblp_key}" if dblp_key else "",
            contributing_sources=[self.name],
            license=self.license,
        )
        if sub and sub in subfields:
            series.name_variants = [subfields[sub]]

        instances = [
            self._parse_instance(conf, series, title, dblp_key)
            for conf in (venue.get("confs") or [])
            if isinstance(conf, dict)
        ]
        return series, [i for i in instances if i is not None]

    def _parse_instance(
        self,
        conf: dict[str, Any],
        series: ConferenceSeries,
        title: str,
        dblp_key: str,
    ) -> ConferenceInstance | None:
        year = conf.get("year")
        conf_id = clean_text(conf.get("id"))
        if year is None and not conf_id:
            return None

        warnings: list[str] = []
        basis_label = clean_text(conf.get("timezone")) or "AoE"
        try:
            parse_basis(basis_label)
        except TimezoneBasisError:
            # Never guess. Record the unusable basis and leave the deadlines
            # undated rather than silently defaulting to UTC.
            warnings.append(f"unrecognised timezone basis: {basis_label!r}")

        deadlines, timeline_warnings = _parse_timeline(conf.get("timeline") or [], basis_label,
                                                       self.name)
        warnings.extend(timeline_warnings)

        place_text = clean_text(conf.get("place"))
        dates_text = clean_text(conf.get("date"))

        # `year` is not reliable: sigmetrics27 carries year 2025 with a date of
        # June 2027, and six instances contradict their own date string. Use it
        # for grouping only, and record the disagreement.
        year_label = str(year) if year is not None else _year_from(dates_text) or ""
        text_year = _year_from(dates_text)
        if text_year and year_label and text_year != year_label:
            warnings.append(f"year {year_label} disagrees with date text {dates_text!r}")

        # (title, dblp, year, id) — unique across all 1,161 instances. `id`
        # alone collides seven times (the two FSEs, and ica3pp reused unsuffixed
        # for four different years).
        record_id = f"{title}|{dblp_key}|{year_label}|{conf_id}"

        return ConferenceInstance(
            source=self.name,
            source_record_id=record_id,
            series_key=series.series_key,
            record_kind="conference",
            title=series.full_name or title,
            acronym=title,
            year_label=year_label,
            # No machine-readable event start/end exists in this source at all:
            # `date` is free text with 131 distinct format skeletons. Storing the
            # verbatim string and leaving the parsed fields null is honest;
            # guessing would produce confidently wrong event dates.
            event_dates_text=dates_text,
            place_text=place_text,
            city=_city_from(place_text),
            country_code=_country_from(place_text),
            is_virtual=bool(_VIRTUAL.search(place_text)),
            is_hybrid=bool(_HYBRID.search(place_text)),
            url=clean_text(conf.get("link")),
            source_url=clean_text(conf.get("link")),
            topics=list(series.field_codes),
            deadlines=deadlines,
            quality_warnings=dedupe_preserving_order(warnings),
            contributing_sources=[self.name],
            license=self.license,
            raw=conf,
        )


# --- helpers -------------------------------------------------------------


def _load_yaml(text: str) -> Any:
    """Parse with ``safe_load``, never the default loader.

    ``safe_load`` is what keeps an unquoted date a ``datetime`` rather than
    something worse, and keeps arbitrary tags from constructing objects.
    """
    import yaml

    return yaml.safe_load(text)


def _shared_dblp_keys(venues: list[dict[str, Any]]) -> frozenset[str]:
    """dblp keys claimed by more than one distinct venue title in this source."""
    titles_by_key: dict[str, set[str]] = {}
    for venue in venues:
        key = clean_text(venue.get("dblp"))
        if key:
            titles_by_key.setdefault(key, set()).add(clean_text(venue.get("title")))
    return frozenset(key for key, titles in titles_by_key.items() if len(titles) > 1)


def _series_key(title: str, dblp_key: str, shared_keys: frozenset[str] = frozenset()) -> str:
    if dblp_key and dblp_key not in shared_keys:
        return f"conf/{dblp_key}"
    if dblp_key:
        # Two venues claim this key upstream. Keep both, distinguished by
        # acronym, rather than letting one overwrite the other. The registry
        # stage will resolve at most one of them to the real dblp venue.
        return f"conf/{dblp_key}:{title.lower().replace(' ', '-')}"
    return f"gen:ccf:{title.lower().replace(' ', '-')}"


def _parse_timeline(
    timeline: list[Any], basis: str, source: str
) -> tuple[list[Deadline], list[str]]:
    """Turn a timeline array into ordered, typed, deduplicated deadlines."""
    out: list[Deadline] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()

    for index, row in enumerate(timeline):
        if not isinstance(row, dict):
            continue

        unknown = set(row) - KNOWN_TIMELINE_KEYS
        if unknown:
            # A typo'd key upstream passes schema validation and is ignored by
            # every consumer. Say so rather than joining them.
            warnings.append(f"unknown timeline keys in round {index + 1}: {sorted(unknown)}")

        comment = clean_text(row.get("comment"))
        abstract_raw = row.get("abstract_deadline")
        deadline_raw = row.get("deadline")

        abstract_instant = _instant(abstract_raw, basis)
        deadline_instant = _instant(deadline_raw, basis)

        # Four instances have a deadline *year* that is simply wrong (EuroVis
        # 2026's is off by two years), which a plain `deadline > now` filter
        # drops silently. Comparing against the abstract date catches exactly
        # this class for free.
        if abstract_instant and deadline_instant and abstract_instant > deadline_instant:
            warnings.append(
                f"round {index + 1}: abstract deadline {abstract_raw!r} falls after "
                f"the full deadline {deadline_raw!r} — likely a wrong year upstream"
            )

        for kind, raw_value, instant_value in (
            ("abstract", abstract_raw, abstract_instant),
            ("submission", deadline_raw, deadline_instant),
        ):
            if raw_value is None:
                continue
            label = comment or (f"round {index + 1}" if len(timeline) > 1 else "")
            identity = (kind, label.lower())
            if identity in seen:
                # Several instances repeat a deadline value verbatim.
                continue
            seen.add(identity)
            out.append(
                Deadline(
                    kind=kind,
                    raw=str(raw_value),
                    instant=instant_value,
                    basis=basis,
                    round_label=label,
                    source=source,
                )
            )

    # Never assume timeline[0] is the earliest: SAC/sac26 and ISSRE/issre23 are
    # both out of chronological order upstream.
    out.sort(key=lambda d: (d.instant or "9999", d.kind))
    return out, warnings


def _instant(value: Any, basis: str) -> str | None:
    try:
        return to_iso_instant(resolve_instant(value, basis))
    except TimezoneBasisError:
        return None


def _year_from(text: str) -> str | None:
    match = _YEAR_IN_TEXT.search(text or "")
    return match.group(0) if match else None


def _city_from(place: str) -> str:
    """First comma-separated component, which is the city in the common case.

    ``place`` has 622 distinct values and no structure — "Vancouver, British
    Columbia, Canada" sits beside "Singapore EXPO" and "Málaga, Spain (hybrid)".
    The verbatim string is kept regardless; this is a convenience, not a claim.
    """
    if not place:
        return ""
    head = place.split(",")[0].strip()
    return "" if _VIRTUAL.fullmatch(head) else head


#: Deliberately tiny. The briefing says normalize to a country code plus a
#: free-text city and explicitly not to attempt geocoding in a prototype.
_COUNTRY_HINTS = {
    "usa": "US", "united states": "US", "u.s.a.": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "scotland": "GB",
    "canada": "CA", "china": "CN", "japan": "JP", "korea": "KR",
    "south korea": "KR", "india": "IN", "germany": "DE", "france": "FR",
    "italy": "IT", "spain": "ES", "australia": "AU", "singapore": "SG",
    "netherlands": "NL", "sweden": "SE", "switzerland": "CH", "austria": "AT",
    "belgium": "BE", "greece": "GR", "portugal": "PT", "brazil": "BR",
    "ireland": "IE", "israel": "IL", "poland": "PL", "denmark": "DK",
    "finland": "FI", "norway": "NO", "czech republic": "CZ", "hungary": "HU",
    "turkey": "TR", "mexico": "MX", "chile": "CL", "argentina": "AR",
    "new zealand": "NZ", "vietnam": "VN", "thailand": "TH", "malaysia": "MY",
    "indonesia": "ID", "taiwan": "TW", "hong kong": "HK", "uae": "AE",
    "luxembourg": "LU",
}


def _country_from(place: str) -> str:
    if not place:
        return ""
    tail = place.split(",")[-1].strip().lower()
    tail = re.sub(r"\s*\(.*\)$", "", tail).strip()
    return _COUNTRY_HINTS.get(tail, "")

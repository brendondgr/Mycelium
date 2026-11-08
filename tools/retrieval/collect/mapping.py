"""Map an open-collector record to a ``ContentItem``-shaped payload.

This is the **port contract** between the open collector's grant/conference
schema and Mycelium's unified :class:`~tools.retrieval.models.ContentItem`. It
replaces :mod:`apps.scraper.pivot.records` (plan Phase 3), which did the
equivalent job for Pivot-RP's flat dict records. The collector's records are
typed dataclasses (:class:`~tools.retrieval.collect.grants.record.Opportunity`,
:class:`~tools.retrieval.collect.conferences.record.ConferenceInstance` /
:class:`~tools.retrieval.collect.conferences.record.ConferenceSeries`) rather than
loosely-shaped dicts, so this module reads dataclass attributes directly instead
of ``rec.get(...)``.

**This module is pure.** No ORM, no network, no Django model import — a record
in, a plain ``dict`` out. Phase 4's ingest step is the only thing that knows how
to turn that dict into a database write, and Phase 8's extraction step is the
only thing that knows how to turn ``metadata["description"]``/``["cfp_text"]``
into a verified ``metadata["ai_summary"]``. Keeping this module ignorant of both
is what makes it independently testable with a plain dataclass literal and no
Postgres.

Every mapper returns (or, for a filtered grant, may return ``None`` in place of)
a dict shaped ``{type, source, external_id, source_url, text, metadata}``:

* ``type`` — ``"grant"`` or ``"conference"`` (the ``ContentItem.Type`` value,
  spelled out rather than imported — importing ``tools.retrieval.models`` here
  would pull Django's app registry into a module that has no business needing
  it).
* ``source`` — ``f"grants:{adapter}"`` / ``f"conf:{adapter}"``, so the feed can
  always tell a Pivot-era row from an open-collector one even mid-migration.
* ``external_id`` — the collector's own upsert key (``stable_key`` /
  ``instance_key``), carried through unchanged so Phase 4's
  ``(source, external_id)`` upsert lines up with what the collector itself
  considers "the same record".
* ``text`` — a searchable join over the record's descriptive fields. This is a
  **pre-extraction** fallback: Phase 8 embeds ``metadata["search_text"]``
  (the verified LLM extraction) once it exists, and only a refused record ever
  falls back to something built from raw text — see plan D9/§8.4. This field is
  that raw-text basis, not a substitute for it.
* ``metadata`` — everything else: display fields, deadline data, and every
  signal (rankings, trust tier, licence, source links) the collector carries
  that Pivot never did.

Two rules run through every field below and are worth stating once rather than
re-justifying at each site:

1. **``deadline_date`` (what a reader sees) and ``prune_after`` (what expiry
   keys on) are computed separately and are allowed to differ.** Conflating
   them is the bug this phase exists to fix — see ``_grant_deadlines`` and
   ``_conference_deadlines``.
2. **Nothing here reads the clock.** ``today`` (grants) and ``now``
   (conferences) are always caller-supplied, so every function is a pure
   function of its arguments and testable without freezing time.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, date, datetime
from typing import Any

from tools.retrieval.collect.conferences.record import (
    SUBMISSION_TYPES,
    ConferenceInstance,
    ConferenceSeries,
)
from tools.retrieval.collect.grants.normalize import (
    clean_dates,
    html_to_text,
    last_due,
    select_next_due,
)
from tools.retrieval.collect.grants.record import Opportunity

__all__ = ["map_conference", "map_grant"]


def _join(*parts: object) -> str:
    """Space-join non-empty parts. The same idiom ``pivot/records.py`` used."""
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())


# --------------------------------------------------------------------------- #
# Grants
# --------------------------------------------------------------------------- #

#: Grants carry no per-adapter licence field on the dataclass itself — unlike
#: ``ConferenceAdapter``, whose ``license`` attribute is copied onto every
#: instance it emits (see ``conferences/adapters/base.py``), nothing in
#: ``grants/adapters`` declares one. So the mapper carries this table instead of
#: reading one off the record. Every one of the five US federal sources
#: (``grants_gov``, ``sam_gov``, ``nih_guide``, ``nsf``, ``sbir``) publishes a US
#: government work: no copyright attaches under 17 U.S.C. § 105, so "public
#: domain" is a statement of law, not a courtesy label picked for this project.
#: ``eu_portal`` is the one non-federal grant source (plan D5) and carries the
#: European Commission's own reuse decision instead. An adapter not in this
#: table (a future addition) gets ``""`` rather than a guess.
_US_GOV_WORK = "US Government Work — no copyright (17 U.S.C. § 105); public domain"
_EU_REUSE = (
    "© European Union, reuse authorised under Commission Decision "
    "2011/833/EU (free reuse with source attribution)"
)
GRANT_LICENSES: dict[str, str] = {
    "grants_gov": _US_GOV_WORK,
    "sam_gov": _US_GOV_WORK,
    "nih_guide": _US_GOV_WORK,
    "nsf": _US_GOV_WORK,
    "sbir": _US_GOV_WORK,
    "eu_portal": _EU_REUSE,
}

#: USD and EUR are the only two currencies the live corpus carries (1,581 /
#: 609 of 2,190). A third currency falls back to "<CODE> " rather than a
#: guessed symbol — never invent a sign for money we cannot read correctly.
_CURRENCY_SYMBOLS: dict[str, str] = {"USD": "$", "EUR": "€"}


def _money(value: float, currency: str) -> str:
    symbol = _CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    return f"{symbol}{round(value):,}"


def _amount_text(record: Opportunity) -> str:
    """The single figure/range a reader sees — deliberately floor/ceiling only.

    ``total_program_funding`` is the whole call's budget pool, not what any one
    award is worth (the measured ERASMUS case: ``total_program_funding`` =
    68,000,000 with no per-award floor or ceiling at all). Folding it in here
    when the per-award figures are missing would overstate what an applicant
    can expect to receive. It is still carried numerically
    (``metadata["total_program_funding"]``) for a reader who wants the pool
    size — just never blended into the headline amount.
    """
    floor, ceiling = record.award_floor, record.award_ceiling
    if floor is None and ceiling is None:
        return ""
    if floor is not None and ceiling is not None and floor != ceiling:
        return f"{_money(floor, record.currency)}–{_money(ceiling, record.currency)}"
    value = ceiling if ceiling is not None else floor
    return _money(value, record.currency)  # type: ignore[arg-type]


def _grant_deadlines(record: Opportunity, today: date) -> tuple[str, str, list[str]]:
    """The core fix (plan Phase 3): ``deadline_date`` and ``prune_after`` differ.

    ``rounds`` is every known application round — ``close_date`` plus
    ``additional_due_dates`` — cleaned through :func:`clean_dates` rather than
    read straight off the dataclass, so a non-ISO or unparseable stray value
    can never survive into a lexicographic-compare expiry check (the collector
    should already emit zero-padded ISO throughout, but this is the one place
    a bad date would silently stop something from ever expiring, so it is
    worth the second pass).

    ``deadline_date`` (what a reader is shown) and ``prune_after`` (what expiry
    keys on) are then computed with the two existing, already-tested
    ``normalize`` helpers that this exact ambiguity was built to resolve —
    :func:`select_next_due` picks the next unpassed round, falling back to the
    latest if every round has passed; :func:`last_due` is always the final
    round. Reusing them rather than re-deriving the same rule here is
    deliberate: the EU-portal-shows-first-round / NIH-shows-last-round bug this
    guards against was already fixed once, in one place, and duplicating the
    logic risks re-diverging it.

    On 173 of 2,190 live rows ``deadline_date != prune_after`` — a multi-round
    grant (e.g. ``num:PAR25144``, 10 rounds) that conflates them is deleted, and
    its paid-for LLM verdict CASCADEs away, the moment its *first* round passes.
    """
    rounds = clean_dates([record.close_date, *record.additional_due_dates])
    deadline_date = select_next_due(rounds, today) or ""
    prune_after = last_due(rounds) or ""
    return deadline_date, prune_after, rounds


def _grant_text(title: str, record: Opportunity, description: str) -> str:
    return _join(
        title,
        record.funder_canonical or record.funder,
        description,
        record.eligibility,
        " ".join(record.categories),
        _amount_text(record),
    )


def map_grant(record: Opportunity, *, today: date) -> dict[str, Any] | None:
    """One :class:`Opportunity` -> a ``ContentItem``-shaped dict, or ``None``.

    Returns ``None`` for ``record_kind == "overlay"`` — 4 of 2,190 live rows,
    NIH policy notices that carry no deadline of their own and point at a
    parent announcement rather than being an applicable opportunity in their
    own right. Everything else, including ``"topic"`` records (the EU portal's
    sub-calls, each independently applicable), passes through.
    """
    if record.record_kind == "overlay":
        return None

    # 95 of 2,190 titles carry HTML entities, including a zero-width space
    # (``&#8203;``) that silently breaks substring matching downstream.
    title = html.unescape(record.title)
    deadline_date, prune_after, rounds = _grant_deadlines(record, today)
    amount = _amount_text(record)
    # ``html_to_text`` also unescapes entities and strips any markup, which
    # matters for eu_portal: its ``description`` carries literal HTML
    # fragments (measured — see docs/plans, Phase 8 §8.1) that would otherwise
    # sit raw in both the embedding basis and the "raw text" fallback that a
    # refused Phase 8 extraction lands on.
    description = html_to_text(record.description)

    metadata: dict[str, Any] = {
        "title": title,
        "funder": record.funder,
        "funder_subunit": record.funder_subunit,
        "funder_canonical": record.funder_canonical,
        "agency_code": record.agency_code,
        "opportunity_number": record.opportunity_number,
        "record_kind": record.record_kind,
        "status": record.status,
        "description": description,
        "eligibility": record.eligibility,
        "categories": list(record.categories),
        "applicant_types": list(record.applicant_types),
        "funding_instruments": list(record.funding_instruments),
        "activity_codes": list(record.activity_codes),
        "assistance_listings": list(record.assistance_listings),
        "cost_sharing": record.cost_sharing,
        "opportunity_category": record.opportunity_category,
        "action_types": list(record.action_types),
        "topic_keywords": list(record.topic_keywords),
        "participating_units": list(record.participating_units),
        "related_numbers": list(record.related_numbers),
        "amount": amount,
        "award_floor": record.award_floor,
        "award_ceiling": record.award_ceiling,
        "total_program_funding": record.total_program_funding,
        "expected_awards": record.expected_awards,
        "currency": record.currency,
        # The core fix (module docstring, point 1): these two are allowed to
        # differ, and on 173 of 2,190 rows they do.
        "deadline_date": deadline_date,
        "prune_after": prune_after,
        "due_dates": rounds,
        "deadline_text": record.close_date_text,
        "dates_inferred": record.dates_inferred,
        "original_deadline": record.original_close_date or "",
        "loi_date": record.intent_date or "",
        "loi_date_text": record.intent_date_text,
        # A NEW key, deliberately not "first_seen" — that field belongs to the
        # New-pin logic (when *Mycelium* first ingested this row), which is a
        # different fact from when the funder posted it. GrantSerializer.
        # get_posted currently conflates the two; Phase 9 repoints it here.
        "published_on": record.posted_date or "",
        "license": GRANT_LICENSES.get(record.source, ""),
        "contributing_sources": sorted(set(record.contributing_sources)),
    }

    return {
        "type": "grant",
        "source": f"grants:{record.source}",
        "external_id": record.stable_key,
        "source_url": record.source_url,
        "text": _grant_text(title, record, description),
        "metadata": metadata,
    }


# --------------------------------------------------------------------------- #
# Conferences
# --------------------------------------------------------------------------- #

#: CS sub-field codes, ported verbatim from
#: ``conferences/adapters/ccf_deadlines.SUBFIELDS`` — the only place this
#: glossary exists anywhere in the collector. ``ccf_deadlines`` series
#: ``field_codes`` and instance ``topics`` are CCF area codes (SC DS AI SE DB CG
#: NW MX HI CT), not English topic words; a card that renders "AI" in a topic
#: chip list reads as a typo, not artificial intelligence.
SUBFIELD_NAMES: dict[str, str] = {
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

#: ISO 3166-1 alpha-2 -> full country name, for the codes the live corpus
#: carries (verified against ``conferences.db``: 41 distinct codes) plus a
#: modest margin of other common ones. The frontend's ``continentOf()`` keys on
#: lower-cased *full* country names (``COUNTRY_TO_CONTINENT`` in
#: ``conference-filters.tsx``); ``country_code`` alone buckets every record to
#: "Other". An unrecognised code falls back to the code itself (never to an
#: empty string) — still visible and filterable, just not continent-bucketed,
#: which is the same graceful-degradation the frontend map already applies.
COUNTRY_NAMES: dict[str, str] = {
    "AE": "United Arab Emirates",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "BE": "Belgium",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "CO": "Colombia",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "EE": "Estonia",
    "EG": "Egypt",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GR": "Greece",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "LU": "Luxembourg",
    "MX": "Mexico",
    "MY": "Malaysia",
    "NL": "Netherlands",
    "NO": "Norway",
    "NZ": "New Zealand",
    "PH": "Philippines",
    "PL": "Poland",
    "PT": "Portugal",
    "QA": "Qatar",
    "RO": "Romania",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "TH": "Thailand",
    "TR": "Turkey",
    "TW": "Taiwan",
    "UA": "Ukraine",
    "US": "United States",
    "VN": "Vietnam",
    "ZA": "South Africa",
}

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


def _country_name(code: str) -> str:
    upper = (code or "").strip().upper()
    if not upper:
        return ""
    return COUNTRY_NAMES.get(upper, upper)


def _subfield_names(codes: list[str]) -> list[str]:
    return [SUBFIELD_NAMES.get(code, code) for code in codes]


def _normalize_url(url: str) -> str:
    """Scheme-normalise a URL that may arrive bare.

    A real value: ``"www.novasworkshop.org"`` has no scheme at all. Left
    as-is, an ``<a href="www.novasworkshop.org">`` resolves *relative to our
    own origin*, silently turning an external link into a broken internal
    one. A URL that already names a scheme (``http``, ``https``, even
    something unusual) is left untouched; everything else is assumed
    ``https``.
    """
    stripped = (url or "").strip()
    if not stripped:
        return ""
    if _SCHEME_RE.match(stripped):
        return stripped
    return f"https://{stripped}"


def _dedupe_acronym_year(acronym: str, year_label: str) -> str:
    """Strip a trailing ``" <year_label>"`` off an acronym.

    OpenReview acronyms embed the edition year directly (``"NOVAS 2026"``) and
    the record carries that same year again, separately, as ``year_label``.
    Left alone, a card renders "NOVAS 2026 2026".
    """
    acronym = acronym.strip()
    year_label = (year_label or "").strip()
    if not year_label:
        return acronym
    stripped = re.sub(rf"\s+{re.escape(year_label)}$", "", acronym).strip()
    return stripped or acronym


def _parse_instant(value: str | None) -> datetime | None:
    """Parse a stored UTC instant string to an aware ``datetime``, or ``None``.

    Same parsing approach as
    :func:`tools.retrieval.collect.conferences.timezones.is_future` (which this
    module deliberately does not import, because it returns only a bool and
    what ``_conference_deadlines`` needs is the parsed moment itself, to sort
    and to take the max of): ``datetime.fromisoformat`` after swapping the
    trailing ``Z`` for an explicit offset. 24 of 3,196 live deadlines carry
    microseconds (``openreview``'s millisecond-epoch source), which
    ``strptime("%Y-%m-%dT%H:%M:%SZ")`` raises on — ``fromisoformat`` handles
    both shapes.

    Parsing to a real ``datetime`` rather than taking a lexicographic
    min/max of the instant *strings* is deliberate too: an ISO string with a
    fractional-second component sorts as text *before* one without it at the
    same integer second (``.`` is ``0x2E``, ``Z`` is ``0x5A``), so a record
    whose deadlines mix microsecond-precision and whole-second instants would
    silently pick the wrong one under a string comparison. No live record
    mixes the two today (checked directly against the corpus), but nothing
    about the schema prevents it, and this is exactly the kind of landmine the
    zero-padding rule elsewhere in this module exists to avoid.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _conference_deadlines(
    instance: ConferenceInstance, now: datetime
) -> tuple[str, str, bool]:
    """``deadline_date`` gates on submission-type dates only, never the event.

    Only ``abstract`` and ``submission`` deadlines count as "the venue is still
    open to me" (``SUBMISSION_TYPES``, shared with the record model rather than
    redeclared here) — a record whose only future date is a ``notification`` is
    CLOSED, because notification is something the venue does *to* a submitter,
    not something a submitter can still act on. ``prune_after`` keys on the
    *last* deadline of any kind (a camera-ready or registration date can
    legitimately be the latest thing on the record), falling back to the event
    date only when the record carries no dated deadline at all.
    """
    submission_moments = [
        moment
        for d in instance.deadlines
        if d.kind in SUBMISSION_TYPES
        and (moment := _parse_instant(d.instant)) is not None
    ]
    future = [moment for moment in submission_moments if moment >= now]
    next_submission = min(future) if future else None
    deadline_date = next_submission.date().isoformat() if next_submission else ""

    all_moments = [
        moment
        for d in instance.deadlines
        if (moment := _parse_instant(d.instant)) is not None
    ]
    if all_moments:
        prune_after = max(all_moments).date().isoformat()
    else:
        prune_after = instance.event_end or instance.event_start or ""

    return deadline_date, prune_after, bool(deadline_date)


def _rank_badges(rankings: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    """Flatten ``{system: {rank, edition}}`` to ``[{system, rank, edition}]``.

    Sorted by system so the frontend never has to parse a dict (plan Phase 3).
    ``"N"`` means "not ranked by this system" — a real statement, not an
    absence — so it stays in the raw ``rankings`` JSON but is excluded here:
    a badge is a claim of rank, and "not ranked" is not one.
    """
    badges = [
        {
            "system": system,
            "rank": info.get("rank", ""),
            "edition": info.get("edition", ""),
        }
        for system, info in rankings.items()
        if info.get("rank") and info["rank"] != "N"
    ]
    return sorted(badges, key=lambda badge: badge["system"])


def _source_links(instance: ConferenceInstance) -> list[dict[str, str]]:
    """One attribution entry per contributing source.

    The record carries a single merged ``url``/``source_url`` — dedupe
    resolves any conflict between sources before this module ever sees the
    record — not one URL per contributor, so every entry here shares that URL;
    what varies is which source is being credited. That is sufficient for an
    attribution footer, the only consumer (plan Phase 10).
    """
    url = instance.source_url or instance.url
    sources = sorted(set(instance.contributing_sources))
    return [{"source": src, "url": url} for src in sources]


def _conference_text(
    name: str,
    acronym: str,
    series: ConferenceSeries | None,
    instance: ConferenceInstance,
) -> str:
    return _join(
        name,
        acronym,
        series.full_name if series else "",
        instance.place_text,
        _country_name(instance.country_code),
        instance.cfp_text,
        " ".join(_subfield_names(instance.topics)),
    )


def map_conference(
    instance: ConferenceInstance, series: ConferenceSeries | None, *, now: datetime
) -> dict[str, Any]:
    """One :class:`ConferenceInstance` (+ its :class:`ConferenceSeries`, if
    resolved) -> a ``ContentItem``-shaped dict.

    Mycelium has no series concept, so every quality signal that lives on the
    series in the collector's own schema — rankings, trust tier, registry
    presence, red flags — is denormalised onto the instance's ``metadata``
    here. ``series`` is ``None`` for an instance whose resolve stage never
    matched it to a series (an unresolved record); every series-derived field
    then takes its "nothing known yet" default rather than raising.

    ``now`` must be timezone-aware (UTC) — every deadline instant this module
    reads is stored as an aware UTC instant, and comparing it against a naive
    ``now`` raises.
    """
    acronym = _dedupe_acronym_year(html.unescape(instance.acronym), instance.year_label)
    fallback_name = (series.full_name if series else "") or acronym
    name = html.unescape(instance.title) or fallback_name
    url = _normalize_url(instance.url)
    deadline_date, prune_after, is_open = _conference_deadlines(instance, now)
    rankings = series.rankings if series else {}

    metadata: dict[str, Any] = {
        # Deliberately "name", not "title" — briefing._showcase_item and the
        # FTS trigger both read this exact key (grants use "title" instead).
        "name": name,
        "acronym": acronym,
        "year_label": instance.year_label,
        "record_kind": instance.record_kind,
        "parent_instance_key": instance.parent_instance_key,
        "event_start": instance.event_start or "",
        "event_end": instance.event_end or "",
        "event_dates_text": instance.event_dates_text,
        "city": instance.city,
        "country_code": instance.country_code,
        "country": _country_name(instance.country_code),
        "place_text": instance.place_text,
        "is_virtual": instance.is_virtual,
        "is_hybrid": instance.is_hybrid,
        "url": url,
        "cfp_text": instance.cfp_text,
        "topics": _subfield_names(instance.topics),
        "topic_codes": list(instance.topics),
        # The core fix, conference half (module docstring, point 1): these two
        # are computed independently and the event date never drives either.
        "deadline_date": deadline_date,
        "prune_after": prune_after,
        "open": is_open,
        "deadlines_structured": [d.to_json() for d in instance.deadlines],
        "rankings": rankings,
        "rank_badges": _rank_badges(rankings),
        "red_flags": list(series.red_flags) if series else [],
        "quality_warnings": list(instance.quality_warnings),
        "series_key": instance.series_key,
        "license": instance.license,
        "source_links": _source_links(instance),
        "indexed_years": series.indexed_years if series else 0,
        "dblp_key": series.dblp_key if series else "",
        "dblp_found": series.dblp_found if series else False,
        "acronym_variants": list(series.acronym_variants) if series else [],
        "name_variants": list(series.name_variants) if series else [],
        "field_codes": list(series.field_codes) if series else [],
        "contributing_sources": sorted(set(instance.contributing_sources)),
    }

    return {
        "type": "conference",
        "source": f"conf:{instance.source}",
        "external_id": instance.instance_key,
        "source_url": instance.source_url or url,
        "text": _conference_text(name, acronym, series, instance),
        "metadata": metadata,
    }

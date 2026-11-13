"""Tests for :mod:`tools.retrieval.collect.mapping`.

Every fixture below is either a real record pulled from the live collector
stores (`data/collect/{opportunities,conferences}.db` under the repository
root, queried directly while writing this file) or, where the plan calls for a case
that does not currently exist on live data (the notification-only-future
conference), a hand-built record in the same real shape — flagged as such at
the point of use, the same way ``EXP-2026-08-007`` hand-built its
``unsupported_claim`` cases rather than only trusting an absent signal.

No Django settings are touched: :mod:`tools.retrieval.collect.mapping` is pure, so
this suite runs as plain pytest against dataclass literals — no ``pytest.mark.
django_db``, no fixtures beyond the ones defined here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from tools.retrieval.collect.grants.record import Opportunity
from tools.retrieval.collect.mapping import map_conference, map_grant

TODAY = date(2026, 8, 16)
NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Grants
# --------------------------------------------------------------------------- #


def test_multi_round_grant_deadline_date_and_prune_after_differ():
    """``num:PAR25144`` — real NIH record, 10 rounds (live corpus row).

    This is the core fix: a grant whose next round is 2026-10-05 but whose
    final round is 2028-01-07 must show the near date and expire on the far
    one. The pre-fix code set both to the same value, which deleted this
    record — and its LLM verdict — the moment the *first* round passed.
    """
    record = Opportunity(
        source="nih_guide",
        source_record_id="41710",
        opportunity_number="PAR-25-144",
        title="Dissemination and Implementation Research in Health (R01)",
        funder="National Institutes of Health",
        funder_canonical="National Institutes of Health",
        posted_date="2024-10-29",
        close_date="2028-01-07",
        close_date_text="Jan 07, 2028 12:00:00 AM EST",
        additional_due_dates=[
            "2025-02-05",
            "2025-06-05",
            "2025-10-05",
            "2026-02-05",
            "2026-06-05",
            "2026-10-05",
            "2027-02-05",
            "2027-06-05",
            "2027-10-05",
        ],
        dates_inferred=True,
        currency="USD",
    )

    item = map_grant(record, today=TODAY)

    assert item is not None
    assert item["metadata"]["deadline_date"] == "2026-10-05"
    assert item["metadata"]["prune_after"] == "2028-01-07"
    assert item["metadata"]["deadline_date"] != item["metadata"]["prune_after"]
    assert item["metadata"]["due_dates"][0] == "2025-02-05"
    assert item["metadata"]["due_dates"][-1] == "2028-01-07"
    assert len(item["metadata"]["due_dates"]) == 10
    assert item["external_id"] == "num:PAR25144"
    assert item["source"] == "grants:nih_guide"


def test_posted_date_never_drives_expiry():
    """``num:PD981670`` — real NSF record. Posted 2015, single round 2026-08-17.

    ``published_on`` must carry the 2015 posting date for display while
    ``prune_after`` keys on the close date alone — proving the two are wired
    to genuinely different source fields, not the same one read twice.
    """
    record = Opportunity(
        source="nsf",
        source_record_id="PD 98-1670",
        opportunity_number="PD 98-1670",
        title="Chemical Oceanography",
        funder="National Science Foundation",
        posted_date="2015-03-13",
        close_date="2026-08-17",
        award_floor=200_000.0,
        award_ceiling=2_000_000.0,
        total_program_funding=26_000_000.0,
        currency="USD",
    )

    item = map_grant(record, today=TODAY)

    assert item["metadata"]["published_on"] == "2015-03-13"
    assert item["metadata"]["deadline_date"] == "2026-08-17"
    assert item["metadata"]["prune_after"] == "2026-08-17"
    assert item["metadata"]["prune_after"] != item["metadata"]["published_on"]
    assert item["metadata"]["amount"] == "$200,000–$2,000,000"
    # total_program_funding is carried numerically but never blended into the
    # headline "amount" — it is the whole call's pool, not one award's size.
    assert item["metadata"]["total_program_funding"] == 26_000_000.0


def test_rolling_grant_never_expires():
    """A real EU-portal shape: ``close_date`` null, no additional rounds.

    ``prune_after`` must be ``""`` — the sentinel the plan defines as "rolling,
    never expires" — not a guessed date.
    """
    record = Opportunity(
        source="eu_portal",
        source_record_id="EUROPEAID/170893/IDACT/RS",
        opportunity_number="EUROPEAID/170893/IDACT/RS",
        record_kind="topic",
        title="Support in strengthening of relevant institutions",
        funder="European Commission",
        close_date=None,
        additional_due_dates=[],
        currency="EUR",
    )

    item = map_grant(record, today=TODAY)

    assert item["metadata"]["deadline_date"] == ""
    assert item["metadata"]["prune_after"] == ""
    assert item["metadata"]["due_dates"] == []


def test_overlay_records_are_dropped():
    """4 of 2,190 live rows are NIH policy notices with no deadline of their
    own. They must not enter the feed as applicable opportunities."""
    record = Opportunity(
        source="nih_guide",
        source_record_id="NOT-OD-26-088",
        opportunity_number="NOT-OD-26-088",
        record_kind="overlay",
        title="Request for Information (RFI) on Proposed Changes",
        close_date=None,
    )

    assert map_grant(record, today=TODAY) is None


def test_topic_records_are_not_dropped():
    """Only ``overlay`` is filtered — a ``topic`` record (the EU portal's
    sub-calls) is independently applicable and must pass through."""
    record = Opportunity(
        source="eu_portal",
        source_record_id="HORIZON-CL5-1",
        opportunity_number="HORIZON-CL5-1",
        record_kind="topic",
        title="A topic call",
    )

    assert map_grant(record, today=TODAY) is not None


def test_title_html_entities_are_unescaped():
    """A real Grants.gov title (``num:PAR27032``). Left as literal markup, a
    substring search for the clean apostrophe form never matches."""
    record = Opportunity(
        source="grants_gov",
        source_record_id="1",
        title=(
            "Maximizing Investigators&rsquo; Research Award (MIRA) for Early "
            "Stage Investigators (ESI)"
        ),
    )

    item = map_grant(record, today=TODAY)

    assert item["metadata"]["title"] == (
        "Maximizing Investigators’ Research Award (MIRA) for Early "
        "Stage Investigators (ESI)"
    )
    assert "&rsquo;" not in item["metadata"]["title"]


def test_zero_width_space_entity_is_unescaped_too():
    """A real Grants.gov title (``num:HHS2026ACFACYFCY0016``).

    ``&#8203;`` is a zero-width space entity. Unescaping turns the literal
    7-character entity text into the single invisible ``\\u200b`` character it
    denotes, so a copy-pasted search string containing the real character (as
    a reader would copy it off the rendered funder page) becomes matchable
    against our stored title, where before it was fighting literal markup.
    """
    raw_record = Opportunity(
        source="grants_gov",
        source_record_id="2",
        title="&#8203;&#8203;FY 2026 Basic Center Program&#8203;",
    )

    item = map_grant(raw_record, today=TODAY)

    zwsp = "​"
    expected = f"{zwsp}{zwsp}FY 2026 Basic Center Program{zwsp}"
    assert item["metadata"]["title"] == expected
    assert "&#8203;" not in item["metadata"]["title"]


def test_license_is_public_domain_for_us_federal_and_reuse_terms_for_eu():
    us_record = Opportunity(source="nih_guide", source_record_id="1", title="x")
    eu_record = Opportunity(source="eu_portal", source_record_id="1", title="x")
    unknown_record = Opportunity(
        source="some_future_source", source_record_id="1", title="x"
    )

    us_item = map_grant(us_record, today=TODAY)
    eu_item = map_grant(eu_record, today=TODAY)
    unknown_item = map_grant(unknown_record, today=TODAY)

    assert "public domain" in us_item["metadata"]["license"]
    assert "2011/833/EU" in eu_item["metadata"]["license"]
    assert unknown_item["metadata"]["license"] == ""


def test_currency_is_never_summed_across_usd_and_eur():
    usd_record = Opportunity(
        source="nsf",
        source_record_id="1",
        title="x",
        currency="USD",
        award_floor=100.0,
        award_ceiling=100.0,
    )
    eur_record = Opportunity(
        source="eu_portal",
        source_record_id="1",
        title="x",
        currency="EUR",
        award_floor=100.0,
        award_ceiling=100.0,
    )

    usd_item = map_grant(usd_record, today=TODAY)
    eur_item = map_grant(eur_record, today=TODAY)

    assert usd_item["metadata"]["currency"] == "USD"
    assert usd_item["metadata"]["amount"] == "$100"
    assert eur_item["metadata"]["currency"] == "EUR"
    assert eur_item["metadata"]["amount"] == "€100"


# --------------------------------------------------------------------------- #
# Conferences
# --------------------------------------------------------------------------- #

#: The real VLDB 2027 deadline list (24 entries, ``ccf_deadlines``), read
#: verbatim off the live ``conferences.db`` store. (kind, raw, instant,
#: round_label); basis is "PT" and source is "ccf_deadlines" throughout.
_VLDB_2027_ROUNDS: list[tuple[str, str, str, str]] = [
    ("abstract", "2026-03-25 17:00:00", "2026-03-26T00:00:00Z", "round 1"),
    ("submission", "2026-04-01 17:00:00", "2026-04-02T00:00:00Z", "round 1"),
    ("abstract", "2026-04-25 17:00:00", "2026-04-26T00:00:00Z", "round 2"),
    ("submission", "2026-05-01 17:00:00", "2026-05-02T00:00:00Z", "round 2"),
    ("abstract", "2026-05-25 17:00:00", "2026-05-26T00:00:00Z", "round 3"),
    ("submission", "2026-06-01 17:00:00", "2026-06-02T00:00:00Z", "round 3"),
    ("abstract", "2026-06-25 17:00:00", "2026-06-26T00:00:00Z", "round 4"),
    ("submission", "2026-07-01 17:00:00", "2026-07-02T00:00:00Z", "round 4"),
    ("abstract", "2026-07-25 17:00:00", "2026-07-26T00:00:00Z", "round 5"),
    ("submission", "2026-08-01 17:00:00", "2026-08-02T00:00:00Z", "round 5"),
    ("abstract", "2026-08-25 17:00:00", "2026-08-26T00:00:00Z", "round 6"),
    ("submission", "2026-09-01 17:00:00", "2026-09-02T00:00:00Z", "round 6"),
    ("abstract", "2026-09-25 17:00:00", "2026-09-26T00:00:00Z", "round 7"),
    ("submission", "2026-10-01 17:00:00", "2026-10-02T00:00:00Z", "round 7"),
    ("abstract", "2026-10-25 17:00:00", "2026-10-26T00:00:00Z", "round 8"),
    ("submission", "2026-11-01 17:00:00", "2026-11-02T01:00:00Z", "round 8"),
    ("abstract", "2026-11-25 17:00:00", "2026-11-26T01:00:00Z", "round 9"),
    ("submission", "2026-12-01 17:00:00", "2026-12-02T01:00:00Z", "round 9"),
    ("abstract", "2026-12-25 17:00:00", "2026-12-26T01:00:00Z", "round 10"),
    ("submission", "2027-01-01 17:00:00", "2027-01-02T01:00:00Z", "round 10"),
    ("abstract", "2027-01-25 17:00:00", "2027-01-26T01:00:00Z", "round 11"),
    ("submission", "2027-02-01 17:00:00", "2027-02-02T01:00:00Z", "round 11"),
    ("abstract", "2027-02-25 17:00:00", "2027-02-26T01:00:00Z", "round 12"),
    ("submission", "2027-03-01 17:00:00", "2027-03-02T01:00:00Z", "round 12"),
]


def _vldb_2027() -> ConferenceInstance:
    deadlines = [
        Deadline(
            kind=kind,
            raw=raw,
            instant=instant,
            basis="PT",
            round_label=round_label,
            source="ccf_deadlines",
        )
        for kind, raw, instant, round_label in _VLDB_2027_ROUNDS
    ]
    return ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="International Conference on Very Large Data Bases|vldb|2027|",
        series_key="conf/vldb",
        title="International Conference on Very Large Data Bases",
        acronym="VLDB",
        year_label="2027",
        deadlines=deadlines,
        contributing_sources=["ccf_deadlines"],
        license="MIT",
    )


def test_24_round_conference_deadline_date_and_prune_after():
    """The real VLDB 2027 instance — 24 deadlines, PT basis (DST-sensitive)."""
    instance = _vldb_2027()

    item = map_conference(instance, series=None, now=NOW)

    assert len(item["metadata"]["deadlines_structured"]) == 24
    # As of NOW (Aug 16 noon), round 5's submission (Aug 2) has passed and
    # round 6's abstract (Aug 26) is the soonest submission-type date left.
    assert item["metadata"]["deadline_date"] == "2026-08-26"
    # prune_after is the *last* deadline of any kind, round 12's submission.
    assert item["metadata"]["prune_after"] == "2027-03-02"
    assert item["metadata"]["open"] is True


def test_microsecond_instant_does_not_crash_parsing():
    """A real OpenReview shape (``CAp/Conference|2026``): millisecond-epoch
    raw values resolve to instants with a fractional-second component, which
    ``strptime("%Y-%m-%dT%H:%M:%SZ")`` raises on."""
    instance = ConferenceInstance(
        source="openreview",
        source_record_id="CAp/Conference|2026",
        title="Conférence sur l'Apprentissage automatique (CAp)",
        acronym="CAp",
        year_label="2026",
        deadlines=[
            Deadline(
                kind="submission",
                raw="1779227986900",
                instant="2026-05-19T21:59:46.900000Z",
                basis="UTC",
                source="openreview",
            )
        ],
    )

    # The instant itself (May 2026) is real; a "now" fixed at the same date
    # every other test uses (Aug 2026) would already be past it, so this test
    # supplies its own earlier "now" purely to keep the deadline in the future.
    earlier_now = datetime(2026, 1, 1, tzinfo=UTC)
    item = map_conference(instance, series=None, now=earlier_now)

    assert item["metadata"]["deadline_date"] == "2026-05-19"
    assert item["metadata"]["open"] is True


def test_aoe_deadline_is_read_as_already_resolved():
    """A real ccf_deadlines shape (``conf/acml|2026``, "Journal Track" round).

    The AoE-to-UTC conversion itself happens upstream, at adapter parse time
    (``timezones.resolve_instant``) — by the time a record reaches this
    module, ``Deadline.instant`` is already the resolved UTC instant, and
    ``basis`` is retained only for display/audit. This test's job is only to
    confirm an AoE-basis deadline participates in the rule exactly like any
    other resolved instant.
    """
    instance = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="acml|2026",
        title="Asian Conference on Machine Learning",
        acronym="ACML",
        year_label="2026",
        deadlines=[
            Deadline(
                kind="submission",
                raw="2026-06-20 23:59:59",
                instant="2026-06-21T11:59:59Z",
                basis="AoE",
                round_label="Journal Track",
                source="ccf_deadlines",
            )
        ],
    )

    earlier_now = datetime(2026, 1, 1, tzinfo=UTC)
    item = map_conference(instance, series=None, now=earlier_now)

    assert item["metadata"]["deadline_date"] == "2026-06-21"


def test_a_notification_only_future_date_is_closed():
    """Hand-built: no live record currently has this exact shape (checked
    directly against the corpus), but the rule must hold regardless — a
    ``notification`` date is something the venue does *to* a submitter, not
    something a submitter can still act on, so it must never make a record
    read as open."""
    instance = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="synthetic|2027",
        title="Synthetic Venue",
        acronym="SYN",
        year_label="2027",
        deadlines=[
            # Every submission-type date is in the past...
            Deadline(kind="submission", instant="2026-01-01T00:00:00Z"),
            # ...but notification is still ahead of NOW.
            Deadline(kind="notification", instant="2027-01-01T00:00:00Z"),
        ],
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["deadline_date"] == ""
    assert item["metadata"]["open"] is False
    # prune_after still keys on the latest deadline of *any* kind.
    assert item["metadata"]["prune_after"] == "2027-01-01"


def test_conference_title_key_is_name_not_title():
    """``briefing._showcase_item`` and the FTS trigger both read ``"name"``
    specifically; grants use ``"title"`` instead. Getting this backwards is a
    silent breakage, not an error."""
    instance = ConferenceInstance(
        source="ccf_deadlines", source_record_id="1", title="A Conference", acronym="AC"
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["name"] == "A Conference"
    assert "title" not in item["metadata"]


def test_conference_title_html_entities_are_unescaped():
    instance = ConferenceInstance(
        source="society_pages",
        source_record_id="1",
        title="Institutional Development Award &amp; Translational Research",
        acronym="IDEA",
    )

    item = map_conference(instance, series=None, now=NOW)

    assert "&amp;" not in item["metadata"]["name"]
    assert "&" in item["metadata"]["name"]


def test_openreview_acronym_year_duplication_is_removed():
    """A real OpenReview record: ``gen:openreview:VLDB.org/Workshop/NOVAS|2026
    |workshop``. Left alone, a card reads "NOVAS 2026 2026"."""
    instance = ConferenceInstance(
        source="openreview",
        source_record_id="VLDB.org/Workshop/NOVAS|2026",
        title="2nd Novel Optimizations for Visionary AI Systems Workshop at VLDB 2026",
        acronym="NOVAS 2026",
        year_label="2026",
        url="www.novasworkshop.org",
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["acronym"] == "NOVAS"
    assert item["metadata"]["name"] == (
        "2nd Novel Optimizations for Visionary AI Systems Workshop at VLDB 2026"
    )


def test_bare_url_is_scheme_normalized():
    """A real value: ``"www.novasworkshop.org"`` has no scheme at all. Left
    alone, an ``<a href>`` resolves relative to our own origin."""
    instance = ConferenceInstance(
        source="openreview", source_record_id="1", url="www.novasworkshop.org"
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["url"] == "https://www.novasworkshop.org"


def test_url_that_already_has_a_scheme_is_left_alone():
    instance = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="1",
        url="http://aaai.org/Conferences/AAAI-22/",
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["url"] == "http://aaai.org/Conferences/AAAI-22/"


def test_country_code_gets_a_mapped_full_name_and_keeps_the_code():
    """A real value: ``country_code = "GR"``. The frontend's ``continentOf()``
    keys on lower-cased *full* country names; the raw code alone buckets
    every conference to "Other"."""
    instance = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="1",
        country_code="GR",
        place_text="Athens, Greece",
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["country_code"] == "GR"
    assert item["metadata"]["country"] == "Greece"


def test_unrecognised_country_code_falls_back_to_the_code_not_blank():
    instance = ConferenceInstance(
        source="ccf_deadlines", source_record_id="1", country_code="XK"
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["country"] == "XK"


def test_ccf_area_codes_are_expanded_to_readable_topic_names():
    """A real value: ``topics = ["AI"]`` (the AAAI ccf_deadlines instance) is a
    CCF sub-field code, not an English topic word."""
    instance = ConferenceInstance(
        source="ccf_deadlines", source_record_id="1", topics=["AI"]
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["topics"] == ["Artificial Intelligence"]
    assert item["metadata"]["topic_codes"] == ["AI"]


def test_rank_badges_flatten_and_exclude_unranked():
    """A real series: AAAI (``ccf: A``, ``core: A*``, ``thcpl: A``)."""
    series = ConferenceSeries(
        series_key="conf/aaai",
        acronym="AAAI",
        rankings={
            "ccf": {"rank": "A", "edition": ""},
            "core": {"rank": "A*", "edition": ""},
            "thcpl": {"rank": "A", "edition": ""},
        },
    )
    instance = ConferenceInstance(source="ccf_deadlines", source_record_id="1")

    item = map_conference(instance, series=series, now=NOW)

    assert item["metadata"]["rank_badges"] == [
        {"system": "ccf", "rank": "A", "edition": ""},
        {"system": "core", "rank": "A*", "edition": ""},
        {"system": "thcpl", "rank": "A", "edition": ""},
    ]
    # The raw rankings JSON is untouched.
    assert item["metadata"]["rankings"]["ccf"]["rank"] == "A"


def test_n_is_excluded_from_badges_but_kept_in_raw_rankings():
    """A real series: ACCV (``ccf: C``, ``core: B``, ``thcpl: N``). "N" means
    "not ranked by this system", not a rank of its own."""
    series = ConferenceSeries(
        series_key="conf/accv",
        acronym="ACCV",
        rankings={
            "ccf": {"rank": "C", "edition": ""},
            "core": {"rank": "B", "edition": ""},
            "thcpl": {"rank": "N", "edition": ""},
        },
    )
    instance = ConferenceInstance(source="ccf_deadlines", source_record_id="1")

    item = map_conference(instance, series=series, now=NOW)

    systems_with_badges = {badge["system"] for badge in item["metadata"]["rank_badges"]}
    assert "thcpl" not in systems_with_badges
    assert item["metadata"]["rankings"]["thcpl"]["rank"] == "N"


def test_unresolved_series_gets_safe_defaults_not_a_crash():
    """An instance whose resolve stage never matched it to a series."""
    instance = ConferenceInstance(source="wikicfp", source_record_id="1")

    item = map_conference(instance, series=None, now=NOW)

    assert "trust_tier" not in item["metadata"]
    assert item["metadata"]["rank_badges"] == []
    assert item["metadata"]["indexed_years"] == 0
    assert item["metadata"]["dblp_found"] is False


def test_series_license_passes_through_unchanged():
    """Unlike grants, conferences already carry a per-adapter ``license`` on
    the record itself (every ``ConferenceAdapter`` declares one) — no lookup
    table needed here."""
    instance = ConferenceInstance(
        source="ccf_deadlines", source_record_id="1", license="MIT"
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["license"] == "MIT"


def test_source_links_credit_every_contributing_source():
    instance = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="1",
        source_url="https://ccfddl.com/conference/aaai.html",
        contributing_sources=["ccf_deadlines", "openreview"],
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["metadata"]["source_links"] == [
        {"source": "ccf_deadlines", "url": "https://ccfddl.com/conference/aaai.html"},
        {"source": "openreview", "url": "https://ccfddl.com/conference/aaai.html"},
    ]


def test_external_id_and_source_prefix():
    instance = ConferenceInstance(
        source="ccf_deadlines",
        source_record_id="1",
        series_key="conf/aaai",
        year_label="2027",
    )

    item = map_conference(instance, series=None, now=NOW)

    assert item["external_id"] == "conf/aaai|2027|conference"
    assert item["source"] == "conf:ccf_deadlines"

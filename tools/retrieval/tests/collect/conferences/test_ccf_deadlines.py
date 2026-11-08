"""The ccf-deadlines adapter, and the five guards its live data forced.

Each guard here exists because the real corpus contains a defect that would
otherwise fail silently. The fixture is trimmed from the live aggregate and keeps
one instance of each.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tools.retrieval.collect.conferences.adapters.ccf_deadlines import (
    CCFDeadlinesAdapter,
    _city_from,
    _country_from,
    _parse_timeline,
)
from tools.retrieval.collect.conferences.pipeline import ConferencePipeline

TODAY = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def parsed(ccf_bundle):
    series, instances = CCFDeadlinesAdapter().parse(ccf_bundle)
    return series, {i.instance_key: i for i in instances}


# --- identity ------------------------------------------------------------


def test_the_two_unrelated_fses_stay_separate_series(parsed):
    """`title` alone collides twice in the live corpus.

    FSE is both Fast Software Encryption (security) and Foundations of Software
    Engineering. Keying on title would silently merge a cryptography venue into
    a software-engineering one.
    """
    series, _ = parsed
    fses = [s for s in series if s.acronym == "FSE"]
    assert len(fses) == 2
    assert {s.series_key for s in fses} == {"conf/fse", "conf/sigsoft"}
    # And they carry genuinely different quality, which proves they are not the
    # same venue seen twice.
    assert {s.rankings["ccf"]["rank"] for s in fses} == {"A", "B"}


def test_the_series_key_is_the_dblp_key_because_the_source_publishes_it(parsed):
    """All 353 venues carry a dblp key, so identity resolution is free here."""
    series, _ = parsed
    assert {s.series_key for s in series} >= {"conf/sigmod", "conf/vldb", "conf/aaai"}
    assert all(s.dblp_key for s in series)


def test_ccs_and_asiaccs_stay_separate_despite_sharing_a_dblp_key():
    """The dblp key is a good join key but not a primary key.

    ccs.yml and asiaccs.yml both declare `dblp: ccs` upstream. Keying on it
    alone silently merged two unrelated security conferences into one series --
    caught on the first live run against the real 353-venue aggregate.
    """
    from tools.retrieval.tests.collect.conferences.conftest import bundle

    venues = [
        {
            "title": "CCS",
            "description": "ACM Conference on Computer and Communications Security",
            "sub": "SC",
            "rank": {"ccf": "A"},
            "dblp": "ccs",
            "confs": [{"year": 2027, "id": "ccs27", "timeline": [{"deadline": "2027-01-01 23:59:59"}], "timezone": "AoE"}],
        },
        {
            "title": "AsiaCCS",
            "description": "Asia Conference on Computer and Communications Security",
            "sub": "SC",
            "rank": {"ccf": "C"},
            "dblp": "ccs",
            "confs": [{"year": 2027, "id": "asiaccs27", "timeline": [{"deadline": "2027-02-01 23:59:59"}], "timezone": "AoE"}],
        },
    ]
    series, instances = CCFDeadlinesAdapter().parse(bundle("ccf_deadlines", venues))

    assert len({s.series_key for s in series}) == 2, "two venues must stay two series"
    assert len({i.instance_key for i in instances}) == 2
    # The shared key is still visible in both, so the registry stage can try to
    # resolve whichever one genuinely owns it.
    assert all(s.dblp_key == "conf/ccs" for s in series)


def test_an_unshared_dblp_key_is_used_bare():
    """Disambiguation must not fire on the 351 venues that are fine."""
    from tools.retrieval.collect.conferences.adapters.ccf_deadlines import _series_key

    assert _series_key("SIGMOD", "sigmod", frozenset()) == "conf/sigmod"
    assert _series_key("CCS", "ccs", frozenset({"ccs"})) == "conf/ccs:ccs"


def test_instance_keys_are_unique(parsed):
    """`id` alone collides seven times upstream (both FSEs, and ica3pp reused
    unsuffixed for four different years)."""
    _, instances = parsed
    assert len(instances) == 11


# --- multi-round ---------------------------------------------------------


def test_vldb_produces_twelve_rounds_each_with_an_abstract_and_a_deadline(parsed):
    """The deepest multi-round venue in the corpus. A single-deadline schema
    would report one of these twelve and drop eleven."""
    _, instances = parsed
    vldb = instances["conf/vldb|2027|conference"]
    assert len(vldb.deadlines) == 24
    assert len({d.round_label for d in vldb.deadlines}) == 12


def test_sigmod_rounds_are_labelled_and_ordered(parsed):
    _, instances = parsed
    sigmod = instances["conf/sigmod|2027|conference"]
    assert len(sigmod.deadlines) == 8
    assert sorted({d.round_label for d in sigmod.deadlines}) == [
        "round 1",
        "round 2",
        "round 3",
        "round 4",
    ]
    instants = [d.instant for d in sigmod.deadlines]
    assert instants == sorted(instants), "deadlines must come back chronological"


def test_timeline_rows_are_sorted_because_upstream_ones_are_not():
    """SAC/sac26 and ISSRE/issre23 are out of chronological order upstream."""
    out, _ = _parse_timeline(
        [
            {"deadline": "2027-06-01 23:59:59", "comment": "late"},
            {"deadline": "2027-01-01 23:59:59", "comment": "early"},
        ],
        "AoE",
        "ccf_deadlines",
    )
    assert [d.round_label for d in out] == ["early", "late"]


def test_a_repeated_deadline_value_is_collapsed():
    """GECCO, ADMA and ESORICS each repeat a deadline verbatim upstream."""
    out, _ = _parse_timeline(
        [
            {"deadline": "2027-01-01 23:59:59", "comment": "round 1"},
            {"deadline": "2027-01-01 23:59:59", "comment": "round 1"},
        ],
        "AoE",
        "ccf_deadlines",
    )
    assert len(out) == 1


# --- timezones -----------------------------------------------------------


def test_aoe_deadlines_resolve_to_noon_utc_the_next_day(parsed):
    _, instances = parsed
    sigmod = instances["conf/sigmod|2027|conference"]
    first = min(sigmod.deadlines, key=lambda d: d.instant)
    assert first.raw == "2026-01-10 23:59:00"
    assert first.instant == "2026-01-11T11:59:00Z"
    assert first.basis == "AoE"


def test_vldb_pt_deadlines_are_daylight_aware(parsed):
    """PT is US Pacific with DST. The upstream project's own CLI raises on it
    and silently drops all ten PT venues, VLDB included."""
    _, instances = parsed
    vldb = instances["conf/vldb|2027|conference"]
    assert {d.basis for d in vldb.deadlines} == {"PT"}
    april = next(d for d in vldb.deadlines if d.raw == "2026-04-01 17:00:00")
    # 17:00 PDT (UTC-7) on 1 April is midnight UTC on the 2nd.
    assert april.instant == "2026-04-02T00:00:00Z"


def test_the_utc_minus_twelve_spelling_is_preserved_not_rewritten_to_aoe(parsed):
    """They resolve identically but they are not the same claim."""
    _, instances = parsed
    aaai = instances["conf/aaai|2027|conference"]
    assert {d.basis for d in aaai.deadlines} == {"UTC-12"}
    submission = next(d for d in aaai.deadlines if d.kind == "submission")
    assert submission.instant == "2026-07-29T11:59:59Z"


def test_every_deadline_carries_a_basis(parsed):
    """Briefing section 10: none may be silently defaulted."""
    _, instances = parsed
    for record in instances.values():
        for deadline in record.deadlines:
            assert deadline.basis, f"{record.instance_key} has a deadline with no basis"


# --- data-integrity guards -----------------------------------------------


def test_the_eurovis_wrong_year_is_flagged_rather_than_dropped_silently(parsed):
    """EuroVis 2026 has abstract 2025-11-26 and deadline 2024-12-03 -- the
    deadline year is off by two. A plain `deadline > now` filter drops the venue
    and logs nothing."""
    _, instances = parsed
    eurovis = instances["conf/vissym|2026|conference"]
    assert any("falls after" in w for w in eurovis.quality_warnings)


def test_an_unknown_timeline_key_is_reported_not_silently_ignored():
    """conference/CG/prcv.yml has `abstract deadline` with a space. The upstream
    schema sets no additionalProperties, so it passes validation and every
    consumer ignores it."""
    _, warnings = _parse_timeline(
        [{"deadline": "2027-01-01 23:59:59", "abstract deadline": "2026-12-01 23:59:59"}],
        "AoE",
        "ccf_deadlines",
    )
    assert any("unknown timeline keys" in w for w in warnings)


def test_a_tbd_deadline_does_not_become_an_instant():
    out, _ = _parse_timeline([{"deadline": "TBD"}], "AoE", "ccf_deadlines")
    assert len(out) == 1
    assert out[0].instant is None
    assert out[0].raw == "TBD"


def test_an_unrecognised_timezone_is_recorded_rather_than_defaulted(ccf_venues):
    """Never infer a basis silently: a wrong default is invisible and up to a
    day wrong."""
    venue = dict(ccf_venues[0])
    conf = dict(venue["confs"][0])
    conf["timezone"] = "Narnia Standard Time"
    venue["confs"] = [conf]
    from tools.retrieval.tests.collect.conferences.conftest import bundle

    _, instances = CCFDeadlinesAdapter().parse(bundle("ccf_deadlines", [venue]))
    assert any("unrecognised timezone basis" in w for w in instances[0].quality_warnings)
    assert all(d.instant is None for d in instances[0].deadlines)


# --- free-text fields ----------------------------------------------------


def test_event_dates_are_kept_verbatim_and_never_parsed(parsed):
    """`date` is free text with 131 distinct format skeletons upstream. Storing
    the string and leaving event_start null is honest; guessing is not."""
    _, instances = parsed
    aaai = instances["conf/aaai|2027|conference"]
    assert aaai.event_dates_text == "February 16-23, 2027"
    assert aaai.event_start is None


def test_the_year_label_is_kept_separate_from_the_event_dates(parsed):
    _, instances = parsed
    aaai = instances["conf/aaai|2027|conference"]
    assert aaai.year_label == "2027"


@pytest.mark.parametrize(
    ("place", "city", "country"),
    [
        ("Vancouver, British Columbia, Canada", "Vancouver", "CA"),
        ("Athens, Greece", "Athens", "GR"),
        ("Huntington Beach, CA, USA", "Huntington Beach", "US"),
        ("Málaga, Spain (hybrid)", "Málaga", "ES"),
        ("Singapore EXPO", "Singapore EXPO", ""),
    ],
)
def test_places_normalize_to_a_city_and_a_country_code(place, city, country):
    """Country code plus free-text city, and explicitly no geocoding."""
    assert _city_from(place) == city
    assert _country_from(place) == country


def test_virtual_and_hybrid_are_detected(ccf_venues):
    venue = dict(ccf_venues[0])
    conf = dict(venue["confs"][0])
    conf["place"] = "Virtual"
    venue["confs"] = [conf]
    from tools.retrieval.tests.collect.conferences.conftest import bundle

    _, instances = CCFDeadlinesAdapter().parse(bundle("ccf_deadlines", [venue]))
    assert instances[0].is_virtual is True


# --- rankings ------------------------------------------------------------


def test_all_three_ranking_systems_are_carried_separately(parsed):
    """CCF, CORE and THCPL must not overwrite each other."""
    series, _ = parsed
    sigmod = next(s for s in series if s.series_key == "conf/sigmod")
    assert sigmod.rankings["ccf"]["rank"] == "A"
    assert sigmod.rankings["core"]["rank"] == "A*"
    assert sigmod.rankings["thcpl"]["rank"] == "A"


def test_no_ranking_edition_is_invented(parsed):
    """The upstream schema has no version field on any rank, so the edition is
    left empty rather than guessed. A dated CORE rank comes from CORE itself."""
    series, _ = parsed
    sigmod = next(s for s in series if s.series_key == "conf/sigmod")
    assert sigmod.rankings["core"]["edition"] == ""


# --- the seam ------------------------------------------------------------


def test_parse_runs_with_no_network(seeded_pipeline, config):
    """The fetch/parse seam is what makes re-parsing yesterday's payloads free."""
    offline = ConferencePipeline(
        type(config)(root=config.root, sources=["ccf_deadlines"], offline=True)
    )
    series, instances, counts, errors = offline.parse("20260816T000000Z")
    assert errors == []
    assert counts["ccf_deadlines"] == 11
    assert len(series) == 7


def test_a_full_run_marks_past_instances_inactive_and_keeps_them(seeded_pipeline):
    report = seeded_pipeline.run(skip_fetch=True, now=TODAY)
    assert report.instance_count == 11
    assert report.deactivated > 0

    from tools.retrieval.collect.conferences.store import ConferenceStore

    with ConferenceStore(seeded_pipeline.config.db_path) as store:
        assert store.count_instances() == 11, "nothing may be deleted"
        assert store.count_instances(active_only=True) < 11


def test_two_consecutive_runs_write_nothing_the_second_time(seeded_pipeline):
    """Briefing section 10 idempotency, over the same raw payloads."""
    seeded_pipeline.run(skip_fetch=True, now=TODAY)
    second = seeded_pipeline.run(skip_fetch=True, now=TODAY)
    assert second.stats.inserted == 0
    assert second.stats.updated == 0
    assert second.series_stats.inserted == 0
    assert second.series_stats.updated == 0

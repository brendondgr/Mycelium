"""The resolve stage: canonical keys, trust tiers, and refusing to guess.

The briefing calls this the most important stage and the one that makes the
output safe to show anyone. Its defining property is that when the evidence does
not separate two candidates, it resolves to *nothing* rather than picking.
"""

from __future__ import annotations

import json

import pytest

from apps.scraper.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)
from apps.scraper.collect.conferences.registry.cache import write_cache
from apps.scraper.collect.conferences.resolve import (
    assign_trust_tier,
    compute_red_flags,
    extract_ordinal,
    normalize_acronym,
    resolve_all,
    strip_ordinal,
)
from apps.scraper.tests.collect.conferences.conftest import fixture_text


@pytest.fixture
def registry_dir(tmp_path):
    write_cache(
        tmp_path, "dblp_venues.json", json.loads(fixture_text("dblp_venues_sample.json"))
    )
    from apps.scraper.collect.conferences.registry.core_rankings import parse_export

    write_cache(tmp_path, "core_rankings.json", parse_export(fixture_text("core_icore2026_sample.csv")))
    return tmp_path


def series(**overrides) -> ConferenceSeries:
    base = {"series_key": "gen:test", "acronym": "TEST", "full_name": "A Test Conference"}
    return ConferenceSeries(**{**base, **overrides})


# --- acronym normalization ----------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NeurIPS", "NEURIPS"),
        ("EuroS&P", "EUROSP"),
        ("ACM_WiSec", "ACMWISEC"),
        ("L@S", "LS"),
        ("ICML 2027", "ICML"),
        ("AAAI'27", "AAAI"),
        ("MM_Asia", "MMASIA"),
    ],
)
def test_acronyms_normalize_for_candidate_generation(raw, expected):
    """CORE acronyms are dirty: 23 contain a space, 18 a hyphen, one an @."""
    assert normalize_acronym(raw) == expected


def test_ordinals_are_stripped_for_matching_and_kept_for_display():
    """"32nd International Conference on X" and "International Conference on X"
    are the same series."""
    title = "32nd International Conference on Machine Learning"
    assert strip_ordinal(title) == "International Conference on Machine Learning"
    assert extract_ordinal(title) == "32nd"
    # A title with no ordinal survives untouched.
    assert strip_ordinal("Conference on Neural Information Processing") == (
        "Conference on Neural Information Processing"
    )


# --- resolution ----------------------------------------------------------


def test_a_published_dblp_key_resolves_without_any_matching(registry_dir):
    """All 353 ccf-deadlines venues publish one, so identity is free there."""
    records = [series(series_key="conf/sigmod", acronym="SIGMOD", dblp_key="conf/sigmod")]
    resolved, _, report = resolve_all(records, [], registry_dir=registry_dir)
    assert resolved[0].dblp_found is True
    assert resolved[0].indexed_years > 0
    assert report.resolved == 1


def test_an_unambiguous_acronym_resolves(registry_dir):
    records = [series(acronym="STOC", full_name="Symposium on Theory of Computing")]
    resolved, _, report = resolve_all(records, [], registry_dir=registry_dir)
    assert resolved[0].dblp_found is True
    assert report.resolved == 1


def test_the_sac_collision_resolves_to_nothing_and_records_both(registry_dir):
    """Both are active, both typed identically, both scored the same.

    Auto-picking the longer-running one deletes Selected Areas in Cryptography
    with no trace -- the failure mode this repo already treats as strictly worse
    than a duplicate.
    """
    records = [series(acronym="SAC", full_name="Symposium on Applied Cryptographic Computing")]
    resolved, _, report = resolve_all(records, [], registry_dir=registry_dir)

    assert resolved[0].dblp_found is False, "must refuse to pick"
    assert set(resolved[0].dblp_candidates) == {"conf/sac", "conf/sacrypt"}
    assert report.ambiguous == 1


def test_a_decisive_title_overlap_does_resolve_a_colliding_acronym(registry_dir):
    """Refusing to guess is not refusing to use evidence. When the full title
    plainly matches one candidate, take it."""
    records = [
        series(acronym="SAC", full_name="Selected Areas in Cryptography"),
    ]
    resolved, _, report = resolve_all(records, [], registry_dir=registry_dir)
    assert resolved[0].dblp_key == "conf/sacrypt"
    assert report.resolved == 1


def test_an_unknown_acronym_is_unresolved_not_invented(registry_dir):
    records = [series(acronym="ZZZQQ", full_name="Nonexistent Venue")]
    resolved, _, report = resolve_all(records, [], registry_dir=registry_dir)
    assert resolved[0].dblp_found is False
    assert resolved[0].dblp_candidates == []
    assert report.unresolved == 1


def test_resolve_runs_with_no_registry_at_all(tmp_path):
    """dblp is publicly warning about instability. A missing cache degrades to
    'no keys this run'; it never crashes the pipeline."""
    records = [series(acronym="SIGMOD")]
    resolved, _, report = resolve_all(records, [], registry_dir=tmp_path / "absent")
    assert report.unresolved == 1
    assert resolved[0].trust_tier != "unassigned"


# --- trust tiers ---------------------------------------------------------


def test_a_formally_ranked_venue_is_tier_a():
    record = series(rankings={"core": {"rank": "A*", "edition": "ICORE2026"}})
    assert assign_trust_tier(record) == "A"


def test_a_long_running_registry_venue_is_tier_a_without_any_ranking():
    record = series(dblp_found=True, indexed_years=36)
    assert assign_trust_tier(record) == "A"


def test_a_registry_venue_with_thin_history_is_tier_b():
    """Absence of history is not evidence of anything -- a new legitimate venue
    has none."""
    record = series(dblp_found=True, indexed_years=1)
    assert assign_trust_tier(record) == "B"


def test_a_society_listing_with_no_ranking_and_no_registry_is_tier_b():
    """This is where every non-CS venue lands, and the registry layer is CS-only.

    Treating B as a euphemism for rejection would discard exactly the records the
    briefing warns about.
    """
    record = series(contributing_sources=["miccai"])
    assert assign_trust_tier(record) == "B"


def test_an_assessed_but_unranked_venue_is_tier_b_not_c():
    """The ranking body describes "unranked" as an assurance the venue is
    legitimate -- a weak positive, not a rejection."""
    record = series(rankings={"core": {"rank": "Unranked", "edition": "ICORE2026"}})
    assert assign_trust_tier(record) == "B"


def test_a_community_only_venue_with_no_registry_match_is_quarantined():
    record = series(contributing_sources=["wikicfp"])
    assert assign_trust_tier(record) == "C"


def test_a_community_venue_that_does_resolve_is_not_quarantined():
    """Tier C means 'no registry match at all', not 'came from a wiki'."""
    record = series(contributing_sources=["wikicfp"], dblp_found=True, indexed_years=12)
    assert assign_trust_tier(record) == "A"


def test_ccf_rank_n_is_not_a_quality_endorsement():
    """"N" means "not ranked by this system" -- a real statement, but not an
    assessment that the venue is good."""
    record = series(rankings={"ccf": {"rank": "N", "edition": ""}})
    assert assign_trust_tier(record) != "A"


def test_every_series_gets_a_tier(registry_dir):
    """Briefing section 10: no record reaches the surfacing layer without one."""
    records = [
        series(series_key="a", acronym="SIGMOD", dblp_key="conf/sigmod"),
        series(series_key="b", acronym="ZZZQQ", contributing_sources=["wikicfp"]),
        series(series_key="c", acronym="SAC"),
    ]
    resolved, _, report = resolve_all(records, [], registry_dir=registry_dir)
    assert all(r.trust_tier in {"A", "B", "C"} for r in resolved)
    assert sum(report.tiers.values()) == 3


# --- red flags -----------------------------------------------------------


def test_a_title_spanning_unrelated_disciplines_is_flagged():
    record = series(
        full_name="International Conference on Engineering, Medicine, Management and Education"
    )
    assert "multi_discipline_title" in compute_red_flags(record, [])


def test_prominent_fees_in_the_cfp_body_are_flagged():
    instance = ConferenceInstance(
        source="wikicfp",
        source_record_id="1",
        cfp_text="All accepted papers require a registration fee of USD 450 paid in advance.",
    )
    assert "fees_prominent" in compute_red_flags(series(), [instance])


def test_a_cfp_with_no_named_committee_is_flagged():
    instance = ConferenceInstance(
        source="wikicfp", source_record_id="1", cfp_text="Submit your paper by the deadline."
    )
    flags = compute_red_flags(series(), [instance])
    assert "no_committee" in flags
    assert "no_publisher" in flags


def test_a_proper_cfp_body_raises_neither_flag():
    instance = ConferenceInstance(
        source="wikicfp",
        source_record_id="1",
        cfp_text=(
            "Proceedings will be published by Springer in LNCS. "
            "The program committee is chaired by the general chair."
        ),
    )
    flags = compute_red_flags(series(), [instance])
    assert "no_committee" not in flags
    assert "no_publisher" not in flags


def test_repeated_extensions_are_flagged():
    """One extension is ordinary; four on the same round is a signal."""
    instance = ConferenceInstance(
        source="wikicfp",
        source_record_id="1",
        deadlines=[Deadline(kind="submission", extension_count=4)],
    )
    assert "repeated_extensions" in compute_red_flags(series(), [instance])


def test_a_single_extension_is_not_flagged():
    instance = ConferenceInstance(
        source="wikicfp",
        source_record_id="1",
        deadlines=[Deadline(kind="submission", extension_count=1)],
    )
    assert "repeated_extensions" not in compute_red_flags(series(), [instance])


def test_a_cfp_appearing_days_before_its_own_deadline_is_flagged():
    instance = ConferenceInstance(
        source="wikicfp",
        source_record_id="1",
        first_seen="2027-01-01T00:00:00Z",
        deadlines=[Deadline(kind="submission", instant="2027-01-10T00:00:00Z")],
    )
    assert "short_cfp_window" in compute_red_flags(series(), [instance])


def test_a_normal_cfp_window_is_not_flagged():
    instance = ConferenceInstance(
        source="wikicfp",
        source_record_id="1",
        first_seen="2026-09-01T00:00:00Z",
        deadlines=[Deadline(kind="submission", instant="2027-01-10T00:00:00Z")],
    )
    assert "short_cfp_window" not in compute_red_flags(series(), [instance])


def test_no_single_flag_forces_a_tier():
    """None of these is conclusive alone. They are stored so a threshold can be
    tuned later against real data instead of hard-coded now against a guess."""
    record = series(
        rankings={"core": {"rank": "A*", "edition": "ICORE2026"}},
        red_flags=["fees_prominent", "no_committee"],
    )
    assert assign_trust_tier(record) == "A"

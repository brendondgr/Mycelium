"""The registry layer: dblp identity and CORE rankings.

Neither carries a deadline. Together they are what turns a pile of scraped CFPs
into something safe to show a user.
"""

from __future__ import annotations

import json

import pytest

from apps.scraper.collect.conferences.registry.cache import RegistryCache, write_cache
from apps.scraper.collect.conferences.registry.core_rankings import (
    CURRENT_EDITION,
    bucket_for,
    export_url,
    for_code_name,
    parse_export,
)
from apps.scraper.collect.conferences.registry.dblp import parse_registry
from apps.scraper.tests.collect.conferences.conftest import fixture_text

# --- dblp ----------------------------------------------------------------


def test_sparql_rows_are_grouped_by_stream_not_by_title():
    """The query returns one row per (stream, title) pair.

    conf/sigmod carries two current titles and 840 conferences carry a former
    one, so grouping by title would double-count venues.
    """
    payload = parse_registry(json.loads(fixture_text("dblp_sparql_sample.json")))
    keys = [v["key"] for v in payload["venues"]]
    assert keys.count("conf/innovations") == 1


def test_current_and_former_titles_are_kept_apart():
    """Former titles resolve a renamed venue in one direction and are the
    ICS -> ITCS trap in the other, so they must not be blended."""
    payload = parse_registry(json.loads(fixture_text("dblp_sparql_sample.json")))
    itcs = next(v for v in payload["venues"] if v["key"] == "conf/innovations")
    assert itcs["titles"] == ["Innovations in Theoretical Computer Science (ITCS)"]
    assert itcs["former_titles"] == ["Innovations in Computer Science (ICS)"]
    # Both acronyms are searchable, which is the point.
    assert set(itcs["acronyms"]) == {"ITCS", "ICS"}


def test_the_acronym_comes_from_the_trailing_parenthetical():
    """dblp publishes no acronym predicate at all in RDF."""
    payload = parse_registry(json.loads(fixture_text("dblp_sparql_sample.json")))
    sac = next(v for v in payload["venues"] if v["key"] == "conf/sac")
    assert sac["acronyms"] == ["SAC"]


def test_the_longevity_signal_arrives_in_the_same_request():
    """Not available from the search API at any price; it would need one extra
    fetch and an HTML parse per venue."""
    payload = parse_registry(json.loads(fixture_text("dblp_sparql_sample.json")))
    sac = next(v for v in payload["venues"] if v["key"] == "conf/sac")
    assert sac["n_years"] == 36
    assert (sac["first_year"], sac["last_year"]) == (1986, 2026)


def test_an_absent_optional_projection_is_a_missing_key_not_a_null():
    """SPARQL-results-JSON omits unbound optionals entirely."""
    payload = parse_registry(json.loads(fixture_text("dblp_sparql_sample.json")))
    sacrypt = next(v for v in payload["venues"] if v["key"] == "conf/sacrypt")
    assert sacrypt["webpage"] == ""


def test_the_key_namespace_records_what_kind_of_venue_it_is():
    payload = json.loads(fixture_text("dblp_venues_sample.json"))
    kinds = {v["key"]: v["kind"] for v in payload["venues"]}
    assert kinds["conf/sac"] == "conf"
    # arXiv/CoRR is typed as a *journal*, not a repository -- a rule filtering
    # preprint servers on kind == "repo" would never catch it.
    assert kinds["journals/corr"] == "journals"


def test_the_licence_is_recorded_on_the_payload():
    payload = parse_registry(json.loads(fixture_text("dblp_sparql_sample.json")))
    assert payload["license"] == "CC0-1.0"


# --- the collision that must never auto-merge ----------------------------


def test_sac_resolves_to_two_venues_and_the_cache_returns_both(tmp_path):
    """The canonical case. Both are active, both are 'Conference or Workshop',
    and the search API returns both with identical relevance.

    Auto-picking the longer-running one would map SAC to Applied Computing and
    delete Selected Areas in Cryptography, silently.
    """
    write_cache(tmp_path, "dblp_venues.json", json.loads(fixture_text("dblp_venues_sample.json")))
    cache = RegistryCache(tmp_path).load()

    candidates = cache.candidates_for_acronym("SAC")
    assert len(candidates) == 2
    assert {c["key"] for c in candidates} == {"conf/sac", "conf/sacrypt"}


def test_the_acronym_index_is_a_list_because_420_acronyms_collide(tmp_path):
    write_cache(tmp_path, "dblp_venues.json", json.loads(fixture_text("dblp_venues_sample.json")))
    cache = RegistryCache(tmp_path).load()
    assert isinstance(cache.by_acronym.get("SAC"), list)


def test_a_missing_cache_reports_unavailable_rather_than_crashing(tmp_path):
    """dblp is publicly warning about instability; the pipeline must degrade to
    'no keys this run', never fail."""
    cache = RegistryCache(tmp_path / "nothing-here").load()
    assert cache.available is False
    assert cache.candidates_for_acronym("SAC") == []


# --- CORE ----------------------------------------------------------------


def test_the_export_parses_with_a_real_csv_reader():
    """The file has no header row and 100 of 987 titles contain commas inside
    quotes. Splitting on commas corrupts 65 rows while looking healthy."""
    payload = parse_export(fixture_text("core_icore2026_sample.csv"))
    assert payload["problems"] == []
    assert len(payload["rankings"]) > 0

    # AIES's title is quoted and contains a comma; all three FoR codes must
    # survive rather than being shifted a column right.
    aies = next(r for r in payload["rankings"] if r["acronym"] == "AIES")
    assert aies["field_codes"] == ["4608", "4602", "4611"]


def test_a_row_with_the_wrong_field_count_is_refused_not_misread():
    """A column insert upstream would silently mis-assign FoR codes to ranks."""
    payload = parse_export("1,Some Conference,SC,ICORE2026,A\r\n")
    assert payload["rankings"] == []
    assert any("expected 9" in problem for problem in payload["problems"])


def test_a_row_from_a_different_edition_is_refused():
    """An invalid `source=` does not 400; it silently serves something else."""
    row = "1,Some Conference,SC,CORE2018,A,Yes,4601,,\r\n"
    payload = parse_export(row, edition="ICORE2026")
    assert payload["rankings"] == []
    assert any("CORE2018" in problem for problem in payload["problems"])


def test_leading_whitespace_in_titles_is_stripped():
    """Two titles begin with a space, which sorts them to the top of the export."""
    payload = parse_export(fixture_text("core_icore2026_sample.csv"))
    assert all(r["title"] == r["title"].strip() for r in payload["rankings"])


@pytest.mark.parametrize(
    ("rank", "bucket"),
    [
        ("A*", "a_star"),
        ("A", "a"),
        ("B", "b"),
        ("C", "c"),
        ("Australasian B", "australasian_b"),
        # Uncontrolled free text: all of these really appear.
        ("National: USA", "national"),
        ("National:USA", "national"),
        ("National: Czecholslovakia", "national"),
        ("Unranked", "unranked"),
        ("unranked: not primarily CS", "unranked"),
        ("Journal Published", "journal_published"),
        ("journal published", "journal_published"),
        ("Multiconference", "multiconference"),
        ("TBR", "to_be_ranked"),
        ("", "unspecified"),
    ],
)
def test_ranks_normalize_by_case_folded_prefix(rank, bucket):
    assert bucket_for(rank) == bucket


def test_the_verbatim_rank_is_always_kept_alongside_the_bucket():
    """The reporting guidelines require displaying the rank with its edition."""
    payload = parse_export(fixture_text("core_icore2026_sample.csv"))
    for row in payload["rankings"]:
        assert row["rank"] is not None
        assert row["edition"] == CURRENT_EDITION


def test_field_of_research_codes_stay_strings():
    """`CSE` is a real value and `0806` must not become `806`."""
    assert for_code_name("4611") == "Machine learning"
    assert for_code_name("CSE") == "Computer Systems Engineering"
    assert for_code_name("0806").endswith("(2008)")
    payload = parse_export(fixture_text("core_icore2026_sample.csv"))
    for row in payload["rankings"]:
        assert all(isinstance(code, str) for code in row["field_codes"])


def test_the_unlabelled_yes_no_column_is_dropped():
    """It looks like a DBLP-presence boolean but disagrees with the real DBLP
    link in 10 of 50 sampled rows, in both directions."""
    payload = parse_export(fixture_text("core_icore2026_sample.csv"))
    assert all("_unused" not in row for row in payload["rankings"])


def test_the_export_url_carries_the_magic_parameter():
    url = export_url("ICORE2026")
    assert "do=Export" in url
    assert "source=ICORE2026" in url


def test_an_unknown_edition_is_rejected():
    with pytest.raises(ValueError, match="unknown CORE edition"):
        export_url("CORE2099")


def test_core_is_disabled_by_default_and_says_why():
    """robots.txt names ClaudeBot/anthropic-ai/GPTBot and disallows them. Our UA
    falls under `*` and is permitted, but that is the maintainer's call to make
    explicitly, not a default to slip past."""
    from apps.scraper.collect.conferences.registry import core_rankings

    enabled, reason = core_rankings.available()
    assert enabled is False
    assert "robots.txt" in reason
    assert core_rankings.ENABLE_FLAG in reason


def test_core_can_be_enabled_deliberately(monkeypatch):
    from apps.scraper.collect.conferences.registry import core_rankings

    monkeypatch.setenv(core_rankings.ENABLE_FLAG, "1")
    assert core_rankings.available()[0] is True


# --- joining -------------------------------------------------------------


def test_rankings_join_on_the_dblp_key_before_the_acronym(tmp_path):
    """11 of 48 sampled CORE venues have a dblp key nothing like their acronym
    (EC -> sigecom, ISS -> tabletop), which no string similarity recovers."""
    from apps.scraper.collect.conferences.record import ConferenceSeries

    write_cache(
        tmp_path,
        "core_rankings.json",
        {
            "rankings": [
                {"acronym": "SOMETHINGELSE", "rank": "A*", "bucket": "a_star",
                 "edition": "ICORE2026", "field_codes": ["4605"], "dblp_key": "conf/sigmod"},
            ]
        },
    )
    cache = RegistryCache(tmp_path).load()
    series = ConferenceSeries(series_key="conf/sigmod", acronym="SIGMOD", dblp_key="conf/sigmod")
    assert cache.ranking_for(series)["core"]["rank"] == "A*"

"""Four layers of deduplication, and the rule that the last one never merges.

A false merge silently deletes a venue a user should have seen and leaves no
trace of having done so. A duplicate is merely annoying and visible. That
asymmetry is the whole reason layer 4 only flags.
"""

from __future__ import annotations

from tools.retrieval.collect.conferences.dedupe import (
    deduplicate,
    merge_instance,
    merge_series,
)
from tools.retrieval.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)


def instance(**overrides) -> ConferenceInstance:
    base = {
        "source": "ccf_deadlines",
        "source_record_id": "1",
        "series_key": "conf/sigmod",
        "title": "ACM Conference on Management of Data",
        "acronym": "SIGMOD",
        "year_label": "2027",
    }
    return ConferenceInstance(**{**base, **overrides})


# --- layer 1 -------------------------------------------------------------


def test_the_same_source_record_twice_collapses_and_keeps_both_deadline_sets():
    left = instance(deadlines=[Deadline(kind="submission", instant="2027-01-01T00:00:00Z",
                                        round_label="r1")])
    right = instance(deadlines=[Deadline(kind="submission", instant="2027-04-01T00:00:00Z",
                                         round_label="r2")])
    _, instances, report = deduplicate([], [left, right])
    assert report.layer1_collapsed == 1
    assert len(instances) == 1
    assert len(instances[0].deadlines) == 2


def test_the_longer_cfp_body_wins_within_a_source():
    left = instance(cfp_text="short")
    right = instance(cfp_text="a considerably longer call for papers body")
    _, instances, _ = deduplicate([], [left, right])
    assert instances[0].cfp_text.startswith("a considerably longer")


# --- layer 2 -------------------------------------------------------------


def test_a_venue_in_two_sources_becomes_one_record_listing_both():
    """Briefing section 10: a venue known to appear in two sources resolves to
    one series with both sources listed."""
    left = instance(source="ccf_deadlines", source_record_id="a")
    right = instance(source="openreview", source_record_id="b")
    _, instances, report = deduplicate([], [left, right])
    assert report.layer2_merged == 1
    assert len(instances) == 1
    assert instances[0].contributing_sources == ["ccf_deadlines", "openreview"]


def test_an_unresolved_record_passes_through_rather_than_being_guessed_at():
    """No series key means the resolve stage refused to place it. Layer 2 does
    not get to invent what resolve declined to decide."""
    left = instance(series_key="", source="wikicfp", source_record_id="a")
    right = instance(series_key="", source="openresearch", source_record_id="b")
    _, instances, report = deduplicate([], [left, right])
    assert report.layer2_merged == 0
    assert len(instances) == 2


def test_a_workshop_does_not_merge_into_its_parent_conference():
    """Tracks and workshops carry their own, usually earlier, deadlines."""
    main = instance(record_kind="conference", source_record_id="a")
    workshop = instance(record_kind="workshop", source_record_id="b", source="openreview")
    _, instances, _ = deduplicate([], [main, workshop])
    assert len(instances) == 2


# --- layer 3 -------------------------------------------------------------


def test_editions_whose_year_labels_disagree_merge_on_event_dates():
    """An edition labelled 2026 can be held in December 2025 or January 2027,
    and six structured-corpus instances contradict their own date string."""
    left = instance(
        source="ccf_deadlines", source_record_id="a", year_label="2026",
        event_start="2026-01-20",
    )
    right = instance(
        source="openreview", source_record_id="b", year_label="2025",
        event_start="2026-01-22",
    )
    _, instances, report = deduplicate([], [left, right])
    assert report.layer3_merged == 1
    assert len(instances) == 1


def test_two_genuinely_different_years_of_one_series_stay_separate():
    left = instance(source="ccf_deadlines", source_record_id="a", year_label="2026",
                    event_start="2026-06-01")
    right = instance(source="openreview", source_record_id="b", year_label="2027",
                     event_start="2027-06-01")
    _, instances, report = deduplicate([], [left, right])
    assert report.layer3_merged == 0
    assert len(instances) == 2


# --- layer 4: flags, never merges ---------------------------------------


def test_a_near_identical_pair_from_two_sources_is_flagged_and_both_survive():
    left = ConferenceInstance(
        source="wikicfp", source_record_id="a", title="International Conference on Data Mining",
        year_label="2027",
    )
    right = ConferenceInstance(
        source="openresearch", source_record_id="b",
        title="International Conference on Data Mining", year_label="2027",
    )
    _, instances, report = deduplicate([], [left, right])

    assert report.layer4_flagged == 1
    assert len(instances) == 2, "layer 4 must never merge"
    assert instances[0].review_candidates and instances[1].review_candidates
    assert len(report.review_pairs) == 1


def test_two_acronym_colliding_venues_from_different_disciplines_stay_separate():
    """Briefing section 10, and the case that motivates the whole rule.

    SAC is both the ACM Symposium on Applied Computing and Selected Areas in
    Cryptography. Merging them deletes a cryptography conference silently.
    """
    applied = ConferenceInstance(
        source="wikicfp", source_record_id="a", acronym="SAC",
        title="ACM Symposium on Applied Computing", series_key="conf/sac", year_label="2027",
    )
    crypto = ConferenceInstance(
        source="openresearch", source_record_id="b", acronym="SAC",
        title="Selected Areas in Cryptography", series_key="conf/sacrypt", year_label="2027",
    )
    _, instances, report = deduplicate([], [applied, crypto])

    assert len(instances) == 2
    assert report.layer2_merged == 0
    assert report.layer3_merged == 0


def test_the_registry_do_not_merge_assertion_suppresses_even_the_flag():
    """dblp asserts owl:differentFrom on 37 conference pairs. That is curated
    knowledge and outranks a string-similarity score."""
    series = [
        ConferenceSeries(series_key="conf/a", dblp_key="conf/a", dblp_found=True),
        ConferenceSeries(series_key="conf/b", dblp_key="conf/b", dblp_found=True),
    ]
    left = ConferenceInstance(
        source="wikicfp", source_record_id="a", series_key="conf/a",
        title="International Conference on Systems", year_label="2027",
    )
    right = ConferenceInstance(
        source="openresearch", source_record_id="b", series_key="conf/b",
        title="International Conference on Systems", year_label="2027",
    )
    _, instances, report = deduplicate(series, [left, right])
    assert report.layer4_flagged == 0
    assert len(instances) == 2


def test_records_from_one_source_are_not_fuzzy_compared():
    """Layer 1 already had its say; two ids in one source are two records."""
    left = ConferenceInstance(source="wikicfp", source_record_id="a",
                              title="Conference on Things", year_label="2027")
    right = ConferenceInstance(source="wikicfp", source_record_id="b",
                               title="Conference on Things", year_label="2027")
    _, _, report = deduplicate([], [left, right])
    assert report.layer4_flagged == 0


# --- merge precedence ----------------------------------------------------


def test_the_venue_native_source_wins_descriptive_text():
    native = instance(source="ccf_deadlines", source_record_id="a", cfp_text="the venue's own words")
    other = instance(
        source="wikicfp", source_record_id="b",
        cfp_text="a much longer third-party transcription that goes on and on and on",
    )
    merged = merge_instance(native, other)
    assert merged.cfp_text == "the venue's own words"


def test_a_source_with_a_real_timezone_leads_over_a_bare_date_source():
    """The structured repository beats a scraped wiki on deadlines because it has
    explicit timezones and the wiki has none."""
    zoned = instance(
        source="ccf_deadlines", source_record_id="a",
        deadlines=[Deadline(kind="submission", instant="2027-01-16T11:59:59Z", basis="AoE",
                            round_label="r1")],
    )
    bare = instance(
        source="wikicfp", source_record_id="b",
        deadlines=[Deadline(kind="submission", instant="2027-01-15T00:00:00Z",
                            basis="inferred:date-only", round_label="r1")],
    )
    merged = merge_instance(zoned, bare)
    assert len(merged.deadlines) == 1
    assert merged.deadlines[0].basis == "AoE"
    assert merged.deadlines[0].instant == "2027-01-16T11:59:59Z"


def test_deadlines_from_both_sides_are_kept_when_they_are_different_rounds():
    """A source contributing only a notification date must not wipe out
    another's submission rounds."""
    left = instance(
        source="ccf_deadlines", source_record_id="a",
        deadlines=[Deadline(kind="submission", instant="2027-01-01T00:00:00Z")],
    )
    right = instance(
        source="wikicfp", source_record_id="b",
        deadlines=[Deadline(kind="notification", instant="2027-03-01T00:00:00Z")],
    )
    merged = merge_instance(left, right)
    assert {d.kind for d in merged.deadlines} == {"submission", "notification"}


def test_contributing_sources_are_unioned_always():
    merged = merge_instance(
        instance(source="ccf_deadlines", source_record_id="a"),
        instance(source="openreview", source_record_id="b"),
    )
    assert set(merged.contributing_sources) == {"ccf_deadlines", "openreview"}


def test_both_raw_payloads_survive_a_merge():
    """Discarding one defeats the point of retaining raw payloads at all."""
    merged = merge_instance(
        instance(source="ccf_deadlines", source_record_id="a", raw={"x": 1}),
        instance(source="openreview", source_record_id="b", raw={"y": 2}),
    )
    assert merged.raw["ccf_deadlines"] == {"x": 1}
    assert merged.raw["openreview"] == {"y": 2}


def test_rankings_from_different_systems_survive_a_series_merge():
    """CCF, CORE and THCPL arrive from different places; a wholesale dict
    overwrite would drop two of three."""
    left = ConferenceSeries(series_key="conf/x", rankings={"ccf": {"rank": "A", "edition": ""}})
    right = ConferenceSeries(
        series_key="conf/x", rankings={"core": {"rank": "A*", "edition": "ICORE2026"}}
    )
    merged = merge_series(left, right)
    assert set(merged.rankings) == {"ccf", "core"}


def test_a_merge_keeps_both_licences_visible():
    """Two share-alike sources and a CC0 one land in the same corpus; losing the
    restrictive one in a merge would be the wrong direction to fail."""
    merged = merge_instance(
        instance(source="ccf_deadlines", source_record_id="a", license="MIT"),
        instance(source="wikicfp", source_record_id="b", license="CC-BY-SA-3.0"),
    )
    assert "MIT" in merged.license and "CC-BY-SA-3.0" in merged.license

"""Eligible fellowships split into a theme-matched band and an open band.

A list that is not topically relevant is a directory, not a recommendation — but
cluster-scoping it naively puts the same university-wide award under every theme
the reader has. The discriminator is the *shape* of an award's fit across those
themes, which is signal the pipeline already computes.
"""

from apps.content.fellowship_bands import (
    MATCHED,
    OPEN,
    classify,
    split,
)


def test_an_award_that_spikes_on_one_theme_is_matched_to_it() -> None:
    banded = classify("a", {"c-ocean": 0.82, "c-medai": 0.11})

    assert banded.band == MATCHED
    assert banded.cluster_ids == ["c-ocean"]


def test_an_award_that_spikes_on_two_themes_is_filed_under_both() -> None:
    banded = classify("a", {"c-ocean": 0.80, "c-medai": 0.78, "c-policy": 0.10})

    assert banded.band == MATCHED
    assert set(banded.cluster_ids) == {"c-ocean", "c-medai"}


def test_a_flat_award_lands_in_the_open_band() -> None:
    """A dissertation completion grant matches every theme about equally."""
    banded = classify("a", {"c-ocean": 0.52, "c-medai": 0.50, "c-policy": 0.51})

    assert banded.band == OPEN
    assert banded.cluster_ids == []


def test_a_single_theme_profile_has_nothing_to_vary_across() -> None:
    """Calling one award "matched to your themes" says nothing they didn't know."""
    assert classify("a", {"c-ocean": 0.9}).band == OPEN
    assert classify("a", {}).band == OPEN


def test_an_award_never_appears_in_both_bands() -> None:
    per_cluster = {
        "spiky": {"c-ocean": 0.9, "c-medai": 0.1},
        "flat": {"c-ocean": 0.5, "c-medai": 0.49},
    }

    matched, open_band, _bands = split(["spiky", "flat"], per_cluster)

    assert matched == {"c-ocean": ["spiky"]}
    assert open_band == ["flat"]
    assert "spiky" not in open_band


def test_a_matched_theme_orders_by_that_themes_own_fit() -> None:
    """Within a theme, the theme's own score decides — not the global order."""
    per_cluster = {
        "weaker-here": {"c-ocean": 0.60, "c-medai": 0.05},
        "stronger-here": {"c-ocean": 0.95, "c-medai": 0.05},
    }

    matched, _open, _bands = split(["weaker-here", "stronger-here"], per_cluster)

    assert matched["c-ocean"] == ["stronger-here", "weaker-here"]


def test_the_matched_band_is_shallow_and_the_overflow_stays_reachable() -> None:
    """Five per theme: a topic-matched list padded to depth is the directory again.

    What falls past the depth is still eligible, so it drops to the open band
    rather than out of the feed entirely.
    """
    ids = [f"f{i}" for i in range(8)]
    per_cluster = {cid: {"c-ocean": 0.9 - i / 100, "c-medai": 0.05}
                   for i, cid in enumerate(ids)}

    matched, open_band, _bands = split(ids, per_cluster, depth=5)

    assert len(matched["c-ocean"]) == 5
    assert open_band == ["f5", "f6", "f7"]


def test_the_open_band_keeps_the_eligibility_order() -> None:
    """A topic-agnostic award has no research-fit ordering worth imposing."""
    per_cluster = {cid: {"c-a": 0.5, "c-b": 0.5} for cid in ("first", "second")}

    _matched, open_band, _bands = split(["first", "second"], per_cluster)

    assert open_band == ["first", "second"]


def test_an_ineligible_award_never_reaches_either_band() -> None:
    """Eligibility is a hard gate: no research fit promotes past it."""
    matched, open_band, bands = split(
        ["eligible"], {"eligible": {"c-a": 0.9, "c-b": 0.1},
                       "ineligible": {"c-a": 0.99, "c-b": 0.01}}
    )

    assert "ineligible" not in bands
    assert "ineligible" not in open_band
    assert all("ineligible" not in ids for ids in matched.values())

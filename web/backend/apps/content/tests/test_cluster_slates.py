"""Per-cluster slates, admission, verdicts, and the reuse rules around them.

The regression stubs the redesign plan asks for, in one place. Each test names
the failure it exists to catch rather than the function it calls — most of these
are properties that were true by accident before and have to stay true on
purpose now.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.content.admission import admit
from apps.content.cluster_fit import (
    RUBRIC_VERSION,
    Candidate,
    Evidence,
    _shuffled,
    areas_fingerprint,
    build_prompt,
    deterministic_writeup,
    is_current,
    parse,
)
from apps.content.clustering import Cluster
from apps.content.comprehension import PROMPT_VERSION, comprehend, source_fingerprint
from apps.content.fusion import ClusteredHit
from apps.content.models import ContentItem, ItemComprehension, RelevanceScore
from apps.content.slates import (
    bridge_cluster_ids,
    compute_cluster_slates,
    merge_cluster_signals,
    prior_cluster_slates,
    prune_cluster_slates,
    slate_depth,
)
from apps.content.verdicts import FILE, READ, SKIM, SKIP, derive_verdict, parse_verdict

OCEAN = Cluster(id="c-ocean", label="Ocean", areas=["reef mapping"])
MEDAI = Cluster(id="c-medai", label="Medical AI", areas=["clinical agents"])
LABELS = {"c-ocean": "Ocean", "c-medai": "Medical AI"}


def _item(name: str, **meta) -> ContentItem:
    meta.setdefault("title", name)
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source=name, external_id=name, metadata=meta
    )


def _hit(name: str, per_cluster: dict[str, float]) -> ClusteredHit:
    best = max(per_cluster, key=lambda cid: per_cluster[cid])
    return ClusteredHit(
        item=ContentItem(external_id=name, metadata={"title": name}),
        final_score=per_cluster[best],
        cluster_id=best,
        per_cluster=per_cluster,
        per_interest={},
        bridge_cluster_ids=[],
        n_matched=1,
    )


# --------------------------------------------------------------------------- #
# Slate arithmetic
# --------------------------------------------------------------------------- #
def test_each_theme_diffs_against_its_own_previous_slate() -> None:
    """Changing one theme's membership cannot make another theme's news."""
    prior = {"c-ocean": {"a": "2026-08-01"}, "c-medai": {"b": "2026-08-01"}}

    slates = compute_cluster_slates(
        prior,
        {"c-ocean": ["a", "c"], "c-medai": ["b"]},
        LABELS,
        content_type=ContentItem.Type.PAPER,
        today="2026-08-23",
    )

    assert slates["a"]["c-ocean"]["is_new"] is False
    assert slates["c"]["c-ocean"]["is_new"] is True
    # The Medical AI slate did not move, so nothing in it is news.
    assert slates["b"]["c-medai"]["is_new"] is False


def test_the_same_item_entering_a_second_theme_is_a_separate_entry_event() -> None:
    """A niche theme's third-best paper entering is genuine news for that theme."""
    prior = {"c-ocean": {"a": "2026-08-01"}}

    slates = compute_cluster_slates(
        prior,
        {"c-ocean": ["a"], "c-medai": ["a"]},
        LABELS,
        content_type=ContentItem.Type.PAPER,
        today="2026-08-23",
    )

    assert slates["a"]["c-ocean"] == {
        "label": "Ocean", "rank": 1, "of": 1,
        "entered_on": "2026-08-01", "is_new": False,
    }
    assert slates["a"]["c-medai"]["is_new"] is True
    assert slates["a"]["c-medai"]["entered_on"] == "2026-08-23"


def test_a_theme_with_nothing_admitted_yields_no_slate_at_all() -> None:
    slates = compute_cluster_slates(
        {}, {"c-ocean": ["a"], "c-medai": []}, LABELS,
        content_type=ContentItem.Type.PAPER, today="2026-08-23",
    )

    assert set(slates) == {"a"}
    assert set(slates["a"]) == {"c-ocean"}


def test_the_flat_signals_derive_from_the_best_theme() -> None:
    """Every existing feed reader still works, unchanged, off `top_rank`."""
    slates = compute_cluster_slates(
        {}, {"c-ocean": ["x", "a"], "c-medai": ["a"]}, LABELS,
        content_type=ContentItem.Type.PAPER, today="2026-08-23",
    )
    signals: dict = {}

    merge_cluster_signals(signals, slates, "a")

    assert signals["top_rank"] == 1  # 2nd in Ocean, 1st in Medical AI
    assert signals["is_new_top"] is True
    assert set(signals["cluster_slates"]) == {"c-ocean", "c-medai"}


def test_an_item_in_no_slate_is_cleared_out_of_both_shapes() -> None:
    """It keeps its stored write-up; it stops counting as something being shown."""
    signals = {"cluster_slates": {"c-ocean": {"rank": 1}}, "top_rank": 1,
               "top_rank_of": 1, "is_new_top": True,
               "writeups": {"c-ocean": {"verdict": "read"}}}

    merge_cluster_signals(signals, {}, "a")

    assert "cluster_slates" not in signals
    assert "top_rank" not in signals
    assert "top_rank_of" not in signals
    assert signals["is_new_top"] is False
    assert signals["writeups"]  # reasoning survives, so re-entry is free


def test_the_denominator_is_the_slate_that_top_rank_came_from() -> None:
    """A card says "1st of 2", not "1st of 4" — the two themes are different lists."""
    slates = compute_cluster_slates(
        {},
        {"c-ocean": ["w", "x", "y", "a"], "c-medai": ["a", "z"]},
        LABELS,
        content_type=ContentItem.Type.PAPER,
        today="2026-08-23",
    )
    signals: dict = {}

    merge_cluster_signals(signals, slates, "a")

    # 4th in Ocean, 1st in Medical AI. `top_rank` takes the better of the two, so
    # the denominator must come from that same theme's list, not the other one.
    assert signals["top_rank"] == 1
    assert signals["top_rank_of"] == 2


def test_a_short_theme_reports_its_real_length_not_the_configured_depth() -> None:
    """A theme that only produced three candidates says "of 3", never "of 25"."""
    slates = compute_cluster_slates(
        {}, {"c-ocean": ["a", "b", "c"]}, LABELS,
        content_type=ContentItem.Type.PAPER, today="2026-08-23",
    )

    assert slates["a"]["c-ocean"]["of"] == 3


def test_a_row_written_before_slates_recorded_length_gets_no_denominator() -> None:
    """The bare ordinal is honest; a guessed depth would not be."""
    signals: dict = {}

    merge_cluster_signals(
        signals,
        {"a": {"c-ocean": {"label": "Ocean", "rank": 2, "entered_on": "",
                           "is_new": False}}},
        "a",
    )

    assert signals["top_rank"] == 2
    assert "top_rank_of" not in signals


def test_a_bridge_is_symmetric_and_costs_nothing_to_derive() -> None:
    """If A is in themes X and Y, both themes see it — no score, no re-run."""
    signals = {"cluster_slates": {
        "c-medai": {"rank": 4, "label": "Medical AI"},
        "c-ocean": {"rank": 1, "label": "Ocean"},
    }}

    assert bridge_cluster_ids(signals) == ["c-ocean", "c-medai"]


def test_papers_and_grants_keep_their_own_depths() -> None:
    """Papers are a flow, opportunities a stock — tuning one must not move both."""
    assert slate_depth(ContentItem.Type.PAPER) == 25
    assert slate_depth(ContentItem.Type.GRANT) == 10
    assert slate_depth(ContentItem.Type.CONFERENCE) == 10
    assert slate_depth(ContentItem.Type.FELLOWSHIP) == 5


# --------------------------------------------------------------------------- #
# Pruning: the current profile is the only source of truth
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_pruning_visits_every_stored_row_not_only_this_runs_candidates() -> None:
    """A deleted cluster produces nothing, so a candidate-driven prune misses it."""
    user = User.objects.create_user("pruner", password="x")
    item = _item("p")
    RelevanceScore.objects.create(
        content=item, target_user=user, score=0.5,
        signals={
            "cluster_slates": {
                "c-ocean": {"label": "Ocean", "rank": 1, "entered_on": "2026-08-01",
                            "is_new": False},
                "c-gone": {"label": "Gone", "rank": 2, "entered_on": "2026-08-01",
                           "is_new": False},
            },
            "writeups": {"c-ocean": {"verdict": "read"}, "c-gone": {"verdict": "read"}},
            "top_rank": 1,
        },
    )

    changed = prune_cluster_slates(
        {"target_user": user}, ContentItem.Type.PAPER, ["c-ocean"]
    )

    signals = RelevanceScore.objects.get(target_user=user).signals
    assert changed == 1
    assert set(signals["cluster_slates"]) == {"c-ocean"}
    # The write-up goes too: there is no theme left for the reasoning to be about.
    assert set(signals["writeups"]) == {"c-ocean"}


@pytest.mark.django_db
def test_a_wholesale_swap_leaves_no_readable_signal_from_the_old_themes() -> None:
    user = User.objects.create_user("swapper", password="x")
    RelevanceScore.objects.create(
        content=_item("p"), target_user=user, score=0.5,
        signals={
            "cluster_slates": {"c-old": {"label": "Old", "rank": 1,
                                         "entered_on": "2026-08-01", "is_new": False}},
            "top_rank": 1, "is_new_top": False, "entered_top_on": "2026-08-01",
        },
    )

    prune_cluster_slates(
        {"target_user": user}, ContentItem.Type.PAPER, ["c-bio", "c-chem"]
    )

    signals = RelevanceScore.objects.get(target_user=user).signals
    assert "cluster_slates" not in signals
    assert "top_rank" not in signals
    assert signals["is_new_top"] is False


@pytest.mark.django_db
def test_recreating_a_deleted_theme_starts_from_an_empty_slate() -> None:
    """Ids are label slugs, so a recreated theme reuses one. Pruning closes the gap."""
    user = User.objects.create_user("resurrector", password="x")
    item = _item("p")
    RelevanceScore.objects.create(
        content=item, target_user=user, score=0.5,
        signals={"cluster_slates": {"c-bio": {"label": "Bio", "rank": 1,
                                              "entered_on": "2026-06-01",
                                              "is_new": False}}},
    )

    # One run without Biology clears its keys …
    prune_cluster_slates({"target_user": user}, ContentItem.Type.PAPER, ["c-chem"])
    # … so when Biology comes back, it has no prior slate to inherit.
    prior = prior_cluster_slates({"target_user": user}, ContentItem.Type.PAPER)
    slates = compute_cluster_slates(
        prior, {"c-bio": [str(item.id)]}, {"c-bio": "Bio"},
        content_type=ContentItem.Type.PAPER, today="2026-08-23",
    )

    assert slates[str(item.id)]["c-bio"]["is_new"] is True


# --------------------------------------------------------------------------- #
# Admission
# --------------------------------------------------------------------------- #
def _cosines(hits, **by_name) -> dict[str, float]:
    """Map the fixture's readable names onto the ids `admit` actually keys on."""
    return {str(h.item.id): by_name[h.item.external_id] for h in hits}


def _names(hits, admitted: set[str]) -> set[str]:
    return {h.item.external_id for h in hits if str(h.item.id) in admitted}


def test_the_relative_floor_never_admits_below_the_hard_minimum() -> None:
    """Every set has a best element; half of it is still something."""
    hits = [_hit("best", {"c-dead": 0.02}), _hit("rest", {"c-dead": 0.011})]
    # A theme with nothing genuinely relevant in it.
    cosines = _cosines(hits, best=0.10, rest=0.09)

    admitted, stats = admit(hits, cosines, threshold=0.5, floor=0.35)

    assert admitted == set()
    assert stats.blocked_by_floor == 2


def test_the_relative_floor_rescues_a_theme_the_absolute_one_excludes() -> None:
    """A distant theme's vocabulary produces lower cosines, not worse papers."""
    hits = [_hit("loud", {"c-loud": 0.9}), _hit("quiet", {"c-quiet": 0.30})]
    cosines = _cosines(hits, loud=0.80, quiet=0.42)

    admitted, stats = admit(hits, cosines, threshold=0.5, floor=0.35)

    assert _names(hits, admitted) == {"loud", "quiet"}
    assert (stats.absolute, stats.relative) == (1, 1)
    # And the diagnostic names the starved theme, so a retrieval gap is visible.
    assert "c-quiet" in stats.note()


def test_a_single_theme_profile_admits_exactly_as_it_did_before() -> None:
    """One theme has nothing to be unfair between, so the relative half is off."""
    hits = [_hit("near", {"c-all": 0.9}), _hit("far", {"c-all": 0.5})]
    cosines = _cosines(hits, near=0.80, far=0.45)

    admitted, _stats = admit(hits, cosines, threshold=0.6, relative=False)

    assert _names(hits, admitted) == {"near"}


# --------------------------------------------------------------------------- #
# Verdicts
# --------------------------------------------------------------------------- #
def test_the_deterministic_verdict_comes_from_the_rank_band() -> None:
    assert derive_verdict(1, depth=25) == READ
    assert derive_verdict(5, depth=25) == READ
    assert derive_verdict(6, depth=25) == SKIM
    assert derive_verdict(20, depth=25) == FILE
    # A shallow opportunity slate bands the same way, proportionally.
    assert derive_verdict(1, depth=10) == READ
    assert derive_verdict(4, depth=10) == SKIM


def test_nothing_is_ever_derived_as_a_skip() -> None:
    """Being twentieth in a theme is not the same as not being worth reading."""
    assert all(derive_verdict(n, depth=25) != SKIP for n in range(1, 26))


def test_a_novel_verdict_is_rejected_rather_than_persisted() -> None:
    """A fifth label is unreadable in the UI and undebuggable in the harness."""
    assert parse_verdict("READ") == READ
    assert parse_verdict(" Skim ") == SKIM
    assert parse_verdict("must-read") is None
    assert parse_verdict(None) is None
    assert parse_verdict(7) is None


# --------------------------------------------------------------------------- #
# The fit stage's output contract
# --------------------------------------------------------------------------- #
def _candidate(name: str = "p") -> Candidate:
    return Candidate(
        item=ContentItem(external_id=name, metadata={"title": name}),
        evidence=Evidence(matched_interests=["reef mapping"], position=1),
    )


def test_a_missing_caveat_drops_the_item_rather_than_storing_a_blank() -> None:
    """A blank caveat reads as "nothing to warn you about". Not what happened."""
    payload = (
        '{"items": [{"n": 1, "verdict": "read", "matters": "It matters.", '
        '"use": "Use it.", "take": "Take it.", "caveat": ""}]}'
    )

    assert parse(payload, [_candidate()], fingerprint="fp") == {}


def test_the_word_none_is_not_a_caveat() -> None:
    payload = (
        '{"items": [{"n": 1, "verdict": "read", "matters": "It matters.", '
        '"use": "Use it.", "take": "Take it.", "caveat": "none"}]}'
    )

    assert parse(payload, [_candidate()], fingerprint="fp") == {}


def test_a_bridge_clause_is_dropped_when_the_item_does_not_bridge() -> None:
    """The model cannot invent a second theme the slates do not put it in."""
    payload = (
        '{"items": [{"n": 1, "verdict": "read", "matters": "It matters.", '
        '"use": "Use it.", "take": "Take it.", "caveat": "Small n.", '
        '"bridge": "Both strands share a method."}]}'
    )
    candidate = _candidate()

    out = parse(payload, [candidate], fingerprint="fp")

    assert out[str(candidate.item.id)]["bridge_note"] == ""


def test_a_bridge_clause_is_kept_when_the_evidence_says_it_bridges() -> None:
    payload = (
        '{"items": [{"n": 1, "verdict": "read", "matters": "It matters.", '
        '"use": "Use it.", "take": "Take it.", "caveat": "Small n.", '
        '"bridge": "Both strands share a method."}]}'
    )
    candidate = _candidate()
    candidate.evidence.also_in = ["Medical AI"]

    out = parse(payload, [candidate], fingerprint="fp")

    assert out[str(candidate.item.id)]["bridge_note"].startswith("Both strands")


def test_candidate_order_is_shuffled_and_reproducible() -> None:
    """Free, and the only cheap defence against input position bias."""
    candidates = [_candidate(f"p{i}") for i in range(8)]

    first = [c.item.external_id for c in _shuffled(candidates, seed=7)]
    again = [c.item.external_id for c in _shuffled(candidates, seed=7)]
    other = [c.item.external_id for c in _shuffled(candidates, seed=8)]

    assert first == again
    assert first != [c.item.external_id for c in candidates] or first == other


def test_the_prompt_says_not_to_reorder_and_names_only_this_strand() -> None:
    prompt = build_prompt("A researcher.", OCEAN, ["Medical AI"], [_candidate()])

    assert "Do not reorder" in prompt
    assert "OUT OF SCOPE for this judgement" in prompt
    assert "The strand you are judging for: Ocean" in prompt


def test_the_deterministic_write_up_is_complete_not_a_stub() -> None:
    """The free reader's document must read as finished, not as one missing parts."""
    writeup = deterministic_writeup(
        ContentItem(external_id="p", metadata={"title": "P"}),
        OCEAN,
        Evidence(matched_interests=["reef mapping"], position=2),
        depth=25,
        fingerprint="fp",
    )

    assert writeup["verdict"] == READ
    assert writeup["beats"] and writeup["caveat"]
    assert writeup["source"] == "deterministic"


# --------------------------------------------------------------------------- #
# Reuse: a model call happens once per artefact
# --------------------------------------------------------------------------- #
def test_only_four_things_invalidate_a_stored_write_up() -> None:
    fingerprint = areas_fingerprint(OCEAN.areas)
    stored = {
        "verdict": READ, "beats": ["b"], "caveat": "c",
        "rubric_version": RUBRIC_VERSION, "areas_fingerprint": fingerprint,
    }

    assert is_current(stored, fingerprint) is True
    # The theme's interests changed — it is answering the wrong question now.
    assert is_current(stored, areas_fingerprint(["something else"])) is False
    # The rubric moved.
    assert is_current({**stored, "rubric_version": "b0"}, fingerprint) is False
    # A malformed row (no caveat, or a novel verdict) is not reusable either.
    assert is_current({**stored, "caveat": ""}, fingerprint) is False
    assert is_current({**stored, "verdict": "must-read"}, fingerprint) is False


def test_relabelling_a_theme_does_not_invalidate_its_write_ups() -> None:
    """A rename changes its name everywhere and changes nothing else."""
    renamed = Cluster(id=OCEAN.id, label="Reef Science", areas=list(OCEAN.areas))

    assert areas_fingerprint(renamed.areas) == areas_fingerprint(OCEAN.areas)


def test_reordering_a_themes_interests_does_not_invalidate_them_either() -> None:
    """Re-saving a profile without changing anything must not cost a model call."""
    assert areas_fingerprint(["a", "B"]) == areas_fingerprint(["b", "A"])


def test_the_rubric_version_is_stamped_on_every_stored_write_up() -> None:
    """Without it a rubric change leaves the store silently mixing two rubrics."""
    writeup = deterministic_writeup(
        ContentItem(external_id="p", metadata={"title": "P"}),
        OCEAN, Evidence(position=1), depth=25, fingerprint="fp",
    )

    assert writeup["rubric_version"] == RUBRIC_VERSION


@pytest.mark.django_db
def test_a_precis_is_computed_once_and_served_to_everyone() -> None:
    """Keying it on the reader would evaporate the system's largest saving."""
    item = _item("shared", abstract="A long abstract about reef photogrammetry.")
    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return (
            '{"problem": "P", "method": "M", "setting": "S", "claim": "C", '
            '"limitations": "L", "reusable": "R", "thin": false}'
        )

    first = comprehend([item], complete=complete)
    second = comprehend([item], complete=complete)

    assert len(calls) == 1
    assert first[str(item.id)].pk == second[str(item.id)].pk
    assert ItemComprehension.objects.count() == 1


@pytest.mark.django_db
def test_a_backfilled_abstract_invalidates_the_precis_it_was_missing_from() -> None:
    """The one change that means the reading was of a genuinely different text."""
    item = _item("thin", abstract="")
    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return '{"problem": "P", "method": "M", "claim": "C", "reusable": "R"}'

    comprehend([item], complete=complete)
    before = source_fingerprint(item)

    item.metadata = {**item.metadata, "abstract": "The abstract, backfilled."}
    item.save(update_fields=["metadata"])
    comprehend([item], complete=complete)

    assert source_fingerprint(item) != before
    assert len(calls) == 2
    assert ItemComprehension.objects.get().prompt_version == PROMPT_VERSION


@pytest.mark.django_db
def test_a_model_answering_the_wrong_question_stores_nothing() -> None:
    """JSON naming none of the précis fields is a mis-route, not a thin read."""
    item = _item("odd", abstract="Real text.")

    comprehend([item], complete=lambda _p: '{"items": [{"n": 1}]}')

    assert ItemComprehension.objects.count() == 0

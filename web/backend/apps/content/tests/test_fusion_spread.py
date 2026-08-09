"""The theme-spread mechanisms: rank merge, quota/interleave, cap, MMR, floor.

Pure functions over hand-built :class:`ClusteredHit` values — no database, no
retrieval, no embeddings. Each test pins one property that a mechanism must have
for its measurement to mean anything, so a silent behaviour change fails here
rather than quietly changing an experiment's numbers.

The fixtures deliberately encode the failure these mechanisms exist to fix: a
"dominant" theme whose candidates all score high and a "starved" theme whose
candidates all score low, so a plain global ranking puts every dominant paper
first and the starved theme's best paper nowhere near the top.
"""

import uuid

from apps.content.fusion import (
    ClusteredHit,
    SpreadPolicy,
    apply_spread,
    cap_cluster_share,
    cluster_relative_pass,
    combine_clusters,
    mmr_clusters,
    quota_clusters,
)
from apps.content.models import ContentItem


def _hit(name: str, per_cluster: dict[str, float]) -> ClusteredHit:
    """A clustered hit with a *stable* id, so orderings are reproducible."""
    item = ContentItem(
        id=uuid.uuid5(uuid.NAMESPACE_URL, name), type=ContentItem.Type.PAPER
    )
    best = max(per_cluster, key=lambda cid: per_cluster[cid])
    return ClusteredHit(
        item=item,
        final_score=per_cluster[best],
        cluster_id=best,
        per_cluster=dict(per_cluster),
        per_interest={},
        bridge_cluster_ids=[cid for cid in per_cluster if cid != best],
        n_matched=1,
    )


def _names(hits) -> list[str]:
    """Map hits back to their fixture names via the deterministic uuid5."""
    lookup = {
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{theme}{i}")): f"{theme}{i}"
        for theme in ("dom", "mid", "star")
        for i in range(12)
    }
    return [lookup[str(hit.item.id)] for hit in hits]


def _lopsided() -> list[ClusteredHit]:
    """Three themes, wildly different score scales — the failure mode itself.

    `dom` occupies 0.90-0.81, `mid` 0.50-0.41, `star` 0.20-0.11. A global ranking
    by max therefore emits all ten `dom` papers before a single `mid` paper.
    """
    hits = []
    for theme, top in (("dom", 0.90), ("mid", 0.50), ("star", 0.20)):
        for i in range(10):
            hits.append(_hit(f"{theme}{i}", {theme: round(top - 0.01 * i, 4)}))
    return hits


def _themes(hits) -> list[str]:
    return [hit.cluster_id for hit in hits]


# -- combine_clusters(merge="rank") -------------------------------------------


def _scores() -> tuple[dict, dict, dict]:
    """Two interests in two clusters, on deliberately different score scales."""
    items = {name: ContentItem(id=uuid.uuid4()) for name in ("a", "b", "c", "d")}
    per_interest = {
        "strong-area": {str(items["a"].id): 0.9, str(items["b"].id): 0.8},
        "weak-area": {str(items["c"].id): 0.3, str(items["d"].id): 0.2},
    }
    clusters = {"C1": ["strong-area"], "C2": ["weak-area"]}
    return per_interest, clusters, {str(i.id): i for i in items.values()}


def test_max_merge_puts_the_whole_strong_cluster_first() -> None:
    per_interest, clusters, by_id = _scores()
    ranked = combine_clusters(per_interest, clusters, by_id)

    # The baseline behaviour, and the reason a spread mechanism is wanted at all.
    assert [hit.cluster_id for hit in ranked] == ["C1", "C1", "C2", "C2"]


def test_rank_merge_makes_the_two_clusters_interleave() -> None:
    per_interest, clusters, by_id = _scores()
    ranked = combine_clusters(per_interest, clusters, by_id, merge="rank")

    # Each cluster's rank-1 paper now ties, then each cluster's rank-2 paper:
    # the weak cluster's best is no longer behind the strong cluster's worst.
    assert sorted(hit.cluster_id for hit in ranked[:2]) == ["C1", "C2"]
    assert sorted(hit.cluster_id for hit in ranked[2:]) == ["C1", "C2"]


def test_rank_merge_keeps_raw_per_cluster_scores_for_attribution() -> None:
    per_interest, clusters, by_id = _scores()
    ranked = combine_clusters(per_interest, clusters, by_id, merge="rank")

    # Only the ranking key changes; the UI chips and the stored breakdown must
    # still read the real combined scores, which are not reciprocal ranks.
    raw = [score for hit in ranked for score in hit.per_cluster.values()]
    assert all(0.0 < score <= 1.0 for score in raw)
    assert {round(s, 4) for hit in ranked for s in hit.per_cluster.values()} == {
        0.9,
        0.8,
        0.3,
        0.2,
    }


def test_rank_merge_renormalizes_the_key_to_the_unit_interval() -> None:
    per_interest, clusters, by_id = _scores()
    ranked = combine_clusters(per_interest, clusters, by_id, merge="rank")

    assert ranked[0].final_score == 1.0
    assert ranked[-1].final_score == 0.0


def test_unknown_merge_is_rejected() -> None:
    per_interest, clusters, by_id = _scores()
    try:
        combine_clusters(per_interest, clusters, by_id, merge="mean")
    except ValueError as exc:
        assert "mean" in str(exc)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("expected ValueError for an unknown merge")


# -- quota_clusters -----------------------------------------------------------


def test_interleave_gives_every_theme_a_slot_in_the_first_cycle() -> None:
    picked = quota_clusters(_lopsided(), limit=9, allocation="equal")

    # The point of the whole exercise: the starved theme's best paper is at
    # position 3, not position 21.
    assert _names(picked)[:3] == ["dom0", "mid0", "star0"]
    assert _themes(picked).count("star") == 3


def test_interleave_splits_slots_evenly() -> None:
    picked = quota_clusters(_lopsided(), limit=12, allocation="equal")
    counts = {theme: _themes(picked).count(theme) for theme in ("dom", "mid", "star")}

    assert counts == {"dom": 4, "mid": 4, "star": 4}


def test_proportional_allocation_favours_the_theme_with_real_mass() -> None:
    picked = quota_clusters(_lopsided(), limit=12, allocation="proportional")
    counts = {theme: _themes(picked).count(theme) for theme in ("dom", "mid", "star")}

    # Strength-weighted, so `dom` keeps more slots than `star` — but `star` is
    # still guaranteed its one, which is what separates this from a plain max.
    assert counts["dom"] > counts["mid"] > counts["star"] >= 1
    assert sum(counts.values()) == 12


def test_a_paper_strong_in_two_themes_is_taken_once() -> None:
    shared = _hit("dom0", {"dom": 0.9, "star": 0.9})
    hits = [shared, _hit("dom1", {"dom": 0.8}), _hit("star1", {"star": 0.7})]
    picked = quota_clusters(hits, limit=3, allocation="equal")

    ids = [str(hit.item.id) for hit in picked]
    assert len(ids) == len(set(ids)) == 3


def test_leftover_slots_fall_back_to_the_global_order() -> None:
    # `star` has only one candidate, so its quota cannot be filled.
    hits = [_hit(f"dom{i}", {"dom": 0.9 - 0.01 * i}) for i in range(6)]
    hits.append(_hit("star0", {"star": 0.2}))
    picked = quota_clusters(hits, limit=6, allocation="equal")

    assert len(picked) == 6
    assert "star0" in _names(picked)


def test_quota_never_exceeds_the_limit_or_repeats() -> None:
    for limit in (1, 2, 5, 17, 30, 100):
        for allocation in ("equal", "proportional"):
            picked = quota_clusters(_lopsided(), limit=limit, allocation=allocation)
            ids = [str(hit.item.id) for hit in picked]
            assert len(ids) == len(set(ids))
            assert len(ids) <= min(limit, 30)


# -- cap_cluster_share --------------------------------------------------------


def test_cap_is_a_no_op_at_alpha_one() -> None:
    hits = _lopsided()
    capped = cap_cluster_share(hits, limit=30, alpha=1.0)

    assert _names(capped) == _names(sorted(hits, key=lambda h: -h.final_score))


def test_cap_breaks_a_monopoly_but_keeps_the_leader_first() -> None:
    capped = cap_cluster_share(_lopsided(), limit=9, alpha=0.5)
    themes = _themes(capped)

    # The strongest paper still wins position 1 — the cap constrains a share, it
    # does not reorder for its own sake.
    assert themes[0] == "dom"
    assert themes.count("dom") <= 5
    assert "star" in themes


def test_cap_defers_rather_than_drops() -> None:
    # A single theme, so every candidate breaches any alpha below 1.0; the cap
    # must still return a full list rather than starving the result.
    hits = [_hit(f"dom{i}", {"dom": 0.9 - 0.01 * i}) for i in range(10)]
    capped = cap_cluster_share(hits, limit=10, alpha=0.2)

    assert len(capped) == 10
    assert set(_names(capped)) == {f"dom{i}" for i in range(10)}


# -- mmr_clusters -------------------------------------------------------------


def test_mmr_at_lambda_zero_is_the_global_order() -> None:
    hits = _lopsided()
    picked = mmr_clusters(hits, limit=30, lam=0.0)

    assert _names(picked) == _names(sorted(hits, key=lambda h: -h.final_score))


def test_mmr_penalty_pulls_a_starved_theme_forward() -> None:
    plain = _themes(mmr_clusters(_lopsided(), limit=10, lam=0.0))
    spread = _themes(mmr_clusters(_lopsided(), limit=10, lam=1.0))

    assert set(plain) == {"dom"}
    assert len(set(spread)) > 1


def test_mmr_is_soft_not_a_hard_quota() -> None:
    # `dom` outscores everything by a wide margin, so even under a penalty it
    # should keep more slots than the themes it dominates — unlike interleave.
    themes = _themes(mmr_clusters(_lopsided(), limit=12, lam=0.5))

    assert themes.count("dom") > themes.count("star")


# -- cluster_relative_pass ----------------------------------------------------


def test_relative_floor_admits_each_theme_against_its_own_best() -> None:
    admitted = cluster_relative_pass(_lopsided(), frac=0.9)
    themes = {name[:-1] for name in _names([h for h in _lopsided()
                                            if str(h.item.id) in admitted])}

    # A global 0.9-of-the-maximum floor would admit `dom` only. Judged per theme,
    # every theme contributes its own strongest papers.
    assert themes == {"dom", "mid", "star"}


def test_relative_floor_at_one_keeps_only_each_themes_best() -> None:
    admitted = cluster_relative_pass(_lopsided(), frac=1.0)

    assert {name for name in _names(
        [h for h in _lopsided() if str(h.item.id) in admitted]
    )} == {"dom0", "mid0", "star0"}


def test_relative_floor_on_an_empty_ranking_is_empty() -> None:
    assert cluster_relative_pass([], frac=0.5) == set()


# -- apply_spread dispatch ----------------------------------------------------


def test_null_policy_reproduces_the_deployed_truncation() -> None:
    """The guarantee the harness's `spread_identity` arm depends on.

    `SpreadPolicy()` must select exactly what `cap_clusters` selects, in exactly
    score order. If this drifts, every spread measurement is confounded by the
    plumbing rather than by a mechanism.
    """
    from apps.content.fusion import cap_clusters

    hits = _lopsided()
    limit = 12
    assert _names(apply_spread(hits, policy=SpreadPolicy(), limit=limit)) == _names(
        sorted(
            cap_clusters(hits, limit=limit),
            key=lambda h: (-h.final_score, str(h.item.id)),
        )
    )


def test_each_select_mode_dispatches_to_its_own_function() -> None:
    hits = _lopsided()
    assert _names(
        apply_spread(hits, policy=SpreadPolicy(select="interleave"), limit=9)
    ) == _names(quota_clusters(hits, limit=9, allocation="equal"))
    assert _names(
        apply_spread(hits, policy=SpreadPolicy(select="quota"), limit=9)
    ) == _names(quota_clusters(hits, limit=9, allocation="proportional"))
    assert _names(
        apply_spread(hits, policy=SpreadPolicy(select="cap", alpha=0.4), limit=9)
    ) == _names(cap_cluster_share(hits, limit=9, alpha=0.4))
    assert _names(
        apply_spread(hits, policy=SpreadPolicy(select="mmr", lam=0.7), limit=9)
    ) == _names(mmr_clusters(hits, limit=9, lam=0.7))


def test_unknown_select_is_rejected() -> None:
    try:
        apply_spread(_lopsided(), policy=SpreadPolicy(select="magic"), limit=5)
    except ValueError as exc:
        assert "magic" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for an unknown select")


def test_every_mechanism_is_order_stable_across_calls() -> None:
    """Reproducibility is a precondition, not a nicety.

    `combine_clusters` iterates a set of ids, so its order among exact ties
    depends on string hashing. Everything here re-sorts on `(-score, id)` first;
    this pins that, since the harness reads *position* from these lists.
    """
    hits = _lopsided()
    for policy in (
        SpreadPolicy(),
        SpreadPolicy(select="interleave"),
        SpreadPolicy(select="quota"),
        SpreadPolicy(select="cap"),
        SpreadPolicy(select="mmr"),
    ):
        first = _names(apply_spread(hits, policy=policy, limit=15))
        second = _names(apply_spread(list(reversed(hits)), policy=policy, limit=15))
        assert first == second, policy


def test_zero_limit_and_empty_input_are_empty_everywhere() -> None:
    for policy in (
        SpreadPolicy(),
        SpreadPolicy(select="interleave"),
        SpreadPolicy(select="quota"),
        SpreadPolicy(select="cap"),
        SpreadPolicy(select="mmr"),
    ):
        assert apply_spread(_lopsided(), policy=policy, limit=0) == []
        assert apply_spread([], policy=policy, limit=10) == []

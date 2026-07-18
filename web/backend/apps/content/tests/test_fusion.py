"""Per-interest RRF/normalization and the cross-interest combination math.

Pure functions over unsaved ``ContentItem`` instances (each given an explicit id)
— no database, no pgvector.
"""

import uuid

from apps.content.fusion import (
    CombinedHit,
    cap_clusters,
    combine_clusters,
    combine_interests,
    fuse_interest,
    with_floor_guarantee,
)
from apps.content.models import ContentItem


def _item() -> ContentItem:
    return ContentItem(id=uuid.uuid4(), type=ContentItem.Type.PAPER)


def _hits(*items: ContentItem):
    """Fake ``(item, score)`` list, already best-first (score is ignored by RRF)."""
    return [(item, 1.0) for item in items]


# -- fuse_interest: RRF + per-interest normalization + floor -------------------


def test_doc_in_both_channels_normalizes_to_one_others_drop() -> None:
    a, b, c = _item(), _item(), _item()
    # a is rank-1 in both lists; b and c each appear once, at a list's tail.
    fused = fuse_interest(_hits(a, b), _hits(a, c), k=60)

    # a: 1/61 + 1/61 (max) -> 1.0 ; b,c: single 1/62 (min) -> 0.0 -> below floor.
    assert fused == {str(a.id): 1.0}


def test_middle_doc_survives_with_interpolated_score() -> None:
    a, b, c = _item(), _item(), _item()
    fused = fuse_interest(_hits(a, b, c), _hits(a, b), k=60)

    # a is top of both -> 1.0 ; b is second in both -> ~0.97 ; c is the lone min.
    assert fused[str(a.id)] == 1.0
    assert 0.9 < fused[str(b.id)] < 1.0
    assert str(c.id) not in fused  # normalized to 0.0, dropped by the floor


def test_empty_fusion_returns_empty() -> None:
    assert fuse_interest([], [], k=60) == {}


def test_floor_drops_subthreshold_contributions() -> None:
    a, b = _item(), _item()
    # A high floor drops everything but the single best.
    fused = fuse_interest(_hits(a, b, _item(), _item()), [], k=60, floor=0.99)
    assert list(fused.values()) == [1.0]
    assert str(a.id) in fused


# -- combine_interests: the softened-CombMNZ breadth preference ---------------


def test_three_interest_paper_outranks_one_interest_paper() -> None:
    """The primary regression: breadth wins at equal per-interest strength."""
    p_broad, p_narrow = _item(), _item()
    items = {str(p_broad.id): p_broad, str(p_narrow.id): p_narrow}
    per_interest = {
        "knowledge-graphs": {str(p_broad.id): 0.8, str(p_narrow.id): 0.8},
        "biomedical-nlp": {str(p_broad.id): 0.8},
        "retrieval": {str(p_broad.id): 0.8},
    }

    combined = combine_interests(per_interest, items, beta=0.15)

    assert combined[0].item is p_broad
    assert combined[0].n_matched == 3
    # mean 0.8 * (1 + 0.15*2) = 1.04 vs the narrow paper's 0.8.
    assert round(combined[0].combined_score, 4) == 1.04
    assert combined[1].item is p_narrow
    assert combined[1].combined_score == 0.8
    assert all(isinstance(h, CombinedHit) for h in combined)


def test_combine_skips_unknown_ids_and_empty_input() -> None:
    assert combine_interests({}, {}, beta=0.15) == []
    # A score for an id absent from items_by_id is skipped, not crashed on.
    orphan = {"the-label": {"missing-id": 0.9}}
    assert combine_interests(orphan, {}, beta=0.15) == []


# -- with_floor_guarantee: niche strong match survives truncation -------------


def test_niche_best_survives_truncation() -> None:
    p1, p2, p3, p4, p_niche = (_item() for _ in range(5))
    ids = {str(p.id): p for p in (p1, p2, p3, p4, p_niche)}
    per_interest = {
        "broad": {
            str(p1.id): 0.9,
            str(p2.id): 0.85,
            str(p3.id): 0.8,
            str(p4.id): 0.7,
        },
        "niche": {str(p_niche.id): 0.5},  # its best, but a low combined score
    }
    combined = combine_interests(per_interest, ids, beta=0.15)

    kept = with_floor_guarantee(combined, per_interest, limit=3)

    kept_items = {h.item for h in kept}
    assert len(kept) == 3
    assert p_niche in kept_items  # guaranteed despite the low combined score
    assert p1 in kept_items  # highest combined score is kept too
    assert p3 not in kept_items  # bumped to make room for the niche match
    # Result stays sorted by combined score.
    assert [h.combined_score for h in kept] == sorted(
        (h.combined_score for h in kept), reverse=True
    )


def test_floor_guarantee_limit_zero_is_empty() -> None:
    p1 = _item()
    per_interest = {"x": {str(p1.id): 1.0}}
    combined = combine_interests(per_interest, {str(p1.id): p1}, beta=0.15)
    assert with_floor_guarantee(combined, per_interest, limit=0) == []


# -- combine_clusters: cluster-scoped ranking + attribution -------------------
#
# Two clusters: "c-med" over {agents, imaging} and "c-ocean" over {assimilation}.
_MED = ["agents", "imaging"]
_OCEAN = ["assimilation"]
_CLUSTERS = {"c-med": _MED, "c-ocean": _OCEAN}


def test_final_score_is_max_cluster_and_argmax_is_attribution() -> None:
    """85%-in-Medical outranks 75%-in-Ocean; each is attributed to its cluster."""
    strong_med, strong_ocean = _item(), _item()
    ids = {str(strong_med.id): strong_med, str(strong_ocean.id): strong_ocean}
    per_interest = {
        "agents": {str(strong_med.id): 0.85},
        "assimilation": {str(strong_ocean.id): 0.75},
    }
    hits = combine_clusters(per_interest, _CLUSTERS, ids, beta=0.15)

    assert hits[0].item is strong_med
    assert hits[0].cluster_id == "c-med"
    assert round(hits[0].final_score, 4) == 0.85
    assert hits[1].item is strong_ocean
    assert hits[1].cluster_id == "c-ocean"
    assert round(hits[1].final_score, 4) == 0.75


def test_breadth_bonus_is_cluster_scoped_not_cross_cluster() -> None:
    """One interest in each of 3 clusters must NOT out-breadth a strong single cluster."""
    clusters = {"c-a": ["a"], "c-b": ["b"], "c-c": ["c"], "c-med": _MED}
    spanner, focused = _item(), _item()
    ids = {str(spanner.id): spanner, str(focused.id): focused}
    per_interest = {
        # spanner matches one interest in each of three separate clusters, 0.8 each
        "a": {str(spanner.id): 0.8},
        "b": {str(spanner.id): 0.8},
        "c": {str(spanner.id): 0.8},
        # focused matches both interests *within one* cluster, 0.8 each
        "agents": {str(focused.id): 0.8},
        "imaging": {str(focused.id): 0.8},
    }
    hits = combine_clusters(per_interest, clusters, ids, beta=0.15)

    # spanner's best cluster score is a lone-interest mean 0.8 (no breadth bonus,
    # since each cluster saw only one match). focused earns the within-cluster
    # breadth bonus: 0.8 * (1 + 0.15) = 0.92 -> it ranks first.
    assert hits[0].item is focused
    assert round(hits[0].final_score, 4) == 0.92
    assert hits[1].item is spanner
    assert round(hits[1].final_score, 4) == 0.8


def test_within_cluster_breadth_still_wins() -> None:
    """3 interests within one cluster still outrank a 1-interest match at equal strength."""
    clusters = {"c-big": ["a", "b", "c"], "c-ocean": _OCEAN}
    broad, narrow = _item(), _item()
    ids = {str(broad.id): broad, str(narrow.id): narrow}
    per_interest = {
        "a": {str(broad.id): 0.8},
        "b": {str(broad.id): 0.8},
        "c": {str(broad.id): 0.8},
        "assimilation": {str(narrow.id): 0.8},
    }
    hits = combine_clusters(per_interest, clusters, ids, beta=0.15)
    assert hits[0].item is broad
    assert hits[0].n_matched == 3
    assert hits[1].item is narrow


def test_bridge_clusters_recorded_for_two_cluster_paper() -> None:
    bridge = _item()
    ids = {str(bridge.id): bridge}
    per_interest = {
        "agents": {str(bridge.id): 0.9},  # c-med (argmax)
        "assimilation": {str(bridge.id): 0.6},  # c-ocean (bridge)
    }
    hits = combine_clusters(per_interest, _CLUSTERS, ids, beta=0.15)
    assert hits[0].cluster_id == "c-med"
    assert hits[0].bridge_cluster_ids == ["c-ocean"]
    assert set(hits[0].per_cluster) == {"c-med", "c-ocean"}
    # per_interest keeps every matched interest (for the chips).
    assert set(hits[0].per_interest) == {"agents", "assimilation"}


def test_single_cluster_paper_has_no_bridge() -> None:
    solo = _item()
    ids = {str(solo.id): solo}
    per_interest = {"agents": {str(solo.id): 0.9}}
    hits = combine_clusters(per_interest, _CLUSTERS, ids, beta=0.15)
    assert hits[0].bridge_cluster_ids == []


def test_argmax_tie_breaks_to_earliest_cluster() -> None:
    tie = _item()
    ids = {str(tie.id): tie}
    per_interest = {
        "agents": {str(tie.id): 0.7},
        "assimilation": {str(tie.id): 0.7},
    }
    hits = combine_clusters(per_interest, _CLUSTERS, ids, beta=0.15)
    assert hits[0].cluster_id == "c-med"  # earliest in cluster order wins the tie


def test_cap_clusters_guarantees_each_cluster_best() -> None:
    # c-med has four strong papers; c-ocean has one weaker paper. A tight cap must
    # still keep c-ocean's best.
    med = [_item() for _ in range(4)]
    ocean = _item()
    ids = {str(p.id): p for p in (*med, ocean)}
    per_interest = {
        "agents": {str(med[0].id): 0.9, str(med[1].id): 0.85, str(med[2].id): 0.8},
        "imaging": {str(med[3].id): 0.75},
        "assimilation": {str(ocean.id): 0.4},
    }
    hits = combine_clusters(per_interest, _CLUSTERS, ids, beta=0.15)
    kept = cap_clusters(hits, limit=3)
    kept_items = {h.item for h in kept}
    assert len(kept) == 3
    assert ocean in kept_items  # c-ocean's best survives truncation
    assert med[0] in kept_items  # the top medical paper survives too
    assert [h.final_score for h in kept] == sorted(
        (h.final_score for h in kept), reverse=True
    )


def test_cap_clusters_noop_when_under_limit() -> None:
    p = _item()
    per_interest = {"agents": {str(p.id): 0.9}}
    hits = combine_clusters(per_interest, _CLUSTERS, {str(p.id): p}, beta=0.15)
    assert cap_clusters(hits, limit=10) == hits
    assert cap_clusters(hits, limit=0) == []

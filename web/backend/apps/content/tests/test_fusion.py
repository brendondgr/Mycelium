"""Per-interest RRF/normalization and the cross-interest combination math.

Pure functions over unsaved ``ContentItem`` instances (each given an explicit id)
— no database, no pgvector.
"""

import uuid

from apps.content.fusion import (
    CombinedHit,
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

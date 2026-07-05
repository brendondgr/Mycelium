"""Per-interest fusion and cross-interest combination — the heart of the change.

Two stages, both pure and DB-free so the scoring logic is unit-testable in
isolation (the pipeline supplies the retrieval hits):

1. :func:`fuse_interest` — for a *single* search interest, fuse its BM25 lexical
   ranking with its pgvector semantic ranking using **Reciprocal Rank Fusion**
   (RRF), then **min-max normalize to [0, 1]** across that interest's fused scores
   and drop anything below a floor. Per-interest normalization is what makes the
   next stage's cross-interest comparison valid: each interest's raw RRF magnitude
   depends on how many candidates it matched, so we rescale each independently.

2. :func:`combine_interests` — across *all* interests, combine each candidate's
   per-interest scores with a softened CombMNZ so a paper matching several
   interests outranks one matching only one:

       combined = mean(normalized_scores) * (1 + β · (n_matched − 1))

   The mean keeps one weak match from dragging a strong multi-match down; the
   linear ``(1 + β·(n−1))`` breadth bonus rewards matching more interests without
   the runaway multiply of raw CombMNZ. ``β`` is a tunable knob (placeholder
   default), not a constant.

3. :func:`with_floor_guarantee` — reserve final slots for the single best paper
   *per interest* so a niche-but-strong match is not drowned out by breadth.

Everything is keyed by ``str(item.id)`` (the content UUID), never object identity:
the BM25 channel and the vector channel surface *different* ``ContentItem``
instances for the same paper (separate queries), so only the stable id unifies
them. ``β`` and the floor are placeholders pending engagement/relevance data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .models import ContentItem

Hit = tuple[ContentItem, float]

#: RRF dampening constant. 60 is the value from the original RRF paper (Cormack
#: et al.) and the de-facto default; it flattens the contribution of deep ranks.
DEFAULT_RRF_K = 60

#: Per-interest abstention floor, applied after min-max normalization. Below this
#: a candidate is treated as "did not match this interest" and drops out of that
#: interest's contribution entirely (Open Decision 5).
DEFAULT_INTEREST_FLOOR = 0.15

#: Breadth bonus for the softened CombMNZ. At 0.15 a 3-interest match earns a
#: 1 + 0.15·2 = 1.30× lift over the mean; a placeholder pending tuning.
DEFAULT_BETA = 0.15


@dataclass(frozen=True)
class CombinedHit:
    """One candidate after cross-interest combination, with its breakdown."""

    item: ContentItem
    combined_score: float
    per_interest: dict[str, float]  # interest label -> that interest's [0,1] score
    n_matched: int


def fuse_interest(
    bm25_hits: Sequence[Hit],
    vector_hits: Sequence[Hit],
    *,
    k: int = DEFAULT_RRF_K,
    floor: float = DEFAULT_INTEREST_FLOOR,
) -> dict[str, float]:
    """Fuse one interest's two channels into normalized per-item scores.

    ``bm25_hits`` and ``vector_hits`` are each ``(item, score)`` **sorted best
    first** (the raw scores are ignored — RRF uses rank position only). Returns a
    ``{item_id: normalized_score}`` map for the items that cleared ``floor``;
    items in neither list are simply absent (not zero). An empty fusion returns
    ``{}``.
    """
    rrf: dict[str, float] = {}
    for hits in (bm25_hits, vector_hits):
        for rank, (item, _score) in enumerate(hits, start=1):
            key = str(item.id)
            rrf[key] = rrf.get(key, 0.0) + 1.0 / (k + rank)
    if not rrf:
        return {}

    values = rrf.values()
    lo, hi = min(values), max(values)
    span = hi - lo
    normalized: dict[str, float] = {}
    for key, raw in rrf.items():
        # Single item (or all-equal) → span 0 → it is the interest's best (1.0).
        score = 1.0 if span == 0 else (raw - lo) / span
        if score >= floor:
            normalized[key] = score
    return normalized


def combine_interests(
    per_interest_scores: Mapping[str, Mapping[str, float]],
    items_by_id: Mapping[str, ContentItem],
    *,
    beta: float = DEFAULT_BETA,
) -> list[CombinedHit]:
    """Combine per-interest scores into one ranked list, best first.

    ``per_interest_scores`` maps ``interest_label -> {item_id: score}`` (the
    output of :func:`fuse_interest` per interest); ``items_by_id`` resolves ids
    back to their ``ContentItem``. A candidate is included if it cleared the floor
    for **at least one** interest. Sorted by combined score descending.
    """
    all_ids: set[str] = set()
    for scores in per_interest_scores.values():
        all_ids.update(scores.keys())

    combined: list[CombinedHit] = []
    for item_id in all_ids:
        item = items_by_id.get(item_id)
        if item is None:
            continue
        contributions = {
            label: scores[item_id]
            for label, scores in per_interest_scores.items()
            if item_id in scores
        }
        values = list(contributions.values())
        n_matched = len(values)
        mean = sum(values) / n_matched
        combined_score = mean * (1.0 + beta * (n_matched - 1))
        combined.append(
            CombinedHit(
                item=item,
                combined_score=combined_score,
                per_interest=contributions,
                n_matched=n_matched,
            )
        )
    combined.sort(key=lambda hit: hit.combined_score, reverse=True)
    return combined


def with_floor_guarantee(
    combined: Sequence[CombinedHit],
    per_interest_scores: Mapping[str, Mapping[str, float]],
    *,
    limit: int,
) -> list[CombinedHit]:
    """Truncate to ``limit`` while guaranteeing each interest's best paper survives.

    Takes the combined ranking and returns at most ``limit`` hits, but first
    reserves a slot for the single highest-scoring paper of every interest (by
    that interest's own normalized score) — so a strong niche match that lost the
    breadth race is not truncated away (Open Decision 4). Remaining slots go to the
    top combined scores; the result is re-sorted by combined score.
    """
    if limit <= 0:
        return []
    by_id = {str(hit.item.id): hit for hit in combined}

    must_have: list[str] = []
    for scores in per_interest_scores.values():
        if not scores:
            continue
        best_id = max(scores, key=lambda key: scores[key])
        if best_id in by_id and best_id not in must_have:
            must_have.append(best_id)

    guaranteed = [by_id[item_id] for item_id in must_have][:limit]
    guaranteed_ids = {str(hit.item.id) for hit in guaranteed}

    slots_left = limit - len(guaranteed)
    fillers = [
        hit for hit in combined if str(hit.item.id) not in guaranteed_ids
    ][:slots_left]

    result = guaranteed + fillers
    result.sort(key=lambda hit: hit.combined_score, reverse=True)
    return result

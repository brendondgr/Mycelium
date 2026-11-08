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

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from tools.retrieval.protocols import Retrievable

Hit = tuple[Retrievable, float]

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

    item: Retrievable
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
    items_by_id: Mapping[str, Retrievable],
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


@dataclass(frozen=True)
class ClusteredHit:
    """One candidate after **cluster-scoped** combination, with its attribution.

    Global ranking is by :attr:`final_score` (the max over the candidate's
    per-cluster combined scores); :attr:`cluster_id` is the argmax cluster (pure
    attribution, never a quota). The breadth bonus lives *inside* each cluster —
    :attr:`n_matched` counts only the argmax cluster's matched interests — so a
    paper matching one interest in each of three clusters cannot out-breadth a
    strong single-cluster match.
    """

    item: Retrievable
    final_score: float  # max over per-cluster combined scores (the ranking key)
    cluster_id: str  # the argmax cluster (attribution)
    per_cluster: dict[str, float]  # cluster_id -> that cluster's combined score
    per_interest: dict[str, float]  # interest label -> score (all clusters; chips)
    bridge_cluster_ids: list[str]  # other clusters cleared, when >= 2 cleared
    n_matched: int  # interests matched *within* the argmax cluster


def combine_clusters(
    per_interest_scores: Mapping[str, Mapping[str, float]],
    cluster_interest_labels: Mapping[str, Sequence[str]],
    items_by_id: Mapping[str, Retrievable],
    *,
    beta: float = DEFAULT_BETA,
    merge: str = "max",
    rrf_k: int = DEFAULT_RRF_K,
    cluster_weights: Mapping[str, float] | None = None,
) -> list[ClusteredHit]:
    """Combine per-interest scores **within each cluster**, then merge globally.

    ``per_interest_scores`` maps ``interest_label -> {item_id: score}`` (the
    output of :func:`fuse_interest`, computed once over the shared pool);
    ``cluster_interest_labels`` maps ``cluster_id -> [interest labels]`` (the
    cluster's areas). For each cluster we run the *existing* softened-CombMNZ
    :func:`combine_interests` over **only** that cluster's interests — so the
    breadth bonus never spans clusters — then take, per candidate, the **max**
    cluster score as its ``final_score`` and the argmax cluster as its
    attribution. A candidate clearing the floor in >= 2 clusters carries the
    others (minus the argmax) as ``bridge_cluster_ids``. Sorted best first.

    Cluster order (the keys of ``cluster_interest_labels``) breaks argmax ties
    deterministically: the earliest-declared cluster wins an exact tie.

    ``merge`` selects how the per-cluster scores become one ranking key:

    - ``"max"`` (default, the deployed behaviour) — ``final_score`` is the largest
      per-cluster combined score, as described above.
    - ``"rank"`` — ``final_score`` is the largest ``1 / (rrf_k + rank)`` over the
      candidate's **rank inside each cluster**, min-max renormalized to [0, 1].
      The max in ``"max"`` compares raw scores across clusters, but a cluster's
      combined scores carry how close *that theme's* vocabulary sits to the
      corpus, so a theme whose absolute scores run low is structurally
      disadvantaged everywhere. :func:`top_per_cluster` already makes this
      argument for within-cluster ranking being "scale-free"; ``"rank"`` applies
      the same reasoning to the global merge. ``per_cluster`` keeps the raw
      combined scores either way, so attribution and the UI chips are unchanged.

    ``cluster_weights`` scales a cluster's score in the **global** ranking key
    only (default: every cluster 1.0 — the deployed behaviour). A confirmed
    exploration is a theme weighted below 1 (:mod:`.explorations`), so it can
    never outrank a declared theme's candidate of equal strength; its own
    within-cluster order, ``per_cluster``, and its slate are untouched.
    """
    weights = cluster_weights or {}
    order = list(cluster_interest_labels.keys())
    cluster_hits: dict[str, dict[str, CombinedHit]] = {}
    for cluster_id in order:
        sub = {
            label: per_interest_scores[label]
            for label in cluster_interest_labels[cluster_id]
            if label in per_interest_scores
        }
        if not sub:
            continue
        hits = combine_interests(sub, items_by_id, beta=beta)
        cluster_hits[cluster_id] = {str(hit.item.id): hit for hit in hits}

    if merge not in ("max", "rank"):
        raise ValueError(f"unknown merge {merge!r}; expected 'max' or 'rank'")
    # For "rank", each cluster's own ordering becomes the cross-cluster currency.
    # Ties break on item id so the mapping is reproducible across processes.
    rank_scores: dict[str, dict[str, float]] = {}
    if merge == "rank":
        for cluster_id, hits in cluster_hits.items():
            ordered = sorted(
                hits.items(), key=lambda kv: (-kv[1].combined_score, kv[0])
            )
            rank_scores[cluster_id] = {
                item_id: 1.0 / (rrf_k + position)
                for position, (item_id, _hit) in enumerate(ordered, start=1)
            }

    all_ids: set[str] = set()
    for hits in cluster_hits.values():
        all_ids.update(hits.keys())

    out: list[ClusteredHit] = []
    for item_id in all_ids:
        item = items_by_id.get(item_id)
        if item is None:
            continue
        per_cluster: dict[str, float] = {}
        per_interest: dict[str, float] = {}
        cleared: list[str] = []
        best_cluster: str | None = None
        best_score = float("-inf")
        best_n = 0
        for cluster_id in order:
            hit = cluster_hits.get(cluster_id, {}).get(item_id)
            if hit is None:
                continue
            per_cluster[cluster_id] = hit.combined_score
            per_interest.update(hit.per_interest)
            cleared.append(cluster_id)
            key_score = (
                hit.combined_score
                if merge == "max"
                else rank_scores[cluster_id][item_id]
            ) * weights.get(cluster_id, 1.0)
            if key_score > best_score:  # strict: earliest cluster wins ties
                best_score = key_score
                best_cluster = cluster_id
                best_n = hit.n_matched
        if best_cluster is None:
            continue
        bridges = (
            [cid for cid in cleared if cid != best_cluster]
            if len(cleared) >= 2
            else []
        )
        out.append(
            ClusteredHit(
                item=item,
                final_score=best_score,
                cluster_id=best_cluster,
                per_cluster=per_cluster,
                per_interest=per_interest,
                bridge_cluster_ids=bridges,
                n_matched=best_n,
            )
        )
    if merge == "rank" and out:
        # Renormalize the reciprocal-rank key back to [0, 1] so downstream
        # consumers that assume a bounded score (logs, the stored
        # `combined_score` signal) see the same magnitude as the "max" path.
        keys = [hit.final_score for hit in out]
        lo, hi = min(keys), max(keys)
        span = hi - lo
        out = [
            replace(
                hit,
                final_score=1.0 if span == 0 else (hit.final_score - lo) / span,
            )
            for hit in out
        ]
    out.sort(key=lambda hit: hit.final_score, reverse=True)
    return out


def cap_clusters(
    clustered: Sequence[ClusteredHit], *, limit: int
) -> list[ClusteredHit]:
    """Truncate to ``limit`` while guaranteeing each cluster's best paper survives.

    The cluster-level twin of :func:`with_floor_guarantee`: before filling by
    ``final_score``, reserve a slot for the single highest-scoring paper of every
    cluster (by that cluster's own score — the paper may be attributed elsewhere),
    so a cluster with weaker matches still surfaces its best item without
    distorting the ordering above it. The result is re-sorted by ``final_score``.
    """
    if limit <= 0:
        return []
    hits = list(clustered)
    if len(hits) <= limit:
        return hits

    best_for_cluster: dict[str, ClusteredHit] = {}
    for hit in hits:
        for cluster_id, score in hit.per_cluster.items():
            current = best_for_cluster.get(cluster_id)
            if current is None or score > current.per_cluster.get(cluster_id, 0.0):
                best_for_cluster[cluster_id] = hit

    must: list[ClusteredHit] = []
    seen: set[str] = set()
    for hit in sorted(
        best_for_cluster.values(), key=lambda h: h.final_score, reverse=True
    ):
        key = str(hit.item.id)
        if key not in seen:
            seen.add(key)
            must.append(hit)
    must = must[:limit]
    must_ids = {str(hit.item.id) for hit in must}

    slots_left = limit - len(must)
    fillers = [hit for hit in hits if str(hit.item.id) not in must_ids][:slots_left]
    result = must + fillers
    result.sort(key=lambda hit: hit.final_score, reverse=True)
    return result


def top_per_cluster(
    clustered: Sequence[ClusteredHit], *, limit: int
) -> dict[str, list[ClusteredHit]]:
    """Each cluster's own best ``limit`` candidates, ranked by *that* cluster's score.

    :func:`combine_clusters` ranks globally by ``final_score`` — the max over a
    candidate's cluster scores — which answers "how strong is this paper anywhere?"
    That is the right question for a person, whose areas are specific enough that
    the strongest papers are spread across them. It is the wrong question for a
    lab, whose areas are broad *theme* names: one theme's vocabulary sits closer to
    the day's literature than another's, so a global ranking is swept by that theme
    and the rest of the lab reads as though nothing was found for it.

    Ranking within each cluster asks the question that actually matters — "what are
    the ten best papers for *this* strand of the lab's work?" — and is scale-free,
    so a theme whose absolute scores run lower still gets its ten. A candidate may
    appear in several clusters' lists; callers dedupe on the union.

    Clusters are keyed by id and only appear when at least one candidate cleared
    them; the ordering of the returned mapping follows the order clusters were
    first seen in ``clustered``.
    """
    if limit <= 0:
        return {}
    by_cluster: dict[str, list[ClusteredHit]] = {}
    for hit in clustered:
        for cluster_id in hit.per_cluster:
            by_cluster.setdefault(cluster_id, []).append(hit)
    return {
        cluster_id: sorted(
            hits, key=lambda h: h.per_cluster.get(cluster_id, 0.0), reverse=True
        )[:limit]
        for cluster_id, hits in by_cluster.items()
    }


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


# --------------------------------------------------------------------------- #
# Theme spread
#
# `combine_clusters` ranks by the max over a candidate's cluster scores, and a
# max concentrates: whichever theme's vocabulary sits closest to the day's
# literature sweeps the ordering, and the rest of the profile reads as though
# nothing was found for it. EXP-2026-08-003 measured that directly —
# `cluster_gini@10` got worse in every cell it tested.
#
# `top_per_cluster` was the first attempt at a remedy, but the caller folds its
# groups into the surfaced set and then re-sorts by `final_score`. A slate member
# is by definition a candidate the global cut rejected, so it always lands below
# the cut and no top-k above it can see the rescue. EXP-2026-08-004 measured
# every `@10` and `@30` delta as exactly 0.0 for that reason.
#
# Everything below is opt-in and defaults to off: `SpreadPolicy()` with no
# arguments reproduces today's behaviour, and `spread=None` in the pipeline never
# reaches this code at all. Which (if any) of these should be a default is an
# empirical question, and deliberately not answered here.
# --------------------------------------------------------------------------- #

#: `select` values understood by :func:`apply_spread`.
SELECT_MODES = (None, "interleave", "quota", "cap", "mmr")


@dataclass(frozen=True)
class SpreadPolicy:
    """How, if at all, to spread a cluster-scoped ranking across its themes.

    Every field defaults to the deployed behaviour, so ``SpreadPolicy()`` is a
    no-op and is used as such: the harness runs it as a null arm that must
    reproduce the untouched path exactly.

    - ``merge`` — passed straight to :func:`combine_clusters`. ``"rank"`` makes
      the cross-cluster comparison scale-free.
    - ``select`` — which selection rule fills the surfaced list.
      ``None`` keeps :func:`cap_clusters`; ``"interleave"`` and ``"quota"`` are
      :func:`quota_clusters` under equal and strength-proportional allocation;
      ``"cap"`` is :func:`cap_cluster_share`; ``"mmr"`` is :func:`mmr_clusters`.
    - ``alpha`` — for ``"cap"``, the largest share of any prefix one theme may
      hold. 1.0 disables the cap; 1/n_clusters forces near-perfect balance.
    - ``lam`` — for ``"mmr"``, how hard to penalize an already-saturated theme,
      in units of the candidate score span. 0.0 disables the penalty.
    - ``admit`` — ``"per_cluster"`` admits, beside whatever cleared the global
      cosine threshold, each theme's own strongest candidates by a *relative*
      floor, so a theme whose cosines run systematically low is not silently
      excluded by a global absolute threshold.
    - ``admit_frac`` — that relative floor, as a fraction of the theme's own best
      combined score.
    """

    merge: str = "max"
    select: str | None = None
    alpha: float = 0.5
    lam: float = 0.5
    admit: str = "global"
    admit_frac: float = 0.5
    rrf_k: int = DEFAULT_RRF_K


def _global_order(clustered: Sequence[ClusteredHit]) -> list[ClusteredHit]:
    """The global ranking, with exact ties broken reproducibly on item id.

    :func:`combine_clusters` iterates a ``set`` of ids, so its order among exactly
    equal scores depends on string hashing and is not stable across processes.
    Every function here starts from this instead, so a spread ordering is
    reproducible — which the harness relies on, since it reads position.
    """
    return sorted(clustered, key=lambda hit: (-hit.final_score, str(hit.item.id)))


def _cluster_rankings(
    clustered: Sequence[ClusteredHit],
) -> dict[str, list[ClusteredHit]]:
    """``cluster_id -> that cluster's candidates, best first by its own score``.

    The same view :func:`top_per_cluster` takes, without the truncation: ranking
    within a cluster is scale-free, so it is the right currency for any rule that
    has to compare "this theme's next best" against another theme's.
    """
    grouped: dict[str, list[tuple[float, str, ClusteredHit]]] = {}
    for hit in clustered:
        for cluster_id, score in hit.per_cluster.items():
            grouped.setdefault(cluster_id, []).append((score, str(hit.item.id), hit))
    return {
        cluster_id: [
            hit for _score, _key, hit in sorted(rows, key=lambda r: (-r[0], r[1]))
        ]
        for cluster_id, rows in grouped.items()
    }


def _allocate(weights: Mapping[str, float], limit: int) -> dict[str, int]:
    """Largest-remainder apportionment of ``limit`` slots, one guaranteed each.

    Below one slot per cluster there is nothing to apportion, so the earliest
    cluster ids take the available slots — the same "declaration order breaks
    ties" rule :func:`combine_clusters` uses.
    """
    ids = sorted(weights)
    n = len(ids)
    if limit <= 0 or n == 0:
        return {cluster_id: 0 for cluster_id in ids}
    if limit <= n:
        return {cid: (1 if i < limit else 0) for i, cid in enumerate(ids)}

    total = sum(max(0.0, weights[cid]) for cid in ids)
    spare = limit - n
    if total <= 0:
        raw = {cid: spare / n for cid in ids}
    else:
        raw = {cid: spare * max(0.0, weights[cid]) / total for cid in ids}

    alloc = {cid: 1 + int(raw[cid]) for cid in ids}
    remainder = limit - sum(alloc.values())
    for cid in sorted(ids, key=lambda c: (-(raw[c] - int(raw[c])), c))[:remainder]:
        alloc[cid] += 1
    return alloc


def quota_clusters(
    clustered: Sequence[ClusteredHit],
    *,
    limit: int,
    allocation: str = "equal",
) -> list[ClusteredHit]:
    """Fill ``limit`` slots by cycling themes, each drawing from its own ranking.

    The returned order **is the result** — callers must not re-sort it, which is
    the whole difference from the slate. Round-robin means theme *k*'s best
    candidate lands at roughly position *k*, not at position 250.

    ``allocation`` decides how many slots each theme gets:

    - ``"equal"`` — every theme gets the same share. Maximum spread; it will
      promote a weak theme's mediocre candidate over a strong theme's good one,
      which is the cost being measured.
    - ``"proportional"`` — shares scale with how much score mass a theme actually
      has in this pool, so a theme with genuinely little to offer today gets
      fewer slots rather than an equal number of filler.

    A candidate strong in two themes is taken once, by whichever theme reaches it
    first; the other theme moves down its own list. Any slots left after every
    theme is exhausted are filled from the global order.
    """
    if limit <= 0:
        return []
    rankings = _cluster_rankings(clustered)
    if not rankings:
        return []
    if allocation not in ("equal", "proportional"):
        raise ValueError(f"unknown allocation {allocation!r}")

    if allocation == "equal":
        weights = {cluster_id: 1.0 for cluster_id in rankings}
    else:
        weights = {
            cluster_id: sum(hit.per_cluster[cluster_id] for hit in hits[:limit])
            for cluster_id, hits in rankings.items()
        }
    quota = _allocate(weights, limit)

    ids = sorted(rankings)
    cursor = dict.fromkeys(ids, 0)
    used = dict.fromkeys(ids, 0)
    taken: list[ClusteredHit] = []
    seen: set[str] = set()

    progressed = True
    while len(taken) < limit and progressed:
        progressed = False
        for cluster_id in ids:
            if len(taken) >= limit:
                break
            if used[cluster_id] >= quota[cluster_id]:
                continue
            hits = rankings[cluster_id]
            position = cursor[cluster_id]
            while position < len(hits) and str(hits[position].item.id) in seen:
                position += 1
            cursor[cluster_id] = position
            if position >= len(hits):
                continue
            hit = hits[position]
            cursor[cluster_id] = position + 1
            seen.add(str(hit.item.id))
            used[cluster_id] += 1
            taken.append(hit)
            progressed = True

    if len(taken) < limit:
        for hit in _global_order(clustered):
            if len(taken) >= limit:
                break
            key = str(hit.item.id)
            if key not in seen:
                seen.add(key)
                taken.append(hit)
    return taken


def cap_cluster_share(
    clustered: Sequence[ClusteredHit], *, limit: int, alpha: float = 0.5
) -> list[ClusteredHit]:
    """The global order, except no theme may hold more than ``alpha`` of a prefix.

    The least invasive rule here: it keeps the global ranking wherever the
    ranking is not monopolized, and only defers a candidate when its theme
    already holds more than its share of everything selected so far. A deferred
    candidate is not dropped — it is retried as the list grows and its share
    allowance rises, and anything still deferred at the end fills the tail.

    ``alpha = 1.0`` is a no-op; ``alpha = 1 / n_clusters`` forces strict balance.
    Every theme is always allowed at least one slot regardless of ``alpha``.
    """
    if limit <= 0:
        return []
    queue = _global_order(clustered)
    taken: list[ClusteredHit] = []
    counts: dict[str, int] = {}

    while queue and len(taken) < limit:
        deferred: list[ClusteredHit] = []
        admitted_any = False
        for hit in queue:
            if len(taken) >= limit:
                deferred.append(hit)
                continue
            allowed = max(1, math.ceil(alpha * (len(taken) + 1)))
            if counts.get(hit.cluster_id, 0) < allowed:
                taken.append(hit)
                counts[hit.cluster_id] = counts.get(hit.cluster_id, 0) + 1
                admitted_any = True
            else:
                deferred.append(hit)
        queue = deferred
        if not admitted_any:
            break

    for hit in queue:
        if len(taken) >= limit:
            break
        taken.append(hit)
    return taken


def mmr_clusters(
    clustered: Sequence[ClusteredHit], *, limit: int, lam: float = 0.5
) -> list[ClusteredHit]:
    """Greedy selection that discounts a candidate by how saturated its theme is.

    The MMR shape, with "already-represented theme" standing in for the usual
    redundancy term::

        adjusted = final_score - lam * span * (taken_from_theme / taken_total)

    ``span`` is the score range of the candidate set, so ``lam`` is scale-free and
    reads as "how many score-spans of relevance a fully-saturated theme forfeits".
    Unlike :func:`cap_cluster_share` this is soft — a theme that is genuinely much
    stronger keeps winning slots, it just has to keep earning them.
    """
    if limit <= 0:
        return []
    pool = _global_order(clustered)
    if not pool:
        return []
    scores = [hit.final_score for hit in pool]
    span = max(scores) - min(scores)
    if span <= 0:
        span = 1.0

    taken: list[ClusteredHit] = []
    counts: dict[str, int] = {}
    remaining = list(pool)
    while remaining and len(taken) < limit:
        best_index = 0
        best_key: tuple[float, str] | None = None
        for i, hit in enumerate(remaining):
            share = (
                counts.get(hit.cluster_id, 0) / len(taken) if taken else 0.0
            )
            adjusted = hit.final_score - lam * span * share
            key = (-adjusted, str(hit.item.id))
            if best_key is None or key < best_key:
                best_key = key
                best_index = i
        hit = remaining.pop(best_index)
        taken.append(hit)
        counts[hit.cluster_id] = counts.get(hit.cluster_id, 0) + 1
    return taken


def cluster_relative_pass(
    clustered: Sequence[ClusteredHit], *, frac: float = 0.5
) -> set[str]:
    """Ids clearing a *relative* floor in at least one theme.

    The deployed admission test is one absolute cosine threshold for the whole
    profile. A theme whose vocabulary sits further from the corpus produces
    systematically lower cosines, so that single number can exclude a theme
    entirely while admitting hundreds of items from its neighbour. This is the
    per-theme counterpart: each theme admits whatever reaches ``frac`` of its own
    best, so "good for this theme" is judged against that theme.

    Returns ids, not hits, because the caller unions this with the global pass and
    wants to preserve the original ordering.
    """
    if not clustered:
        return set()
    best: dict[str, float] = {}
    for hit in clustered:
        for cluster_id, score in hit.per_cluster.items():
            if score > best.get(cluster_id, float("-inf")):
                best[cluster_id] = score
    return {
        str(hit.item.id)
        for hit in clustered
        if any(score >= frac * best[cid] for cid, score in hit.per_cluster.items())
    }


def apply_spread(
    clustered: Sequence[ClusteredHit], *, policy: SpreadPolicy, limit: int
) -> list[ClusteredHit]:
    """Dispatch ``policy.select`` and return the surfaced list **in final order**.

    ``select=None`` falls back to :func:`cap_clusters` — the deployed truncation —
    re-emitted through :func:`_global_order` so its position ordering is
    reproducible. That combination is the null policy the harness uses to prove
    the spread path introduces nothing on its own.
    """
    if limit <= 0:
        return []
    if policy.select is None:
        # `cap_clusters` fills its remaining slots in *given* order, so it is only
        # as reproducible as its input. Sorting on both sides makes the null
        # policy independent of how `combine_clusters` happened to iterate its id
        # set — which matters because the harness reads position from this list.
        return _global_order(cap_clusters(_global_order(clustered), limit=limit))
    if policy.select == "interleave":
        return quota_clusters(clustered, limit=limit, allocation="equal")
    if policy.select == "quota":
        return quota_clusters(clustered, limit=limit, allocation="proportional")
    if policy.select == "cap":
        return cap_cluster_share(clustered, limit=limit, alpha=policy.alpha)
    if policy.select == "mmr":
        return mmr_clusters(clustered, limit=limit, lam=policy.lam)
    raise ValueError(
        f"unknown select {policy.select!r}; expected one of {SELECT_MODES}"
    )

"""The evaluation arms. Every one is a thin call into `apps.content`.

The discipline that makes this harness worth building: **no arm contains ranking
logic of its own.** Each is a few lines of plumbing around the production
functions, so when `fusion.py` or `lexical.py` changes, the next run measures the
change automatically and nothing here needs editing.

- `bm25_only` — whether this repository's BM25 is correct at all. No embeddings.
- `dense_only` — the bge-small ceiling on its own.
- `fusion_dense_pool` — **production behaviour**: BM25 indexes only what dense
  retrieval already found.
- `fusion_union_pool` — true hybrid, BM25 top-N union dense top-N. Its gap from
  the arm above is exactly what the pool restriction costs.
- `fusion_full` — the above plus `rerank_by_focus`.

`fusion_dense_pool` runs the real `_build_pool`, which is why the `VectorIndex`
seam had to exist: it is the one parameter that swaps pgvector for the in-memory
index without the pipeline knowing.

**Profile arms** (`flat_profile`, `clustered_profile`) score a whole synthetic
profile rather than one query, and are the C-003 ablation. They keep the same
discipline for the same reason: `fuse_interests_pool` and `fuse_clusters_pool`
already share `_build_pool` and both take `index: VectorIndex | None`, so the two
arms run over an identical candidate pool with an identical `per_interest_scores`
map and the *only* difference between them is the aggregation step. If anything
here reimplemented `combine_clusters`, the resulting number would be about the
harness.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

Ranking = dict[str, list[tuple[str, float]]]

#: How deep each run file goes. TREC convention, and what LongEval expects.
DEPTH = 1000


def _sorted_hits(
    scores: dict[str, float], depth: int = DEPTH
) -> list[tuple[str, float]]:
    """`{doc_id: score}` → a deterministic best-first list.

    Ties break on `doc_id` so the same inputs always produce byte-identical run
    files — a precondition for the harness's determinism goal.
    """
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:depth]


def bm25_only(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Production BM25 over the whole corpus. No embeddings involved."""
    from apps.content.lexical import build_bm25_index, rank_bm25_over

    log(f"building BM25 index over {len(docs)} docs …")
    index = build_bm25_index(docs)
    if index is None:
        raise RuntimeError("build_bm25_index returned None — no indexable text?")

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        hits = rank_bm25_over(query_text, index)
        ranking[query_id] = [(str(item.id), score) for item, score in hits[:DEPTH]]
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def dense_only(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """The vector channel alone, through the same index production would use."""
    from apps.content import embeddings

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        vector = embeddings.embed_text(query_text)
        hits = index.search(vector, limit=DEPTH)
        ranking[query_id] = [(str(doc.id), sim) for doc, sim in hits]
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def fusion_dense_pool(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """Production behaviour: `_build_pool` verbatim, one interest per query.

    This is claim C1 as actually implemented — the dense channel picks the pool,
    BM25 only reorders inside it.
    """
    from apps.content.pipeline import _build_pool

    from .datasets import search_interest

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        _pool, per_interest, _best = _build_pool(
            [search_interest(query_text)],
            content_type=None,
            pool_per_interest=pool_per_interest,
            created_on=None,
            index=index,
        )
        scores = per_interest.get(query_text, {})
        ranking[query_id] = _sorted_hits(scores)
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def fusion_union_pool(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """True hybrid: the pool is BM25 top-N ∪ dense top-N, then production fusion.

    The audit's sharpest structural criticism is that BM25 currently indexes only
    what dense retrieval already found, so the lexical channel can never *add* a
    document — only reorder. This arm is that criticism turned into a number: it
    uses the identical `fuse_interest` call, changing only which candidates are in
    the pool.
    """
    from apps.content import embeddings
    from apps.content.fusion import fuse_interest
    from apps.content.lexical import build_bm25_index, rank_bm25_over

    log(f"building corpus-wide BM25 index over {len(docs)} docs …")
    corpus_index = build_bm25_index(docs)
    if corpus_index is None:
        raise RuntimeError("build_bm25_index returned None — no indexable text?")

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        vector = embeddings.embed_text(query_text)
        dense_hits = index.search(vector, limit=pool_per_interest)
        lexical_hits = rank_bm25_over(query_text, corpus_index)[:pool_per_interest]

        pool: dict[str, Any] = {str(doc.id): doc for doc, _ in dense_hits}
        for doc, _ in lexical_hits:
            pool.setdefault(str(doc.id), doc)

        # Restrict both channels to the union pool, preserving their orderings —
        # then hand them to the *same* fusion function production calls.
        pooled_lexical = [(d, s) for d, s in lexical_hits if str(d.id) in pool]
        pooled_dense = [(d, s) for d, s in dense_hits if str(d.id) in pool]
        scores = fuse_interest(pooled_lexical, pooled_dense)
        ranking[query_id] = _sorted_hits(scores)
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


def fusion_full(
    queries: Sequence[tuple[str, str]],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    log: Callable[[str], None] = print,
    **_: Any,
) -> Ranking:
    """`fusion_dense_pool` plus the production focus re-rank.

    LongEval gives one keyword query and no declared research areas, so the focus
    signal here is the query's own terms — the closest honest analogue. Whether
    that helps or hurts is precisely what this arm reports.
    """
    from apps.content.pipeline import _build_pool
    from apps.content.ranking import rerank_by_focus

    from .datasets import search_interest

    ranking: Ranking = {}
    for i, (query_id, query_text) in enumerate(queries, start=1):
        pool, per_interest, _best = _build_pool(
            [search_interest(query_text)],
            content_type=None,
            pool_per_interest=pool_per_interest,
            created_on=None,
            index=index,
        )
        scores = per_interest.get(query_text, {})
        hits = sorted(
            ((pool[key], value) for key, value in scores.items() if key in pool),
            key=lambda kv: -kv[1],
        )
        reranked = rerank_by_focus(hits, [query_text])
        ranking[query_id] = _sorted_hits(
            {str(hit.item.id): hit.score for hit in reranked}
        )
        if i % 25 == 0:
            log(f"  scored {i}/{len(queries)} queries")
    return ranking


ARMS: dict[str, Callable[..., Ranking]] = {
    "bm25_only": bm25_only,
    "dense_only": dense_only,
    "fusion_dense_pool": fusion_dense_pool,
    "fusion_union_pool": fusion_union_pool,
    "fusion_full": fusion_full,
}

#: Arms that never touch a vector — runnable before any corpus is embedded.
LEXICAL_ONLY = {"bm25_only"}


# --- profile arms: the C-003 cluster-scoping ablation -----------------------

#: Default depth for a profile run. Above `k_interests * pool_per_interest`, so
#: the pool is never truncated and neither truncation guarantee
#: (`with_floor_guarantee` for flat, `cap_clusters` for clustered) can bind. That
#: is deliberate for the aggregation ablation (EXP-2026-08-003): it leaves
#: mean-vs-max as the *only* difference between those two arms.
#:
#: The slate arm needs the opposite — a cut that **does** bind, because a slate is
#: a mechanism for surviving truncation. Configs override this.
PROFILE_SURFACE_LIMIT = 5000

#: Papers each theme contributes when the slate is on. Production's
#: `PAPER_CLUSTER_TOP_N`.
PROFILE_CLUSTER_TOP_N = 10


@dataclass
class ProfileRun:
    """A profile arm's output: the rankings plus the diagnostics C-003 needs.

    `diagnostics` carries the abstention-floor instrumentation the plan calls the
    most likely bug: `fuse_interest` drops a candidate below 0.15 *before*
    aggregation, so an interest that weakly matches contributes nothing rather
    than a low score. Under clustering that culling happens per interest while
    aggregation happens per cluster, and clusters that are empty for most
    candidates would make the two arms agree trivially. The histogram of how many
    clusters (flat: how many interests) each surfaced candidate cleared is the
    evidence for or against that, and goes into the experiment's `ISSUES.md`
    whatever the outcome.
    """

    ranking: Ranking
    diagnostics: dict[str, Any]


def _profile_ranking(
    pairs: Sequence[tuple[Any, float]], *, order_is_result: bool
) -> list[tuple[str, float]]:
    """A profile arm's surfaced list as a run-file ranking, scored by position.

    Two things this has to get right, and one trap it exists to avoid.

    `order_is_result` says where the ranking comes from. A spread policy returns
    a list whose **order is the result** — its scores are unchanged and
    deliberately not monotone in position, because re-sorting a spread ordering by
    score is exactly the bug `EXP-2026-08-004` measured. Every other arm returns
    candidates whose score *is* the ranking, and `_sorted_hits` puts them in
    deterministic `(-score, id)` order first.

    Both then get **positional** scores, `1/(1+i)`. That is not cosmetic:
    `ir_measures` re-sorts a run by score and breaks ties by its own convention,
    so an arm with many tied scores (the baseline, whose `final_score` ties often)
    is silently re-ordered inside the metric while an arm with distinct scores is
    not. Measured on the first smoke run, that alone moved `nDCG@100` by 0.0016
    between two arms whose run files were byte-identical. Scoring every arm by
    position removes the asymmetry: what the arm ordered is what gets scored.
    """
    if order_is_result:
        ranked = [str(item.id) for item, _score in pairs[:DEPTH]]
    else:
        ranked = [
            doc_id
            for doc_id, _score in _sorted_hits(
                {str(item.id): score for item, score in pairs}
            )
        ]
    return [(doc_id, 1.0 / (1 + position)) for position, doc_id in enumerate(ranked)]


def _cleared_histogram(counts: Sequence[int]) -> dict[str, int]:
    histogram: dict[str, int] = {}
    for count in counts:
        key = str(count)
        histogram[key] = histogram.get(key, 0) + 1
    return dict(sorted(histogram.items(), key=lambda kv: int(kv[0])))


def _surfacing_stats(sizes: list[int], pools: list[int]) -> dict[str, float]:
    """How much of the pool each arm actually surfaced.

    Essential to reading any slate result honestly: a slate buys theme coverage by
    surfacing *more* items, so a coverage gain that comes with a larger surfaced
    set is a different thing from one that comes free. It also says whether the
    cut binds at all — if the mean surfaced size equals the mean pool size, the
    threshold never fired and every arm is trivially identical.
    """
    if not sizes:
        return {}
    return {
        "mean_surfaced": round(sum(sizes) / len(sizes), 2),
        "median_surfaced": float(sorted(sizes)[len(sizes) // 2]),
        "max_surfaced": float(max(sizes)),
        "mean_pool": round(sum(pools) / len(pools), 2),
    }


def flat_profile(
    profiles: Sequence[Any],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    beta: float = 0.15,
    surface_limit: int = PROFILE_SURFACE_LIMIT,
    match_threshold: float | None = None,
    log: Callable[[str], None] = print,
    **_: Any,
) -> ProfileRun:
    """Flat aggregation over a whole profile: `pipeline.fuse_interests_pool`.

    Every one of the profile's interests is combined by the softened CombMNZ
    `mean × (1 + β(n−1))`, ignoring the cluster partition entirely. This is the
    "global ranking" half of C-003's comparison.
    """
    from apps.content.pipeline import fuse_interests_pool

    ranking: Ranking = {}
    cleared: list[int] = []
    sizes: list[int] = []
    pools: list[int] = []
    for i, profile in enumerate(profiles, start=1):
        pairs, rows, pool_size = fuse_interests_pool(
            profile.interests(),
            content_type=None,
            surface_limit=surface_limit,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=lambda _message: None,
            created_on=None,
            match_threshold=match_threshold,
            index=index,
        )
        ranking[profile.id] = _profile_ranking(pairs, order_is_result=False)
        cleared.extend(int(extra["n_matched"]) for _item, _score, extra in rows)
        sizes.append(len(pairs))
        pools.append(pool_size)
        if i % 10 == 0:
            log(f"  scored {i}/{len(profiles)} profiles")
    return ProfileRun(
        ranking=ranking,
        diagnostics={
            "interests_cleared_per_candidate": _cleared_histogram(cleared),
            "surfacing": _surfacing_stats(sizes, pools),
        },
    )


def clustered_profile(
    profiles: Sequence[Any],
    docs: Sequence[Any],
    *,
    index,
    pool_per_interest: int = 100,
    beta: float = 0.15,
    surface_limit: int = PROFILE_SURFACE_LIMIT,
    match_threshold: float | None = None,
    cluster_top_n: int = 0,
    spread=None,
    log: Callable[[str], None] = print,
    **_: Any,
) -> ProfileRun:
    """Cluster-scoped aggregation: `pipeline.fuse_clusters_pool`.

    The same pool and the same per-interest scores as :func:`flat_profile` — both
    go through `_build_pool` — combined *within* each cluster and then max-pooled
    across them. This is the claim C-003 makes.

    With `cluster_top_n = 0` (the default) this is the **global ranking** an
    individual's feed uses. With it set, the same call additionally folds in each
    cluster's own best `cluster_top_n` candidates — the **slate**, which is what
    an institutional/lab target gets. :func:`slate_profile` is that configuration
    under its own name, so the two appear as separate arms in the results.
    """
    from apps.content.pipeline import fuse_clusters_pool

    ranking: Ranking = {}
    cleared: list[int] = []
    sizes: list[int] = []
    pools: list[int] = []
    for i, profile in enumerate(profiles, start=1):
        pairs, rows, pool_size, _slate = fuse_clusters_pool(
            profile.interests(),
            profile.clusters(),
            content_type=None,
            surface_limit=surface_limit,
            pool_per_interest=pool_per_interest,
            beta=beta,
            emit=lambda _message: None,
            created_on=None,
            match_threshold=match_threshold,
            cluster_top_n=cluster_top_n,
            spread=spread,
            index=index,
        )
        ranking[profile.id] = _profile_ranking(
            pairs, order_is_result=spread is not None
        )
        cleared.extend(len(extra["per_cluster"]) for _item, _score, extra in rows)
        sizes.append(len(pairs))
        pools.append(pool_size)
        if i % 10 == 0:
            log(f"  scored {i}/{len(profiles)} profiles")
    return ProfileRun(
        ranking=ranking,
        diagnostics={
            "clusters_cleared_per_candidate": _cleared_histogram(cleared),
            "surfacing": _surfacing_stats(sizes, pools),
        },
    )


def slate_profile(
    profiles: Sequence[Any],
    docs: Sequence[Any],
    *,
    cluster_top_n: int = PROFILE_CLUSTER_TOP_N,
    **kwargs: Any,
) -> ProfileRun:
    """The **lab** path: cluster-scoped aggregation plus the per-theme slate.

    `fusion.top_per_cluster` gives every cluster its own best `cluster_top_n`
    candidates *by that cluster's own score*, and `fuse_clusters_pool` folds any
    slate member the global cut missed back into the surfaced set. Its docstring
    is explicit about why: a global ranking "is swept by that theme and the rest
    of the lab reads as though nothing was found for it," which is exactly the
    failure EXP-2026-08-003 measured in the global ranking.

    So this arm is the untested half of C-003 (Q-010). It is deliberately a thin
    keyword-forwarding wrapper over :func:`clustered_profile` — the difference
    between the two arms is one production argument, and nothing else.
    """
    return clustered_profile(
        profiles, docs, cluster_top_n=cluster_top_n, **kwargs
    )


def _spread_policies() -> dict[str, Any]:
    """The theme-spread arms of `EXP-2026-08-005`, one production policy each.

    Built lazily inside a function because `SpreadPolicy` lives in Django app code
    that `eval/run.py` only makes importable after `django.setup()`.

    `spread_identity` is the null arm and the experiment's falsifier 4: a policy
    with every field at its default must reproduce `clustered_profile` exactly. If
    it does not, the spread plumbing — not a mechanism — is moving the numbers,
    and nothing else in the experiment can be trusted.

    The parameterized policies use the midpoint of their range. `cap` at
    `alpha=0.5` lets one theme hold half of any prefix (with three themes, perfect
    balance would be 0.33 and 1.0 is a no-op); `mmr` at `lam=0.5` forfeits half a
    score-span for a fully saturated theme. Neither is tuned — tuning a knob on
    the same profiles used to measure it is how a null result becomes a positive
    one, so the values are fixed before the runs and left alone.
    """
    from apps.content.fusion import SpreadPolicy

    return {
        "spread_identity": SpreadPolicy(),
        "spread_interleave": SpreadPolicy(select="interleave"),
        "spread_quota": SpreadPolicy(select="quota"),
        "spread_cap": SpreadPolicy(select="cap", alpha=0.5),
        "spread_mmr": SpreadPolicy(select="mmr", lam=0.5),
        "spread_rankmerge": SpreadPolicy(merge="rank"),
        "spread_floor": SpreadPolicy(admit="per_cluster", admit_frac=0.5),
        # Combinations, phase 4. Each pairs the mechanism that fixes the *scores*
        # with one that fixes the *selection*, plus the widened admission.
        "spread_rankmerge_interleave": SpreadPolicy(
            merge="rank", select="interleave"
        ),
        "spread_rankmerge_quota": SpreadPolicy(merge="rank", select="quota"),
        "spread_rankmerge_cap": SpreadPolicy(merge="rank", select="cap", alpha=0.5),
        "spread_rankmerge_mmr": SpreadPolicy(merge="rank", select="mmr", lam=0.5),
        "spread_floor_interleave": SpreadPolicy(
            select="interleave", admit="per_cluster", admit_frac=0.5
        ),
        "spread_all": SpreadPolicy(
            merge="rank", select="interleave", admit="per_cluster", admit_frac=0.5
        ),
    }


def _spread_arm(name: str) -> Callable[..., ProfileRun]:
    """One named policy as an arm — a keyword forward, and nothing else.

    Same discipline as `slate_profile`: an arm differs from the `clustered_profile`
    baseline by exactly one production argument, so a measured difference can only
    have come from production code.
    """

    def arm(profiles, docs, **kwargs) -> ProfileRun:
        kwargs.pop("cluster_top_n", None)  # the policy is the theme protection
        return clustered_profile(
            profiles, docs, spread=_spread_policies()[name], **kwargs
        )

    arm.__name__ = name
    arm.__doc__ = f"Cluster-scoped aggregation under the `{name}` spread policy."
    return arm


#: Arms that take synthetic profiles instead of queries. `eval/run.py` routes on
#: this: same entrypoint, same results contract, different input construction.
PROFILE_ARMS: dict[str, Callable[..., ProfileRun]] = {
    "flat_profile": flat_profile,
    "clustered_profile": clustered_profile,
    "slate_profile": slate_profile,
}

#: Names only — the policies themselves need Django configured, so they are built
#: on first call rather than at import.
SPREAD_ARM_NAMES = (
    "spread_identity",
    "spread_interleave",
    "spread_quota",
    "spread_cap",
    "spread_mmr",
    "spread_rankmerge",
    "spread_floor",
    "spread_rankmerge_interleave",
    "spread_rankmerge_quota",
    "spread_rankmerge_cap",
    "spread_rankmerge_mmr",
    "spread_floor_interleave",
    "spread_all",
)

PROFILE_ARMS.update({name: _spread_arm(name) for name in SPREAD_ARM_NAMES})

"""Synthetic multi-interest, multi-cluster profiles built from a collection's queries.

`harness/datasets.py` states the problem this module solves: a LongEval query is a
single keyword string, so "the multi-interest and cluster machinery is simply not
exercised by this collection." Every existing arm scores one query at a time, and
`combine_clusters` never fires. There is no way to measure C-003 against the data
already on disk without first *constructing* something with clusters in it.

A **synthetic profile** is *K* of the collection's queries treated as *K* declared
interests, partitioned into *C* clusters. Its relevance judgments are the union of
its constituent queries' qrels — deduplicated, keeping the maximum grade where a
document is judged for more than one constituent query — and each cluster carries
its own relevant set, which is what the coverage metrics in
:mod:`harness.cluster_metrics` attribute against.

**The grouping is the independent variable, not an implementation detail.** How
interests are assigned to clusters determines the answer, so it is a controlled
condition with three modes:

``coherent``
    Groups are formed greedily by embedding similarity, so the interests inside a
    cluster are genuinely related. This is the condition C-003 assumes.

``random``
    The **same profiles** as ``coherent`` — identical interest sets, so the flat
    arm is bit-identical between the two modes — repartitioned by a seeded
    shuffle. Cluster structure is noise. This is the negative control, and it is
    not optional: if clustered scoring "improves" coverage here too, the metric is
    measuring something other than cluster structure and the finding is void.

``imbalanced``
    Coherent groups, then the profiles selected for the largest spread in
    *score mass* across their clusters. This is the condition C-003 actually
    claims to fix — one theme whose vocabulary sits closer to the corpus than the
    others'. Score mass is the mean cosine of a query's top dense hits, computed
    from the same index the run uses; the selection rule is fixed here and
    recorded in the experiment's `PROTOCOL.md` rather than tuned after seeing
    results.

Everything is deterministic given ``seed``. Cluster **declaration order** is
shuffled per profile on purpose: `combine_clusters` breaks argmax ties by
earliest-declared cluster, and with synthetic profiles declaration order is
arbitrary, so leaving it fixed would smuggle in a hidden variable.

Nothing here imports Django at module level — `SearchInterest` and `Cluster` are
resolved lazily — so the construction logic is unit-testable without settings.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

#: The three grouping conditions. All three are required for a valid finding.
MODES = ("coherent", "random", "imbalanced")


@dataclass(frozen=True)
class SyntheticProfile:
    """One constructed profile: *K* interests in *C* clusters, plus its judgments.

    ``cluster_query_ids`` is ordered — its key order is the cluster declaration
    order handed to `combine_clusters`, and therefore its tie-break order.
    """

    id: str
    mode: str
    query_ids: tuple[str, ...]
    query_texts: dict[str, str]
    cluster_query_ids: dict[str, list[str]]
    qrels: dict[str, int]
    cluster_relevant: dict[str, set[str]]

    @property
    def n_relevant(self) -> int:
        return sum(1 for grade in self.qrels.values() if grade > 0)

    def interests(self) -> list[Any]:
        """The profile's interests as production `SearchInterest` objects.

        A query's text is its label, its BM25 query, and its embed text — the same
        shape :func:`harness.datasets.search_interest` uses for a single query.
        """
        from apps.content.interests_query import SearchInterest

        return [
            SearchInterest(
                label=self.query_texts[qid],
                query_text=self.query_texts[qid],
                embed_text=self.query_texts[qid],
            )
            for qid in self.query_ids
        ]

    def clusters(self) -> list[Any]:
        """The profile's clusters as production `Cluster` objects.

        ``areas`` are the interest **labels**, because that is the key
        `combine_clusters` looks up in the per-interest score map.
        """
        from apps.content.clustering import Cluster

        return [
            Cluster(
                id=cluster_id,
                label=cluster_id,
                areas=[self.query_texts[qid] for qid in query_ids],
            )
            for cluster_id, query_ids in self.cluster_query_ids.items()
        ]


# --- construction ----------------------------------------------------------


def _similarity(vectors: np.ndarray) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms) @ (matrix / norms).T


def coherent_groups(
    query_ids: Sequence[str], vectors: np.ndarray, *, size: int
) -> list[tuple[str, ...]]:
    """Partition queries into groups of ``size`` that are internally similar.

    Greedy agglomeration: take the most similar unused pair as a seed, then extend
    it with whichever unused query has the highest mean similarity to the group so
    far, until the group is full. Leftovers that cannot fill a final group are
    dropped. Ties break on query id, so the partition is deterministic.

    This is the "genuinely related interests" condition. It is not k-means — a
    k-means partition gives clusters of uneven size, and the experiment needs every
    cluster to carry the same number of interests so that cluster size is not an
    uncontrolled variable alongside cluster coherence.
    """
    if size < 2:
        raise ValueError("a cluster needs at least two interests to be a grouping")
    sims = _similarity(vectors)
    position = {qid: i for i, qid in enumerate(query_ids)}
    remaining = list(query_ids)

    groups: list[tuple[str, ...]] = []
    while len(remaining) >= size:
        best_pair: tuple[str, str] | None = None
        best_score = float("-inf")
        for i, left in enumerate(remaining):
            for right in remaining[i + 1 :]:
                score = float(sims[position[left], position[right]])
                if score > best_score or (
                    score == best_score
                    and best_pair is not None
                    and (left, right) < best_pair
                ):
                    best_score, best_pair = score, (left, right)
        assert best_pair is not None
        group = list(best_pair)
        for member in group:
            remaining.remove(member)

        while len(group) < size:
            indices = [position[member] for member in group]
            candidates = sorted(
                remaining,
                key=lambda qid: (
                    -float(np.mean(sims[position[qid], indices])),
                    qid,
                ),
            )
            group.append(candidates[0])
            remaining.remove(candidates[0])
        groups.append(tuple(group))
    return groups


def _candidate_groupings(
    groups: Sequence[tuple[str, ...]],
    *,
    n_clusters: int,
    n_candidates: int,
    seed: int,
) -> list[tuple[tuple[str, ...], ...]]:
    """Distinct profiles, each ``n_clusters`` coherent groups drawn without replacement.

    Groups are reused across profiles — a collection of 100 queries yields only 50
    pairs — but no two profiles have the same group set, and the draw is seeded.
    """
    rng = random.Random(seed)
    seen: set[frozenset[tuple[str, ...]]] = set()
    out: list[tuple[tuple[str, ...], ...]] = []
    # Bounded so an over-large `n_candidates` on a small collection terminates
    # instead of spinning on duplicate draws.
    for _ in range(n_candidates * 200):
        if len(out) >= n_candidates:
            break
        pick = tuple(rng.sample(list(groups), n_clusters))
        key = frozenset(pick)
        if key in seen:
            continue
        seen.add(key)
        out.append(pick)
    return out


def _cluster_mass_variance(
    grouping: Sequence[tuple[str, ...]], masses: Mapping[str, float]
) -> float:
    """Spread of score mass across a profile's clusters — the imbalance selector.

    A cluster's mass is the mean mass of its queries; the profile's imbalance is
    the population variance across clusters. High variance means one theme's
    vocabulary sits far closer to the corpus than the others', which is exactly
    the condition C-003 claims to fix.
    """
    per_cluster = [
        float(np.mean([masses.get(qid, 0.0) for qid in group])) for group in grouping
    ]
    return float(np.var(per_cluster))


def _build(
    grouping: Sequence[Sequence[str]],
    *,
    profile_id: str,
    mode: str,
    query_texts: Mapping[str, str],
    qrels_by_query: Mapping[str, Mapping[str, int]],
    rng: random.Random,
) -> SyntheticProfile:
    """One profile from an ordered grouping, with union qrels and per-cluster sets."""
    ordered = list(grouping)
    rng.shuffle(ordered)  # declaration order is the argmax tie-break; do not fix it

    cluster_query_ids: dict[str, list[str]] = {
        f"c{i}": list(group) for i, group in enumerate(ordered)
    }
    query_ids = tuple(qid for group in ordered for qid in group)

    qrels: dict[str, int] = {}
    for qid in query_ids:
        for doc_id, grade in qrels_by_query.get(qid, {}).items():
            if grade > qrels.get(doc_id, -1):
                qrels[doc_id] = grade

    cluster_relevant = {
        cluster_id: {
            doc_id
            for qid in group
            for doc_id, grade in qrels_by_query.get(qid, {}).items()
            if grade > 0
        }
        for cluster_id, group in cluster_query_ids.items()
    }
    return SyntheticProfile(
        id=profile_id,
        mode=mode,
        query_ids=query_ids,
        query_texts={qid: query_texts[qid] for qid in query_ids},
        cluster_query_ids=cluster_query_ids,
        qrels=qrels,
        cluster_relevant=cluster_relevant,
    )


def synthesize(
    *,
    mode: str,
    query_ids: Sequence[str],
    query_texts: Mapping[str, str],
    vectors: np.ndarray,
    qrels_by_query: Mapping[str, Mapping[str, int]],
    masses: Mapping[str, float] | None = None,
    n_profiles: int = 30,
    k_interests: int = 6,
    n_clusters: int = 3,
    seed: int = 20260809,
    candidate_pool: int = 300,
) -> list[SyntheticProfile]:
    """``n_profiles`` synthetic profiles under one grouping ``mode``.

    ``coherent`` and ``random`` return the **same interest sets** in the same
    order of selection — only the partition differs — so the flat arm produces an
    identical ranking under both and any difference between the clustered arms is
    attributable to grouping alone. ``imbalanced`` re-selects from the same
    candidate pool by :func:`_cluster_mass_variance` and therefore needs
    ``masses``.

    ``vectors`` are the queries' embeddings in ``query_ids`` order.
    """
    if mode not in MODES:
        raise ValueError(f"unknown grouping mode {mode!r}; expected one of {MODES}")
    if k_interests % n_clusters:
        raise ValueError(
            f"k_interests={k_interests} must divide evenly into "
            f"n_clusters={n_clusters} so cluster size is not a second variable"
        )
    size = k_interests // n_clusters

    groups = coherent_groups(query_ids, vectors, size=size)
    if len(groups) < n_clusters:
        raise ValueError(
            f"{len(query_ids)} queries yield only {len(groups)} coherent group(s) "
            f"of size {size} — too few for {n_clusters} clusters per profile"
        )
    candidates = _candidate_groupings(
        groups, n_clusters=n_clusters, n_candidates=candidate_pool, seed=seed
    )

    if mode == "imbalanced":
        if not masses:
            raise ValueError("the imbalanced mode needs per-query score masses")
        chosen = sorted(
            candidates,
            key=lambda grouping: -_cluster_mass_variance(grouping, masses),
        )[:n_profiles]
    else:
        chosen = candidates[:n_profiles]

    profiles: list[SyntheticProfile] = []
    for i, grouping in enumerate(chosen):
        rng = random.Random(f"{seed}:{mode}:{i}")
        if mode == "random":
            # Same interests as `coherent`, repartitioned into equal-size clusters
            # by a seeded shuffle. Cluster structure becomes noise.
            flat = [qid for group in grouping for qid in group]
            rng.shuffle(flat)
            grouping = tuple(
                tuple(flat[j : j + size]) for j in range(0, len(flat), size)
            )
        profiles.append(
            _build(
                grouping,
                profile_id=f"{mode}-{i:03d}",
                mode=mode,
                query_texts=query_texts,
                qrels_by_query=qrels_by_query,
                rng=rng,
            )
        )
    return profiles


# --- inputs the synthesiser needs, read off a dataset -----------------------


def qrels_by_query(dataset) -> dict[str, dict[str, int]]:
    """`query_id -> {doc_id: grade}` for the whole collection."""
    out: dict[str, dict[str, int]] = {}
    for qrel in dataset.qrels_iter():
        out.setdefault(qrel.query_id, {})[qrel.doc_id] = int(qrel.relevance)
    return out


def query_masses(
    queries: Sequence[tuple[str, str]],
    index,
    *,
    depth: int = 100,
) -> dict[str, float]:
    """Each query's **score mass**: the mean cosine of its top ``depth`` dense hits.

    The imbalance selector's input, and the honest reading of "one theme's
    vocabulary sits closer to the corpus than another's". Deliberately *not* the
    query's judged-document count: that is the denominator of
    `min_cluster_recall`, so selecting on it would bias the metric being reported.

    Fused scores are unusable for this — `fuse_interest` min-max normalizes within
    each interest, so every query's best candidate is 1.0 by construction and the
    magnitudes are not comparable across queries. Raw cosine is.
    """
    from tools.retrieval import embeddings

    masses: dict[str, float] = {}
    for query_id, text in queries:
        vector = embeddings.embed_text(text)
        hits = index.search(vector, limit=depth)
        masses[query_id] = (
            float(np.mean([sim for _doc, sim in hits])) if hits else 0.0
        )
    return masses


def query_vectors(queries: Sequence[tuple[str, str]]) -> np.ndarray:
    """Embed every query with the production encoder, in the given order."""
    from tools.retrieval import embeddings

    return np.asarray(
        [embeddings.embed_text(text) for _query_id, text in queries],
        dtype=np.float32,
    )

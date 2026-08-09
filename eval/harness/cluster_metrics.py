"""Per-cluster coverage metrics — the one place this harness hand-rolls a metric.

**Why this violates the standing rule.** `harness/scoring.py` says never hand-roll
a metric, and that rule is right: `ir_measures` is the implementation the LongEval
overview papers score with, so a number produced through it is comparable to a
published one. Nothing here replaces it — the relevance family (`nDCG@10`,
`R@100`) still goes through `ir_measures` untouched.

But no IR toolkit implements per-cluster coverage, and none can: a *cluster* is a
property of the **profile** doing the searching, not of the collection. There is
no qrels file in the world that says "this document belongs to the user's second
research theme". The attribution has to be derived from which of the profile's
constituent queries judged the document relevant, which only the harness knows.

C-003 is a coverage claim — "one vocabulary-dominant theme does not monopolise the
feed" — and no standard metric can see it. nDCG@10 over a union of judgments is
blind to which theme the relevant documents came from. So these three exist, and
because they are hand-written they carry the obligations the rule was protecting:
unit tests with hand-computed expected values (`eval/tests/test_cluster_metrics.py`)
and a note in the experiment's `ISSUES.md`.

The three, in order of how much weight they carry:

- :func:`min_cluster_recall` — **primary.** The worst-served cluster's recall.
  "No theme is starved" is literally the claim, so the minimum is literally the
  metric.
- :func:`cluster_coverage` — how many clusters got *anything*. Coarser, and the
  one that reads clearly in a figure.
- :func:`cluster_gini` — inequality of the per-cluster share. Continuous, so it
  catches partial monopolisation that the other two round away.

A document relevant to more than one cluster counts for **each** of them. That is
deliberate: a cluster is served by a document that is relevant to it, regardless
of whether some other cluster is also served by the same document.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

#: The cut-offs every profile run reports. `@10` is the primary — it is the depth
#: at which a feed actually competes for attention.
DEFAULT_CUTOFFS = (10, 100)


def _served_counts(
    ranked_ids: Sequence[str],
    cluster_relevant: Mapping[str, set[str]],
    k: int,
) -> dict[str, int]:
    """Per cluster, how many of its relevant documents appear in the top ``k``.

    Clusters with no relevant documents at all are excluded outright: they have no
    recall to be starved of, and leaving them in would drag every profile's
    minimum to zero for a reason that has nothing to do with aggregation.
    """
    top = set(ranked_ids[:k])
    return {
        cluster_id: len(top & relevant)
        for cluster_id, relevant in cluster_relevant.items()
        if relevant
    }


def min_cluster_recall(
    ranked_ids: Sequence[str],
    cluster_relevant: Mapping[str, set[str]],
    *,
    k: int,
) -> float:
    """Recall of the **worst-served** cluster in the top ``k``. Higher is better.

    ``cluster_relevant`` maps ``cluster_id -> {relevant doc ids}``, built from the
    qrels of that cluster's own constituent queries. Returns ``0.0`` when no
    cluster has any relevant document (nothing to measure, and the profile is
    dropped from the paired comparison by the caller).
    """
    served = _served_counts(ranked_ids, cluster_relevant, k)
    if not served:
        return 0.0
    return min(
        served[cluster_id] / len(cluster_relevant[cluster_id]) for cluster_id in served
    )


def cluster_coverage(
    ranked_ids: Sequence[str],
    cluster_relevant: Mapping[str, set[str]],
    *,
    k: int,
) -> float:
    """Share of judgeable clusters with >= 1 relevant doc in the top ``k``."""
    served = _served_counts(ranked_ids, cluster_relevant, k)
    if not served:
        return 0.0
    return sum(1 for count in served.values() if count > 0) / len(served)


def cluster_gini(
    ranked_ids: Sequence[str],
    cluster_relevant: Mapping[str, set[str]],
    *,
    k: int,
) -> float:
    """Gini coefficient of the per-cluster share of relevant docs in the top ``k``.

    **Lower is better** — 0 is a perfectly even split across clusters, and it
    approaches ``1 - 1/C`` when a single cluster takes everything. This is the
    opposite direction from the other two metrics, which is why it is reported
    under its own name rather than folded into a single "coverage" number.

    An empty top ``k`` (no relevant documents retrieved at all) returns ``0.0``,
    the conventional Gini of an all-zero vector. That is *not* a good outcome —
    it is an undefined one — so it must always be read next to
    :func:`cluster_coverage`, which will be ``0.0`` in exactly that case.
    """
    served = _served_counts(ranked_ids, cluster_relevant, k)
    if not served:
        return 0.0
    counts = sorted(served.values())
    total = sum(counts)
    if total == 0:
        return 0.0
    n = len(counts)
    weighted = sum((i + 1) * value for i, value in enumerate(counts))
    return (2.0 * weighted - (n + 1) * total) / (n * total)


def coverage_metrics(
    ranked_ids: Sequence[str],
    cluster_relevant: Mapping[str, set[str]],
    *,
    cutoffs: Sequence[int] = DEFAULT_CUTOFFS,
) -> dict[str, float]:
    """All three metrics at every cut-off, named as they appear in results files."""
    out: dict[str, float] = {}
    for k in cutoffs:
        out[f"min_cluster_recall@{k}"] = min_cluster_recall(
            ranked_ids, cluster_relevant, k=k
        )
        out[f"cluster_coverage@{k}"] = cluster_coverage(
            ranked_ids, cluster_relevant, k=k
        )
        out[f"cluster_gini@{k}"] = cluster_gini(ranked_ids, cluster_relevant, k=k)
    return out

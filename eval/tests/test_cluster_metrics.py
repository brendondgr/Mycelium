"""Hand-computed fixtures for the three hand-rolled coverage metrics.

`harness/cluster_metrics.py` breaks the harness's standing "never hand-roll a
metric" rule, for the reason given in its docstring. The price of that exception
is this file: every expected value below is worked out by hand in the comment
above it, so the metrics are pinned to arithmetic a reader can check rather than
to whatever the implementation happens to return.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.cluster_metrics import (  # noqa: E402
    cluster_coverage,
    cluster_gini,
    coverage_metrics,
    min_cluster_recall,
)

# Three clusters with 2, 4 and 5 relevant documents. The ranking below puts
# a1, a2 (all of A), b1 (1 of 4 of B) and nothing from C in the top 5.
CLUSTERS = {
    "A": {"a1", "a2"},
    "B": {"b1", "b2", "b3", "b4"},
    "C": {"c1", "c2", "c3", "c4", "c5"},
}
RANKED = ["a1", "x1", "a2", "b1", "x2", "c1", "b2", "x3", "c2", "b3"]


# top-5 = a1 x1 a2 b1 x2 → A 2/2 = 1.0, B 1/4 = 0.25, C 0/5 = 0.0 → min 0.0
def test_min_cluster_recall_is_the_starved_cluster() -> None:
    assert min_cluster_recall(RANKED, CLUSTERS, k=5) == pytest.approx(0.0)


# top-10 = the whole list → A 2/2 = 1.0, B 3/4 = 0.75, C 2/5 = 0.4 → min 0.4
def test_min_cluster_recall_at_full_depth() -> None:
    assert min_cluster_recall(RANKED, CLUSTERS, k=10) == pytest.approx(0.4)


# top-5 serves A and B but not C → 2 of 3 clusters
def test_cluster_coverage_counts_clusters_with_any_hit() -> None:
    assert cluster_coverage(RANKED, CLUSTERS, k=5) == pytest.approx(2 / 3)
    assert cluster_coverage(RANKED, CLUSTERS, k=10) == pytest.approx(1.0)


# top-5 counts are A=2, B=1, C=0. Sorted ascending [0, 1, 2], n=3, total=3.
# G = (2*(1*0 + 2*1 + 3*2) - (3+1)*3) / (3*3) = (2*8 - 12) / 9 = 4/9
def test_cluster_gini_measures_monopolisation() -> None:
    assert cluster_gini(RANKED, CLUSTERS, k=5) == pytest.approx(4 / 9)


# top-10 counts are A=2, B=3, C=2 → sorted [2, 2, 3], total=7.
# G = (2*(1*2 + 2*2 + 3*3) - 4*7) / (3*7) = (2*15 - 28) / 21 = 2/21
def test_cluster_gini_falls_as_the_split_evens_out() -> None:
    assert cluster_gini(RANKED, CLUSTERS, k=10) == pytest.approx(2 / 21)


# One cluster taking everything: counts [0, 0, 3], total=3.
# G = (2*(1*0 + 2*0 + 3*3) - 4*3) / (3*3) = (18 - 12) / 9 = 2/3 = 1 - 1/C
def test_cluster_gini_peaks_at_one_minus_one_over_c() -> None:
    ranked = ["b1", "b2", "b3"]
    assert cluster_gini(ranked, CLUSTERS, k=3) == pytest.approx(2 / 3)


def test_clusters_with_no_judgments_are_excluded_not_scored_zero() -> None:
    """An unjudgeable cluster has no recall to be starved of.

    Counting it as 0.0 would drag every profile's minimum to zero for a reason
    that has nothing to do with aggregation, which would make the primary metric
    a measure of the qrels rather than of the ranker.
    """
    clusters = {**CLUSTERS, "D": set()}
    assert min_cluster_recall(RANKED, clusters, k=10) == pytest.approx(0.4)
    assert cluster_coverage(RANKED, clusters, k=10) == pytest.approx(1.0)


def test_nothing_relevant_retrieved_reads_as_zero_coverage() -> None:
    """Gini's all-zero convention is 0.0 — only legible next to coverage 0.0."""
    ranked = ["x1", "x2", "x3"]
    assert min_cluster_recall(ranked, CLUSTERS, k=3) == 0.0
    assert cluster_coverage(ranked, CLUSTERS, k=3) == 0.0
    assert cluster_gini(ranked, CLUSTERS, k=3) == 0.0


def test_a_document_relevant_to_two_clusters_serves_both() -> None:
    clusters = {"A": {"shared"}, "B": {"shared"}}
    assert min_cluster_recall(["shared"], clusters, k=1) == pytest.approx(1.0)
    assert cluster_coverage(["shared"], clusters, k=1) == pytest.approx(1.0)


def test_coverage_metrics_emits_every_metric_at_every_cutoff() -> None:
    out = coverage_metrics(RANKED, CLUSTERS, cutoffs=(5, 10))
    assert set(out) == {
        "min_cluster_recall@5",
        "cluster_coverage@5",
        "cluster_gini@5",
        "min_cluster_recall@10",
        "cluster_coverage@10",
        "cluster_gini@10",
    }
    assert out["min_cluster_recall@10"] == pytest.approx(0.4)

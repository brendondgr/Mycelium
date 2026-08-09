"""Synthetic profile construction. No collection download, no Django.

The properties the C-003 ablation's validity rests on:

1. `coherent` really does group similar interests, and `random` really does not.
2. `coherent` and `random` describe the **same** interest sets, so the flat arm
   is identical between them and any clustered difference is grouping alone.
3. Union qrels keep the maximum grade, and each cluster carries only its own
   constituent queries' relevant documents.
4. Everything is reproducible from the seed, and cluster **declaration order** is
   shuffled — `combine_clusters` breaks argmax ties by earliest cluster, so a
   fixed order would be a hidden variable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.profiles import coherent_groups, synthesize  # noqa: E402

# Six queries in three obvious themes: (q0, q1) share an axis, (q2, q3) another,
# (q4, q5) a third. Any honest coherence procedure recovers exactly those pairs.
QUERY_IDS = ["q0", "q1", "q2", "q3", "q4", "q5"]
QUERY_TEXTS = {qid: f"topic {qid}" for qid in QUERY_IDS}
VECTORS = np.array(
    [
        [1.0, 0.0, 0.0],
        [0.99, 0.1, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.99, 0.1],
        [0.0, 0.0, 1.0],
        [0.1, 0.0, 0.99],
    ],
    dtype=np.float32,
)
QRELS = {
    "q0": {"d1": 2, "d2": 1},
    "q1": {"d1": 1, "d3": 1},   # d1 is judged twice: 2 must win
    "q2": {"d4": 1, "d5": 0},   # grade 0 is judged, not relevant
    "q3": {"d6": 2},
    "q4": {"d7": 1},
    "q5": {"d8": 1},
}
MASSES = {"q0": 0.9, "q1": 0.9, "q2": 0.2, "q3": 0.2, "q4": 0.5, "q5": 0.5}


def _kwargs(**overrides):
    base = dict(
        query_ids=QUERY_IDS,
        query_texts=QUERY_TEXTS,
        vectors=VECTORS,
        qrels_by_query=QRELS,
        n_profiles=1,
        k_interests=6,
        n_clusters=3,
        seed=7,
        candidate_pool=8,
    )
    return {**base, **overrides}


def _partition(profile) -> set[frozenset[str]]:
    return {frozenset(group) for group in profile.cluster_query_ids.values()}


def test_coherent_groups_recovers_the_planted_themes() -> None:
    groups = coherent_groups(QUERY_IDS, VECTORS, size=2)
    assert {frozenset(g) for g in groups} == {
        frozenset({"q0", "q1"}),
        frozenset({"q2", "q3"}),
        frozenset({"q4", "q5"}),
    }


def test_coherent_groups_is_deterministic() -> None:
    assert coherent_groups(QUERY_IDS, VECTORS, size=2) == coherent_groups(
        QUERY_IDS, VECTORS, size=2
    )


def test_coherent_and_random_share_the_same_interest_sets() -> None:
    """The negative control is only valid if the flat arm cannot tell them apart."""
    coherent = synthesize(mode="coherent", **_kwargs())[0]
    shuffled = synthesize(mode="random", **_kwargs())[0]
    assert set(coherent.query_ids) == set(shuffled.query_ids)
    assert coherent.qrels == shuffled.qrels


def test_random_repartitions_into_equal_clusters() -> None:
    shuffled = synthesize(mode="random", **_kwargs())[0]
    assert len(shuffled.cluster_query_ids) == 3
    assert all(len(g) == 2 for g in shuffled.cluster_query_ids.values())
    # With three planted pairs, a shuffle that reproduced the coherent partition
    # would be a 1-in-15 coincidence; this seed does not.
    coherent = synthesize(mode="coherent", **_kwargs())[0]
    assert _partition(shuffled) != _partition(coherent)


def test_union_qrels_keep_the_maximum_grade() -> None:
    profile = synthesize(mode="coherent", **_kwargs())[0]
    assert profile.qrels["d1"] == 2  # judged 2 by q0 and 1 by q1
    assert profile.qrels["d5"] == 0
    assert profile.n_relevant == 7  # d1..d4, d6..d8; d5 is judged non-relevant


def test_each_cluster_carries_only_its_own_relevant_documents() -> None:
    profile = synthesize(mode="coherent", **_kwargs())[0]
    by_queries = {
        frozenset(queries): profile.cluster_relevant[cluster_id]
        for cluster_id, queries in profile.cluster_query_ids.items()
    }
    assert by_queries[frozenset({"q0", "q1"})] == {"d1", "d2", "d3"}
    assert by_queries[frozenset({"q2", "q3"})] == {"d4", "d6"}  # d5 has grade 0
    assert by_queries[frozenset({"q4", "q5"})] == {"d7", "d8"}


def test_imbalanced_selects_the_widest_score_mass_spread() -> None:
    profile = synthesize(mode="imbalanced", masses=MASSES, **_kwargs())[0]
    means = [
        float(np.mean([MASSES[qid] for qid in group]))
        for group in profile.cluster_query_ids.values()
    ]
    # The planted pairs give cluster masses {0.9, 0.2, 0.5} — the only grouping of
    # these six queries into coherent pairs, and a genuinely lopsided one.
    assert sorted(means) == pytest.approx([0.2, 0.5, 0.9])


def test_imbalanced_refuses_to_guess_at_score_mass() -> None:
    with pytest.raises(ValueError, match="score masses"):
        synthesize(mode="imbalanced", **_kwargs())


def test_the_same_seed_reproduces_the_same_profiles() -> None:
    first = synthesize(mode="coherent", **_kwargs())
    second = synthesize(mode="coherent", **_kwargs())
    assert [p.cluster_query_ids for p in first] == [p.cluster_query_ids for p in second]


def test_cluster_declaration_order_is_shuffled_across_profiles() -> None:
    """Declaration order is the argmax tie-break, so it must not be a constant.

    Candidate groupings are deduplicated as *sets* of groups, so no two profiles
    share a partition and orderings cannot be compared within one. What the
    assertion checks instead is that declaration order is not a function of the
    groups' contents: for at least some profiles the declared order is not the
    order the groups would sort into.
    """
    ids = [f"t{i}" for i in range(20)]
    vectors = np.zeros((20, 10), dtype=np.float32)
    for i in range(20):
        vectors[i, i // 2] = 1.0
        vectors[i, (i // 2 + 1) % 10] = 0.05 * (i % 2)
    profiles = synthesize(
        mode="coherent",
        **_kwargs(
            query_ids=ids,
            query_texts={qid: qid for qid in ids},
            vectors=vectors,
            qrels_by_query={qid: {f"d{qid}": 1} for qid in ids},
            n_profiles=40,
            candidate_pool=120,
        ),
    )
    unsorted_orders = 0
    for profile in profiles:
        declared = [tuple(sorted(g)) for g in profile.cluster_query_ids.values()]
        if declared != sorted(declared):
            unsorted_orders += 1
    assert unsorted_orders > len(profiles) // 4


def test_cluster_size_must_divide_evenly() -> None:
    with pytest.raises(ValueError, match="divide evenly"):
        synthesize(mode="coherent", **_kwargs(k_interests=5, n_clusters=2))


def test_too_few_queries_is_an_error_not_a_silent_short_profile() -> None:
    with pytest.raises(ValueError, match="too few"):
        synthesize(
            mode="coherent",
            **_kwargs(
                query_ids=QUERY_IDS[:4],
                vectors=VECTORS[:4],
                n_clusters=3,
                k_interests=6,
            ),
        )

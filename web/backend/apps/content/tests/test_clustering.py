"""Reading interest clusters out of the contract + the per-cluster watch seed.

Pure functions over plain dicts — no database, no pgvector.
"""

from apps.content.clustering import (
    IMPLICIT_CLUSTER_ID,
    Cluster,
    cluster_interests,
    cluster_labels,
    make_cluster_id,
    seed_watch_topics,
)


def _clustered() -> dict:
    return {
        "version": 2,
        "areas": ["agentic AI in healthcare", "medical imaging", "data assimilation"],
        "keywords": ["RAG", "PINNs"],
        "clusters": [
            {
                "id": "c-medai",
                "label": "Medical AI Agents",
                "areas": ["agentic AI in healthcare", "medical imaging"],
            },
            {
                "id": "c-ocean",
                "label": "Oceanography & Data Assimilation",
                "areas": ["data assimilation"],
            },
        ],
    }


# ---- cluster_interests ------------------------------------------------------


def test_no_areas_returns_empty() -> None:
    assert cluster_interests({}) == []
    assert cluster_interests(None) == []


def test_v1_fallback_single_implicit_cluster() -> None:
    clusters = cluster_interests({"areas": ["a", "b", "c"]})
    assert len(clusters) == 1
    assert clusters[0].is_implicit
    assert clusters[0].id == IMPLICIT_CLUSTER_ID
    assert clusters[0].areas == ["a", "b", "c"]


def test_explicit_clusters_parsed() -> None:
    clusters = cluster_interests(_clustered())
    assert [c.id for c in clusters] == ["c-medai", "c-ocean"]
    assert clusters[0].areas == ["agentic AI in healthcare", "medical imaging"]
    assert clusters[1].areas == ["data assimilation"]
    assert not clusters[0].is_implicit


def test_stale_cluster_area_dropped() -> None:
    # A cluster references an area no longer declared — it is self-healing (the
    # phantom area is simply not included).
    data = _clustered()
    data["clusters"][0]["areas"].append("removed area")
    clusters = cluster_interests(data)
    assert "removed area" not in clusters[0].areas


def test_orphan_area_self_heals_to_implicit() -> None:
    # A declared area assigned to no cluster (hand-edited blob) is not dropped
    # from scoring; it lands in a trailing implicit cluster.
    data = _clustered()
    data["areas"].append("PINNs research")
    clusters = cluster_interests(data)
    assert clusters[-1].is_implicit
    assert clusters[-1].areas == ["PINNs research"]


def test_cluster_labels_map() -> None:
    labels = cluster_labels(_clustered())
    assert labels["c-medai"] == "Medical AI Agents"
    assert labels["c-ocean"] == "Oceanography & Data Assimilation"


# ---- make_cluster_id --------------------------------------------------------


def test_make_cluster_id_slugifies() -> None:
    assert make_cluster_id("Medical AI Agents") == "c-medical-ai-agents"
    assert make_cluster_id("Oceanography & Data Assimilation") == (
        "c-oceanography-data-assimilation"
    )


def test_make_cluster_id_disambiguates() -> None:
    existing = ["c-ocean"]
    assert make_cluster_id("Ocean", existing) == "c-ocean-2"
    assert make_cluster_id("Ocean", ["c-ocean", "c-ocean-2"]) == "c-ocean-3"


def test_make_cluster_id_empty_label() -> None:
    assert make_cluster_id("") == "c-cluster"


# ---- seed_watch_topics ------------------------------------------------------


def test_seed_per_cluster_label_then_areas_then_keywords() -> None:
    topics = seed_watch_topics(_clustered())
    # Each real cluster contributes its label then its areas; keywords last.
    assert topics == [
        "Medical AI Agents",
        "agentic AI in healthcare",
        "medical imaging",
        "Oceanography & Data Assimilation",
        "data assimilation",
        "RAG",
        "PINNs",
    ]


def test_seed_v1_backward_compatible() -> None:
    # No clusters → implicit cluster's label is skipped → areas + keywords, exactly
    # the historical seeding.
    topics = seed_watch_topics({"areas": ["a", "b"], "keywords": ["k"]})
    assert topics == ["a", "b", "k"]


def test_seed_dedupes_and_caps() -> None:
    topics = seed_watch_topics(
        {"areas": ["x"], "keywords": ["x", "y"]}, cap=2
    )
    assert topics == ["x", "y"]  # "x" not repeated, capped at 2


def test_seed_no_interests_empty() -> None:
    assert seed_watch_topics({}) == []


def test_cluster_dataclass_shape() -> None:
    c = Cluster(id="c-x", label="X", areas=["a"])
    assert not c.is_implicit

"""Cluster proposal at intake — LLM grouping, geometric fallback, valid partition."""

import json

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.intake.clusters import (
    compose_clusters,
    propose_clusters,
    sort_into_clusters,
)

_AREAS = ["agentic AI in healthcare", "medical imaging", "data assimilation", "PINNs"]


def _all_areas(clusters) -> set[str]:
    return {a for c in clusters for a in c["areas"]}


def _assert_partition(clusters, areas) -> None:
    members = [a for c in clusters for a in c["areas"]]
    assert _all_areas(clusters) == set(areas)  # every area present
    assert len(members) == len(set(members))  # no area in two clusters
    ids = [c["id"] for c in clusters]
    assert len(ids) == len(set(ids))  # unique ids
    assert all(c["id"] and c["label"] and c["areas"] for c in clusters)


def test_llm_proposal_partitions_areas() -> None:
    def fake_complete(_prompt: str) -> str:
        return json.dumps(
            {
                "clusters": [
                    {
                        "label": "Medical AI",
                        "areas": ["agentic AI in healthcare", "medical imaging"],
                    },
                    {"label": "Scientific ML", "areas": ["data assimilation", "PINNs"]},
                ]
            }
        )

    clusters, source = propose_clusters(_AREAS, complete=fake_complete)
    assert source == "llm"
    _assert_partition(clusters, _AREAS)
    assert {c["label"] for c in clusters} == {"Medical AI", "Scientific ML"}


def test_llm_phantom_and_missing_areas_are_healed() -> None:
    # The model drops one real area and invents a phantom — finalize must sweep the
    # dropped area into a cluster and ignore the phantom.
    def fake_complete(_prompt: str) -> str:
        return json.dumps(
            {
                "clusters": [
                    {"label": "A", "areas": ["agentic AI in healthcare", "quantum"]},
                    {"label": "B", "areas": ["medical imaging", "data assimilation"]},
                ]
            }
        )

    clusters, _source = propose_clusters(_AREAS, complete=fake_complete)
    _assert_partition(clusters, _AREAS)  # PINNs swept in, "quantum" ignored


def test_geometric_fallback_when_llm_unusable() -> None:
    def bad_complete(_prompt: str) -> str:
        return "not json at all"

    def fake_embed(texts):
        # Two clean groups on a 2-axis space: medical vs sciml.
        axis = {
            "agentic AI in healthcare": [1.0, 0.0],
            "medical imaging": [0.9, 0.1],
            "data assimilation": [0.0, 1.0],
            "PINNs": [0.1, 0.9],
        }
        return [axis.get(t, [0.5, 0.5]) for t in texts]

    clusters, source = propose_clusters(
        _AREAS, complete=bad_complete, embed=fake_embed
    )
    assert source == "geometric"
    _assert_partition(clusters, _AREAS)


def test_no_llm_no_embedder_still_partitions() -> None:
    clusters, source = propose_clusters(
        _AREAS, complete=lambda _p: None, embed=lambda _t: None
    )
    assert source == "geometric"
    _assert_partition(clusters, _AREAS)


def test_single_area_single_cluster() -> None:
    clusters, source = propose_clusters(["oceanography"], complete=lambda _p: None)
    assert source == "single"
    assert len(clusters) == 1
    assert clusters[0]["areas"] == ["oceanography"]


def test_empty_areas() -> None:
    clusters, source = propose_clusters([], complete=lambda _p: None)
    assert clusters == []


def test_sort_into_clusters_preserves_ids() -> None:
    existing = [
        {"id": "c-med", "label": "Medical AI", "areas": ["agentic AI in healthcare"]},
        {"id": "c-sci", "label": "Scientific ML", "areas": ["PINNs"]},
    ]

    def fake_embed(texts):
        axis = {
            "agentic AI in healthcare": [1.0, 0.0],
            "PINNs": [0.0, 1.0],
            "medical imaging": [0.95, 0.05],  # nearest to medical
            "data assimilation": [0.05, 0.95],  # nearest to sciml
        }
        return [axis.get(t, [0.5, 0.5]) for t in texts]

    updated = sort_into_clusters(
        existing, ["medical imaging", "data assimilation"], embed=fake_embed
    )
    by_id = {c["id"]: c for c in updated}
    assert set(by_id) == {"c-med", "c-sci"}  # ids preserved, no new clusters
    assert "medical imaging" in by_id["c-med"]["areas"]
    assert "data assimilation" in by_id["c-sci"]["areas"]


# -- compose (theme -> sub-topic, may invent) --------------------------------


def _compose_partition(clusters) -> None:
    """A composed result is a valid stable-id partition of its own area union."""
    members = [a for c in clusters for a in c["areas"]]
    assert len(members) == len(set(members))  # no sub-topic in two clusters
    ids = [c["id"] for c in clusters]
    assert len(ids) == len(set(ids))
    assert all(c["id"] and c["label"] and c["areas"] for c in clusters)


def test_compose_builds_themes_with_subtopics() -> None:
    # Free-text instruction -> niche themes, each with several concrete (partly
    # invented) sub-topics — the initial-build / instruct-box reasoning.
    def fake_complete(_prompt: str) -> str:
        return json.dumps(
            {
                "clusters": [
                    {
                        "label": "AI & Healthcare",
                        "areas": [
                            "AI agents in health",
                            "computer vision for health",
                            "robotic surgery",
                        ],
                    },
                    {
                        "label": "Robotics",
                        "areas": [
                            "vision-language-action models",
                            "robotic automation",
                        ],
                    },
                ]
            }
        )

    clusters, source = compose_clusters(
        instruction="AI in healthcare, and robotics like VLA and surgical robots",
        complete=fake_complete,
    )
    assert source == "llm"
    _compose_partition(clusters)
    assert {c["label"] for c in clusters} == {"AI & Healthcare", "Robotics"}
    # Sub-topics not present in any declared-area list were still accepted.
    union = _all_areas(clusters)
    assert "vision-language-action models" in union


def test_compose_preserves_existing_theme_id() -> None:
    existing = [
        {
            "id": "c-aihealth",
            "label": "AI & Healthcare",
            "areas": ["AI agents in health"],
        },
    ]

    def fake_complete(_prompt: str) -> str:
        return json.dumps(
            {
                "clusters": [
                    {
                        "label": "AI & Healthcare",
                        "areas": ["AI agents in health", "medical imaging"],
                    },
                    {"label": "Robotics", "areas": ["robotic surgery"]},
                ]
            }
        )

    clusters, _source = compose_clusters(
        instruction="refine my interests",
        existing_clusters=existing,
        complete=fake_complete,
    )
    by_label = {c["label"]: c for c in clusters}
    # The persisting theme keeps its original id; the new theme gets a fresh one.
    assert by_label["AI & Healthcare"]["id"] == "c-aihealth"
    assert by_label["Robotics"]["id"] != "c-aihealth"


def test_compose_clamps_to_caps() -> None:
    def fake_complete(_prompt: str) -> str:
        return json.dumps(
            {
                "clusters": [
                    {"label": f"Theme {i}", "areas": [f"a{i}", f"b{i}", f"c{i}"]}
                    for i in range(4)
                ]
            }
        )

    clusters, _source = compose_clusters(
        instruction="lots of things",
        complete=fake_complete,
        max_clusters=2,
        max_areas_per_cluster=2,
    )
    assert len(clusters) == 2
    assert all(len(c["areas"]) <= 2 for c in clusters)


def test_compose_fallback_keeps_existing_when_llm_down() -> None:
    existing = [
        {"id": "c-med", "label": "Medical AI", "areas": ["agentic AI in healthcare"]},
    ]
    clusters, source = compose_clusters(
        instruction="anything", existing_clusters=existing, complete=lambda _p: None
    )
    assert source == "fallback"
    assert clusters[0]["id"] == "c-med"


def test_compose_fallback_groups_areas_when_no_existing() -> None:
    clusters, source = compose_clusters(
        instruction="", areas=_AREAS, complete=lambda _p: None,
    )
    assert source == "fallback"
    assert _all_areas(clusters) == set(_AREAS)  # every declared area kept


def test_compose_empty_when_nothing_to_reason_over() -> None:
    clusters, source = compose_clusters(complete=lambda _p: None)
    assert clusters == []
    assert source == "fallback"


@pytest.mark.django_db
def test_compose_endpoint_instruct_mode() -> None:
    api = APIClient()
    user = User.objects.create_user("ci", password="x")
    api.force_authenticate(user)
    # No LLM configured in tests, so the instruct mode degrades to grouping the
    # supplied areas — the response shape (clusters + widened areas + seed) is
    # what we assert.
    resp = api.post(
        "/api/auth/intake/clusters/",
        {
            "instruction": "AI for healthcare and robotics",
            "areas": ["healthcare ML", "robotics"],
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"clusters", "areas", "watch_topics", "source"}
    assert _all_areas(body["clusters"]) == {"healthcare ML", "robotics"}
    assert set(body["areas"]) == {"healthcare ML", "robotics"}


@pytest.mark.django_db
def test_propose_endpoint(client=None) -> None:
    api = APIClient()
    user = User.objects.create_user("cp", password="x")
    api.force_authenticate(user)
    resp = api.post(
        "/api/auth/intake/clusters/",
        {"areas": ["oceanography", "healthcare ML"]},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "clusters" in body and "watch_topics" in body and "source" in body
    assert _all_areas(body["clusters"]) == {"oceanography", "healthcare ML"}

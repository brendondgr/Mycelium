"""Cluster proposal at intake — LLM grouping, geometric fallback, valid partition."""

import json

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.intake.clusters import (
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

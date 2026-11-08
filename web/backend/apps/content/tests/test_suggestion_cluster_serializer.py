"""SuggestionSerializer cluster attribution: live label resolution + null fallback."""

import pytest
from django.contrib.auth.models import User
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

from apps.content.serializers import SuggestionSerializer


def _score(user, *, signals) -> RelevanceScore:
    paper = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="OpenAlex",
        external_id=str(signals),
        metadata={"title": "A paper", "abstract": "x"},
    )
    return RelevanceScore.objects.create(
        content=paper, target_user=user, score=0.8, signals=signals
    )


@pytest.mark.django_db
def test_cluster_label_resolves_live_from_context() -> None:
    """A renamed cluster shows its new label without a re-score (context wins)."""
    user = User.objects.create_user("s1", password="x")
    score = _score(
        user,
        signals={
            "cluster_id": "c-ocean",
            "cluster_label": "Old Ocean Name",  # frozen at score time
            "per_cluster": {"c-ocean": 0.8, "c-med": 0.5},
            "bridge_cluster_ids": ["c-med"],
        },
    )
    data = SuggestionSerializer(
        score,
        context={"cluster_labels": {"c-ocean": "Oceanography", "c-med": "Medical AI"}},
    ).data
    assert data["cluster"] == {"id": "c-ocean", "label": "Oceanography"}
    assert data["per_cluster"] == {"c-ocean": 0.8, "c-med": 0.5}
    assert data["bridge_clusters"] == [{"id": "c-med", "label": "Medical AI"}]


@pytest.mark.django_db
def test_cluster_label_falls_back_to_frozen_without_context() -> None:
    user = User.objects.create_user("s2", password="x")
    score = _score(
        user,
        signals={"cluster_id": "c-ocean", "cluster_label": "Oceanography"},
    )
    data = SuggestionSerializer(score).data
    assert data["cluster"] == {"id": "c-ocean", "label": "Oceanography"}
    assert data["bridge_clusters"] == []


@pytest.mark.django_db
def test_flat_path_has_null_cluster() -> None:
    """A flat / single-cluster row carries no attribution — cluster is null."""
    user = User.objects.create_user("s3", password="x")
    score = _score(user, signals={"per_interest": {"graph": 0.9}})
    data = SuggestionSerializer(score).data
    assert data["cluster"] is None
    assert data["per_cluster"] == {}
    assert data["bridge_clusters"] == []

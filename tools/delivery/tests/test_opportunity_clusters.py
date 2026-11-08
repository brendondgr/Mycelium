"""Grants and conferences carry cluster attribution, like papers do.

The cards have rendered a cluster badge since the cluster sprint; until the matcher
scored opportunities per cluster there was simply never anything to put in it.

Postgres-gated: this exercises real pgvector retrieval, so it skips on SQLite the
same way ``test_retrieval.py`` does. The competing-candidate detail matters — a lone
candidate min-max normalises to 1.0 in *every* cluster and would appear to match all
of them, so discrimination has to be tested against a field of rivals.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.db import connection

from tools.recommendation.models import RelevanceScore
from tools.recommendation.opportunities import match_opportunities_for_user
from tools.retrieval.models import ContentItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def pgvector(db):
    if connection.vendor != "postgresql":
        pytest.skip("cluster-scoped opportunity matching requires PostgreSQL")


def _embed(text: str):
    from tools.retrieval.embeddings import embed_texts

    vectors = embed_texts([text])
    return vectors[0] if vectors else None


def _grant(external_id: str, title: str, abstract: str):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=external_id,
        metadata={"title": title, "abstract": abstract, "sponsor": "NSF"},
        embedding=_embed(f"{title} {abstract}"),
    )


def _user_with_clusters(username="clustered"):
    """A researcher with two genuinely distinct themes."""
    user = User.objects.create_user(username)
    profile = user.profile
    profile.interests = {
        "areas": [
            "medical imaging segmentation",
            "clinical decision support",
            "soft robotics actuators",
            "robot grasping control",
        ],
        "clusters": [
            {
                "id": "c-med",
                "label": "Medical AI",
                "areas": [
                    "medical imaging segmentation",
                    "clinical decision support",
                ],
            },
            {
                "id": "c-rob",
                "label": "Robotics",
                "areas": ["soft robotics actuators", "robot grasping control"],
            },
        ],
    }
    profile.save(update_fields=["interests"])
    return user


def _single_cluster_user(username="flat"):
    user = User.objects.create_user(username)
    profile = user.profile
    profile.interests = {"areas": ["medical imaging segmentation"]}
    profile.save(update_fields=["interests"])
    return user


def _corpus():
    """Rivals on both themes, so the argmax has something to discriminate against."""
    _grant(
        "g-med-1",
        "Deep learning for tumour segmentation in MRI",
        "Automated medical image segmentation for clinical radiology workflows.",
    )
    _grant(
        "g-med-2",
        "Clinical decision support from electronic health records",
        "Predictive models supporting diagnosis at the point of care.",
    )
    _grant(
        "g-rob-1",
        "Soft pneumatic actuators for compliant manipulators",
        "Design and control of soft robotic actuators for safe grasping.",
    )
    _grant(
        "g-rob-2",
        "Learning dexterous robot grasping from demonstration",
        "Robot manipulation policies for grasping unfamiliar objects.",
    )


def _signals_by_title(user) -> dict:
    rows = RelevanceScore.objects.filter(
        target_user=user, content__type=ContentItem.Type.GRANT
    ).select_related("content")
    return {(r.content.metadata or {}).get("title", ""): r.signals for r in rows}


def test_a_two_cluster_researcher_gets_grants_attributed_per_theme(
    pgvector,
) -> None:
    user = _user_with_clusters()
    _corpus()

    match_opportunities_for_user(user, "grants", complete=lambda _p: None)

    by_title = _signals_by_title(user)
    assert by_title, "the matcher surfaced nothing to attribute"

    labels = {
        title: sig.get("cluster_label")
        for title, sig in by_title.items()
        if sig.get("cluster_id")
    }
    assert labels, "no grant carried a cluster attribution"

    # Each grant lands in the theme it actually belongs to, not merely *a* theme.
    for title, label in labels.items():
        medical = "tumour" in title or "Clinical" in title
        expected = "Medical AI" if medical else "Robotics"
        assert label == expected, f"{title!r} attributed to {label!r}"


def test_attribution_records_the_scores_behind_it(pgvector) -> None:
    """`per_cluster` is what makes an attribution auditable rather than asserted."""
    user = _user_with_clusters("audited")
    _corpus()

    match_opportunities_for_user(user, "grants", complete=lambda _p: None)

    signals = [s for s in _signals_by_title(user).values() if s.get("cluster_id")]
    assert signals
    for sig in signals:
        per_cluster = sig.get("per_cluster") or {}
        assert per_cluster, "attribution with no per-cluster scores behind it"
        # The attributed cluster is the argmax, by construction.
        best = max(per_cluster, key=per_cluster.get)
        assert sig["cluster_id"] == best


def test_a_single_cluster_researcher_is_unchanged(pgvector) -> None:
    """The invariant every cluster feature here preserves: fewer than two real
    clusters keeps the flat path byte-for-byte, so nobody's feed changes shape
    just because the capability now exists."""
    user = _single_cluster_user()
    _corpus()

    match_opportunities_for_user(user, "grants", complete=lambda _p: None)

    for sig in _signals_by_title(user).values():
        assert sig.get("cluster_id") in (None, "")
        assert not sig.get("per_cluster")


def test_the_serializer_exposes_the_attribution_to_the_card(pgvector) -> None:
    """The grant card has always rendered a cluster badge; now it has a value."""
    from tools.delivery.serializers import GrantSerializer

    user = _user_with_clusters("serialized")
    _corpus()
    match_opportunities_for_user(user, "grants", complete=lambda _p: None)

    row = (
        RelevanceScore.objects.filter(
            target_user=user, content__type=ContentItem.Type.GRANT
        )
        .exclude(signals__cluster_id=None)
        .first()
    )
    assert row is not None

    data = GrantSerializer(
        row, context={"today": "2026-07-26", "cluster_labels": {"c-med": "Renamed"}}
    ).data
    assert "cluster" in data
    if data["cluster"] and data["cluster"]["id"] == "c-med":
        # A renamed cluster reads through live, without re-scoring anything.
        assert data["cluster"]["label"] == "Renamed"

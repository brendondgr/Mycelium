"""Staff merge and reverse concepts from the admin, and both are logged."""

import pytest
from django.urls import reverse

from apps.knowledge.linker import link
from apps.knowledge.models import Concept, ConceptMerge, Facet


@pytest.fixture
def pair(db, embedder):
    return link("uncertainty quantification").concept, link("UQ").concept


def test_merge_and_reverse_from_the_admin(admin_client, pair):
    target, source = pair
    response = admin_client.post(
        reverse("admin:knowledge_concept_changelist"),
        {"action": "merge_into_first", "_selected_action": [target.pk, source.pk]},
        follow=True,
    )
    assert response.status_code == 200
    source.refresh_from_db()
    assert (source.status, source.merged_into) == (Concept.Status.MERGED, target)

    record = ConceptMerge.objects.get(kind=ConceptMerge.Kind.MERGE)
    admin_client.post(
        reverse("admin:knowledge_conceptmerge_changelist"),
        {"action": "reverse", "_selected_action": [record.pk]},
        follow=True,
    )
    source.refresh_from_db()
    assert source.status == Concept.Status.ACTIVE
    assert ConceptMerge.objects.filter(kind=ConceptMerge.Kind.UNMERGE).exists()


def test_a_refused_merge_changes_nothing(admin_client, db, embedder):
    problem = link("segmentation", facet=Facet.PROBLEM).concept
    method = link("tracking", facet=Facet.METHOD).concept
    response = admin_client.post(
        reverse("admin:knowledge_concept_changelist"),
        {"action": "merge_into_first", "_selected_action": [problem.pk, method.pk]},
        follow=True,
    )
    assert "cannot be merged" in response.content.decode()
    assert not ConceptMerge.objects.exists()

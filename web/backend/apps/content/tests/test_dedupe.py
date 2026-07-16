"""Cleanup of cross-source duplicate paper rows (apps.content.dedupe)."""

import pytest
from django.contrib.auth.models import User

from apps.content.dedupe import (
    dedupe_papers,
    group_duplicate_papers,
    merge_content_items,
    pick_survivor,
)
from apps.content.models import ContentItem, RelevanceScore, SavedOpportunity


def _paper(source, external_id, **metadata):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source=source,
        external_id=external_id,
        metadata={"sources": [source], **metadata},
    )


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(username="researcher", password="pass-123")


@pytest.mark.django_db
def test_groups_duplicates_by_shared_arxiv():
    _paper("OpenAlex", "doi:10.48550/arxiv.2607.12764",
           title="EvoGraph-R1", doi="10.48550/arxiv.2607.12764", arxiv="2607.12764")
    _paper("SemanticScholar", "semanticscholar:abc",
           title="EvoGraph-R1", arxiv="2607.12764")
    # An unrelated paper must NOT be swept in.
    _paper("OpenAlex", "doi:10.1/other", title="Something Else", doi="10.1/other")

    groups = group_duplicate_papers()
    assert len(groups) == 1
    assert len(groups[0]) == 2


@pytest.mark.django_db
def test_survivor_prefers_embedding_then_sources():
    thin = _paper("SemanticScholar", "semanticscholar:abc", title="P", arxiv="1")
    rich = _paper("OpenAlex", "doi:10.1/p", title="P", doi="10.1/p", arxiv="1")
    rich.embedding = [0.1, 0.2, 0.3]
    rich.save(update_fields=["embedding"])

    assert pick_survivor([thin, rich]).pk == rich.pk


@pytest.mark.django_db
def test_merge_repoints_scores_and_keeps_higher(user):
    survivor = _paper("OpenAlex", "doi:10.1/p", title="P", doi="10.1/p", arxiv="1")
    loser = _paper("SemanticScholar", "semanticscholar:abc", title="P", arxiv="1")

    # Same user scored both copies; the loser's score is higher and must win.
    RelevanceScore.objects.create(content=survivor, target_user=user, score=0.40)
    RelevanceScore.objects.create(content=loser, target_user=user, score=0.90)

    merge_content_items(survivor, loser)

    assert not ContentItem.objects.filter(pk=loser.pk).exists()
    scores = RelevanceScore.objects.filter(target_user=user)
    assert scores.count() == 1
    assert scores.get().content_id == survivor.pk
    assert scores.get().score == pytest.approx(0.90)
    # Sources unioned onto the survivor.
    survivor.refresh_from_db()
    assert set(survivor.metadata["sources"]) == {"OpenAlex", "SemanticScholar"}


@pytest.mark.django_db
def test_merge_repoints_save_without_collision(user):
    survivor = _paper("OpenAlex", "doi:10.1/p", title="P", doi="10.1/p", arxiv="1")
    loser = _paper("SemanticScholar", "semanticscholar:abc", title="P", arxiv="1")
    SavedOpportunity.objects.create(
        user=user, content=loser, area=SavedOpportunity.Area.PAPER, title="P"
    )

    merge_content_items(survivor, loser)

    save = SavedOpportunity.objects.get(user=user)
    assert save.content_id == survivor.pk


@pytest.mark.django_db
def test_dedupe_papers_dry_run_then_apply(user):
    _paper("OpenAlex", "doi:10.1/p", title="P", doi="10.1/p", arxiv="1")
    _paper("SemanticScholar", "semanticscholar:abc", title="P", arxiv="1")

    dry = dedupe_papers(apply=False)
    assert dry.groups == 1
    assert dry.duplicates == 1
    assert dry.merged == 0
    assert ContentItem.objects.count() == 2  # nothing written

    applied = dedupe_papers(apply=True)
    assert applied.merged == 1
    assert ContentItem.objects.count() == 1

    # Idempotent: a second apply finds nothing.
    again = dedupe_papers(apply=True)
    assert again.groups == 0

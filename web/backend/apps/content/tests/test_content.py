import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import Lab
from apps.content.models import ContentItem, RelevanceScore
from apps.research.models import Project


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(username="researcher", password="pass-123")


@pytest.fixture
def paper(db: None) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="arXiv",
        metadata={"title": "On Mycelial Networks"},
    )


@pytest.mark.django_db
def test_content_item_types() -> None:
    grant = ContentItem.objects.create(type=ContentItem.Type.GRANT, source="grants.gov")
    assert grant.type == "grant"
    assert grant.embedding is None


@pytest.mark.django_db
def test_score_targets_user_profile(paper: ContentItem, user: User) -> None:
    score = RelevanceScore.objects.create(
        content=paper,
        target_user=user,
        score=0.87,
        signals={"interest": 0.9, "project": 0.0},
    )

    assert score.target_type == "user"
    assert score.target == user
    assert list(paper.scores.all()) == [score]


@pytest.mark.django_db
def test_score_targets_project(paper: ContentItem) -> None:
    lab = Lab.objects.create(name="Forest Lab", slug="forest-lab")
    project = Project.objects.create(scope_lab=lab, name="Roadmap")

    score = RelevanceScore.objects.create(
        content=paper, target_project=project, score=0.5
    )

    assert score.target_type == "project"
    assert score.target == project


@pytest.mark.django_db
def test_score_requires_exactly_one_target(paper: ContentItem, user: User) -> None:
    lab = Lab.objects.create(name="Forest Lab", slug="forest-lab")
    with pytest.raises(IntegrityError), transaction.atomic():
        RelevanceScore.objects.create(
            content=paper, target_user=user, target_lab=lab, score=0.1
        )


@pytest.mark.django_db
def test_score_rejects_no_target(paper: ContentItem) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RelevanceScore.objects.create(content=paper, score=0.1)


@pytest.mark.django_db
def test_score_clean_validates_target(paper: ContentItem) -> None:
    with pytest.raises(ValidationError):
        RelevanceScore(content=paper, score=0.1).clean()


@pytest.mark.django_db
def test_one_score_per_content_and_target(paper: ContentItem, user: User) -> None:
    RelevanceScore.objects.create(content=paper, target_user=user, score=0.5)

    with pytest.raises(IntegrityError), transaction.atomic():
        RelevanceScore.objects.create(content=paper, target_user=user, score=0.9)


@pytest.mark.django_db
def test_distinct_targets_share_a_content_item(paper: ContentItem, user: User) -> None:
    other = User.objects.create_user(username="second", password="pass-123")

    RelevanceScore.objects.create(content=paper, target_user=user, score=0.5)
    RelevanceScore.objects.create(content=paper, target_user=other, score=0.7)

    assert paper.scores.count() == 2

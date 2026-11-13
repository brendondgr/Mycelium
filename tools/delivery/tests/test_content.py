import pytest
from apps.accounts.models import Lab
from apps.research.models import Project
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from tools.delivery.models import SavedOpportunity
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem


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


@pytest.mark.django_db
def test_external_id_dedups_per_source() -> None:
    ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="arXiv", external_id="2406.00001"
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ContentItem.objects.create(
            type=ContentItem.Type.PAPER, source="arXiv", external_id="2406.00001"
        )


@pytest.mark.django_db
def test_same_external_id_allowed_across_sources() -> None:
    ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="arXiv", external_id="10.1/x"
    )
    # A different source may legitimately reuse the same identifier string.
    ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="OpenAlex", external_id="10.1/x"
    )

    assert ContentItem.objects.filter(external_id="10.1/x").count() == 2


@pytest.mark.django_db
def test_blank_external_id_is_exempt_from_dedup() -> None:
    # Manually-entered items without a source id must not collide with each other.
    ContentItem.objects.create(type=ContentItem.Type.GRANT, source="manual")
    ContentItem.objects.create(type=ContentItem.Type.GRANT, source="manual")

    assert ContentItem.objects.filter(source="manual").count() == 2


@pytest.mark.django_db
def test_conference_type_available() -> None:
    conf = ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="legacy",
        external_id="80246426",
    )
    assert conf.type == "conference"
    assert conf.get_type_display() == "Conference"


@pytest.mark.django_db
def test_saved_opportunity_unique_per_user_content(
    paper: ContentItem, user: User
) -> None:
    SavedOpportunity.objects.create(
        user=user,
        content=paper,
        area=SavedOpportunity.Area.GRANT,
        title="A grant",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        SavedOpportunity.objects.create(
            user=user,
            content=paper,
            area=SavedOpportunity.Area.GRANT,
            title="A grant (dup)",
        )


@pytest.mark.django_db
def test_saved_opportunity_survives_content_prune(
    paper: ContentItem, user: User
) -> None:
    """Pruning the global item must not destroy a user's saved deadline."""
    saved = SavedOpportunity.objects.create(
        user=user,
        content=paper,
        area=SavedOpportunity.Area.GRANT,
        title="Amazon Research Awards",
        deadline_date="2026-11-12",
        deadline_kind=SavedOpportunity.DeadlineKind.APPLICATION,
        snapshot={"title": "Amazon Research Awards", "amount": "Upper: $70,000 USD"},
    )

    paper.delete()  # the daily prune removes an expired ContentItem
    saved.refresh_from_db()

    assert saved.content_id is None  # SET_NULL, not cascade-deleted
    assert saved.title == "Amazon Research Awards"
    assert saved.snapshot["amount"] == "Upper: $70,000 USD"
    assert str(saved.deadline_date) == "2026-11-12"


@pytest.mark.django_db
def test_saved_opportunity_allows_null_content_duplicates(user: User) -> None:
    # Two pruned saves (content=None) must not collide under the partial unique key.
    SavedOpportunity.objects.create(
        user=user, area=SavedOpportunity.Area.CONFERENCE, title="One"
    )
    SavedOpportunity.objects.create(
        user=user, area=SavedOpportunity.Area.CONFERENCE, title="Two"
    )
    assert SavedOpportunity.objects.filter(user=user, content__isnull=True).count() == 2

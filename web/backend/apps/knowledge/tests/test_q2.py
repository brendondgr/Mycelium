"""Q2: which of a person's declared concepts are backed by their own papers?

The second of the four cross-entity queries (``docs/goals.md``, Next 1):
person → concept ← the person's works. A fixture person who declares three
things, publishes on two of them in other words, and publishes on one thing
they never declared.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import AuthorWork
from apps.knowledge import demonstrated, read, service
from apps.knowledge.models import WorkFacets


@pytest.fixture
def ada(db, embedder):
    embedder.near("semantic segmentation", "Semantic segmentation of imagery")
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    user.profile.interests = {
        "areas": ["Semantic segmentation of imagery", "Coral reef ecology"],
        "keywords": ["science policy"],
    }
    user.profile.save()
    service.project_declared(user)
    for source_id, method, problem in (
        ("W1", "semantic segmentation", "coral reef ecology"),
        ("W2", "semantic segmentation", "kelp forest decline"),
    ):
        work = AuthorWork.objects.create(
            verified=True,
            user=user, source="openalex", source_id=source_id, title=source_id
        )
        WorkFacets.objects.create(
            author_work=work, terms={"method": [method], "problem": [problem]}
        )
    demonstrated.record_person(user)
    return user


def test_q2_separates_said_shown_and_both(ada):
    rows = {row.surface: row for row in read.backing(ada)}
    both = rows["Semantic segmentation of imagery"]
    assert both.declared and both.demonstrated and len(both.works) == 2
    reef = rows["Coral reef ecology"]
    assert reef.declared and reef.demonstrated and len(reef.works) == 1
    assert rows["science policy"].declared_only
    kelp = rows["kelp forest decline"]
    assert kelp.demonstrated and not kelp.declared


def test_q2_is_about_one_person_only(ada):
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    assert read.backing(bo) == []
    assert all(row.concept_id for row in read.backing(ada))

"""Project team-relevance signal recompute (Feature D).

Uses deterministic 3-D vectors with ``embed_text`` mocked to ``None`` (so the
declared-focus + on-demand member embedding drop out), isolating the members and
engagement math. Every principle the brief asserts is checked here: no individual
profile is mutated, more positive engagement pulls the team vector toward a topic,
and a negative action lowers that topic's presence.
"""

import math
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab, LabMembership, Profile
from apps.content.models import ContentItem, ProjectProfile, RelevanceEvent
from apps.content.targets import target_for_project
from apps.content.team_profile import recompute_project_profile
from apps.research.models import Project, ProjectMember

_NO_EMBEDDER = "apps.content.team_profile.embeddings.embed_text"


def _cos(a, b) -> float:
    dot = sum(float(x) * float(y) for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    return dot / (na * nb) if na and nb else 0.0


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="L", slug="l")


def _member(username, lab, embedding=None) -> User:
    user = User.objects.create_user(username=username, password="p")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    if embedding is not None:
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.embedding = embedding
        profile.save(update_fields=["embedding"])
    return user


@pytest.fixture
def project(db, lab) -> Project:
    return Project.objects.create(name="P", scope_lab=lab)


def _paper(title, embedding) -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=title,
        metadata={"title": title, "abstract": title},
        embedding=embedding,
    )


def _event(project, user, content, action, weight) -> RelevanceEvent:
    return RelevanceEvent.objects.create(
        user=user, project=project, content=content, action=action, weight=weight
    )


@pytest.mark.django_db
def test_recompute_writes_vector_and_never_mutates_profiles(project, lab):
    m1 = _member("m1", lab, embedding=[1.0, 0.0, 0.0])
    m2 = _member("m2", lab, embedding=[0.0, 1.0, 0.0])
    ProjectMember.objects.create(project=project, user=m1)
    ProjectMember.objects.create(project=project, user=m2)

    with patch(_NO_EMBEDDER, return_value=None):
        recompute_project_profile(project, reason=ProjectProfile.Reason.MANUAL)

    project.refresh_from_db()
    assert project.embedding is not None  # a team vector was written
    profile_record = ProjectProfile.objects.get(project=project)
    assert profile_record.last_recomputed is not None
    # The individual member profiles are untouched — the team signal is separate.
    m1_embedding = list(Profile.objects.get(user=m1).embedding)
    m2_embedding = list(Profile.objects.get(user=m2).embedding)
    assert m1_embedding == pytest.approx([1.0, 0.0, 0.0])
    assert m2_embedding == pytest.approx([0.0, 1.0, 0.0])


@pytest.mark.django_db
def test_more_positive_engagement_pulls_team_vector(project, lab):
    members = [_member(f"m{i}", lab) for i in range(3)]
    for member in members:
        ProjectMember.objects.create(project=project, user=member)
    paper_a = _paper("A", [1.0, 0.0, 0.0])
    paper_b = _paper("B", [0.0, 1.0, 0.0])
    for member in members:  # 3 thumbs-up on A
        _event(project, member, paper_a, RelevanceEvent.Action.THUMBS_UP, 1.0)
    _event(project, members[0], paper_b, RelevanceEvent.Action.THUMBS_UP, 1.0)  # 1 on B

    with patch(_NO_EMBEDDER, return_value=None):
        recompute_project_profile(project)

    project.refresh_from_db()
    team = list(project.embedding)
    assert _cos(team, [1.0, 0.0, 0.0]) > _cos(team, [0.0, 1.0, 0.0])


@pytest.mark.django_db
def test_negative_weight_lowers_a_topics_presence(project, lab):
    member = _member("m", lab)
    ProjectMember.objects.create(project=project, user=member)
    paper_a = _paper("A", [1.0, 0.0, 0.0])
    paper_b = _paper("B", [0.0, 1.0, 0.0])
    _event(project, member, paper_a, RelevanceEvent.Action.THUMBS_UP, 1.0)
    event_b = _event(project, member, paper_b, RelevanceEvent.Action.THUMBS_UP, 1.0)

    with patch(_NO_EMBEDDER, return_value=None):
        recompute_project_profile(project)
    project.refresh_from_db()
    presence_when_liked = _cos(list(project.embedding), [0.0, 1.0, 0.0])

    event_b.action = RelevanceEvent.Action.THUMBS_DOWN
    event_b.weight = -0.7
    event_b.save(update_fields=["action", "weight"])
    with patch(_NO_EMBEDDER, return_value=None):
        recompute_project_profile(project)
    project.refresh_from_db()
    presence_when_disliked = _cos(list(project.embedding), [0.0, 1.0, 0.0])

    assert presence_when_disliked < presence_when_liked


@pytest.mark.django_db
def test_target_for_project_merges_team_interests(project):
    ProjectProfile.objects.create(
        project=project,
        interests={"areas": ["reef ecology"], "keywords": ["coral"]},
        recompute_reason=ProjectProfile.Reason.MANUAL,
    )
    target = target_for_project(project)
    assert "reef ecology" in target.interests["areas"]
    assert "coral" in target.interests["keywords"]


@pytest.mark.django_db
def test_project_target_prefers_stored_team_vector(project):
    project.embedding = [0.1, 0.2, 0.3]
    project.save(update_fields=["embedding"])
    target = target_for_project(project)
    assert list(target.stored_vector) == pytest.approx([0.1, 0.2, 0.3])

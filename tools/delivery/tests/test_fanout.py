"""Cross-member relevance fan-out + in-app suggestions (Feature F).

Deterministic 3-D vectors on member profiles + the shared item; cosine is scored
directly against the floor (never an RRF rank). Checks the brief's assertions: the
sharer is never suggested to themselves, below-floor members get audited abstentions
(not notifications), and re-sharing never double-notifies.
"""

import pytest
from apps.accounts.models import Lab, LabMembership, Profile
from apps.research.models import Project, ProjectMember
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from tools.delivery.fanout import fan_out_relevance
from tools.delivery.models import MemberSuggestion, ProjectShare
from tools.retrieval.models import ContentItem


@pytest.fixture
def client() -> APIClient:
    return APIClient()


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


def _paper(embedding, title="A paper") -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=title,
        metadata={"title": title},
        embedding=embedding,
    )


def _share(project, item, sharer) -> ProjectShare:
    return ProjectShare.objects.create(project=project, content=item, shared_by=sharer)


@pytest.mark.django_db
def test_suggests_above_floor_and_abstains_below(project, lab):
    sharer = _member("sharer", lab, embedding=[1.0, 0.0, 0.0])
    keen = _member("keen", lab, embedding=[1.0, 0.0, 0.0])  # cosine 1.0 with item
    meh = _member("meh", lab, embedding=[0.0, 1.0, 0.0])  # cosine 0.0
    for user in (sharer, keen, meh):
        ProjectMember.objects.create(project=project, user=user)
    item = _paper([1.0, 0.0, 0.0])

    result = fan_out_relevance(_share(project, item, sharer), embed_missing=False)
    assert result["scored"] == 2  # keen + meh, never the sharer

    keen_row = MemberSuggestion.objects.get(user=keen, content=item)
    assert keen_row.suggested is True
    assert keen_row.delivered_via == "in_app"
    meh_row = MemberSuggestion.objects.get(user=meh, content=item)
    assert meh_row.suggested is False  # persisted abstention, not delivered
    assert not MemberSuggestion.objects.filter(user=sharer).exists()


@pytest.mark.django_db
def test_below_every_floor_zero_suggested_but_n_audit_rows(project, lab):
    sharer = _member("sharer", lab, embedding=[0.0, 0.0, 1.0])
    a = _member("a", lab, embedding=[0.0, 1.0, 0.0])
    b = _member("b", lab, embedding=[0.0, 1.0, 0.0])
    for user in (sharer, a, b):
        ProjectMember.objects.create(project=project, user=user)
    item = _paper([1.0, 0.0, 0.0])

    result = fan_out_relevance(_share(project, item, sharer), embed_missing=False)
    assert result["suggested"] == 0
    assert MemberSuggestion.objects.filter(content=item, suggested=True).count() == 0
    assert MemberSuggestion.objects.filter(content=item, suggested=False).count() == 2


@pytest.mark.django_db
def test_reshare_does_not_double_notify(project, lab):
    sharer = _member("sharer", lab, embedding=[1.0, 0.0, 0.0])
    keen = _member("keen", lab, embedding=[1.0, 0.0, 0.0])
    for user in (sharer, keen):
        ProjectMember.objects.create(project=project, user=user)
    item = _paper([1.0, 0.0, 0.0])

    fan_out_relevance(_share(project, item, sharer), embed_missing=False)
    fan_out_relevance(_share(project, item, sharer), embed_missing=False)  # re-share
    assert MemberSuggestion.objects.filter(user=keen, content=item).count() == 1


@pytest.mark.django_db
def test_no_embedding_aborts(project, lab):
    sharer = _member("sharer", lab, embedding=[1.0, 0.0, 0.0])
    keen = _member("keen", lab, embedding=[1.0, 0.0, 0.0])
    for user in (sharer, keen):
        ProjectMember.objects.create(project=project, user=user)
    item = _paper(None)  # no abstract → no embedding → nothing to score

    result = fan_out_relevance(_share(project, item, sharer), embed_missing=False)
    assert result["reason"] == "no_embedding"
    assert MemberSuggestion.objects.count() == 0


@pytest.mark.django_db
def test_suggestions_endpoint_lists_and_dismisses(client, project, lab):
    sharer = _member("sharer", lab, embedding=[1.0, 0.0, 0.0])
    keen = _member("keen", lab, embedding=[1.0, 0.0, 0.0])
    for user in (sharer, keen):
        ProjectMember.objects.create(project=project, user=user)
    item = _paper([1.0, 0.0, 0.0])
    fan_out_relevance(_share(project, item, sharer), embed_missing=False)

    client.force_authenticate(keen)
    listing = client.get("/api/suggestions/")
    assert listing.status_code == 200
    assert listing.data["count"] == 1
    suggestion = listing.data["items"][0]
    assert suggestion["content_id"] == str(item.id)
    assert suggestion["shared_by"]["username"] == "sharer"

    dismissed = client.post(f"/api/suggestions/{suggestion['id']}/dismiss/")
    assert dismissed.status_code == 200
    assert client.get("/api/suggestions/").data["count"] == 0  # gone after dismissal
    assert MemberSuggestion.objects.get(id=suggestion["id"]).dismissed is True

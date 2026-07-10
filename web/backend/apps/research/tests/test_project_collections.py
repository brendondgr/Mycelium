"""Shared collections / reading lists (Feature C)."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, Lab, LabMembership
from apps.content.models import CollectionItem, ContentItem
from apps.research.models import Project, ProjectMember


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="Reyes Lab", slug="reyes-lab")


@pytest.fixture
def member(db, lab: Lab) -> User:
    user = User.objects.create_user(username="jordan", password="p")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    return user


@pytest.fixture
def project(db, lab: Lab, member: User) -> Project:
    project = Project.objects.create(name="Reef Mapping", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=member)
    return project


def _paper(title: str = "A paper") -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=title,
        metadata={"title": title, "abstract": title},
    )


def _make_collection(client, project, name="Aim 2 review", **extra):
    return client.post(
        f"/api/projects/{project.id}/collections/", {"name": name, **extra}
    )


@pytest.mark.django_db
def test_create_list_and_add_items(client, project, member):
    client.force_authenticate(member)
    created = _make_collection(client, project, description="for the review")
    assert created.status_code == 201
    cid = created.data["id"]
    assert created.data["name"] == "Aim 2 review"

    listing = client.get(f"/api/projects/{project.id}/collections/")
    assert listing.status_code == 200
    assert listing.data["count"] == 1

    paper = _paper()
    added = client.post(
        f"/api/projects/{project.id}/collections/{cid}/items/",
        {"content_item": str(paper.id), "note": "key method"},
    )
    assert added.status_code == 201
    assert added.data["item_count"] == 1
    assert added.data["items"][0]["note"] == "key method"


@pytest.mark.django_db
def test_duplicate_add_is_a_noop_200_not_500(client, project, member):
    client.force_authenticate(member)
    cid = _make_collection(client, project, name="L").data["id"]
    paper = _paper()
    first = client.post(
        f"/api/projects/{project.id}/collections/{cid}/items/",
        {"content_item": str(paper.id)},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/projects/{project.id}/collections/{cid}/items/",
        {"content_item": str(paper.id)},
    )
    assert second.status_code == 200  # no-op, not a constraint 500
    assert CollectionItem.objects.filter(collection_id=cid, content=paper).count() == 1


@pytest.mark.django_db
def test_archive_hides_from_default_list_but_preserves_items(client, project, member):
    client.force_authenticate(member)
    cid = _make_collection(client, project, name="L").data["id"]
    paper = _paper()
    client.post(
        f"/api/projects/{project.id}/collections/{cid}/items/",
        {"content_item": str(paper.id)},
    )
    archived = client.patch(
        f"/api/projects/{project.id}/collections/{cid}/", {"is_archived": True}
    )
    assert archived.status_code == 200
    assert archived.data["is_archived"] is True

    assert client.get(f"/api/projects/{project.id}/collections/").data["count"] == 0
    with_archived = client.get(
        f"/api/projects/{project.id}/collections/?archived=1"
    )
    assert with_archived.data["count"] == 1
    detail = client.get(f"/api/projects/{project.id}/collections/{cid}/")
    assert len(detail.data["items"]) == 1  # items preserved for audit


@pytest.mark.django_db
def test_rename_and_remove_item(client, project, member):
    client.force_authenticate(member)
    cid = _make_collection(client, project, name="Old").data["id"]
    renamed = client.patch(
        f"/api/projects/{project.id}/collections/{cid}/", {"name": "New"}
    )
    assert renamed.data["name"] == "New"

    paper = _paper()
    client.post(
        f"/api/projects/{project.id}/collections/{cid}/items/",
        {"content_item": str(paper.id)},
    )
    removed = client.delete(
        f"/api/projects/{project.id}/collections/{cid}/items/{paper.id}/"
    )
    assert removed.status_code == 204
    assert CollectionItem.objects.filter(collection_id=cid).count() == 0


@pytest.mark.django_db
def test_non_visible_outsider_blocked(client, project):
    outsider = User.objects.create_user(username="nope", password="p")
    client.force_authenticate(outsider)
    assert (
        client.get(f"/api/projects/{project.id}/collections/").status_code == 403
    )
    assert (
        _make_collection(client, project, name="X").status_code == 403
    )


@pytest.mark.django_db
def test_visible_non_participant_can_read_but_not_write(client, lab, project):
    """A dept head can *see* a lab project but must join to change its collections."""
    dept_owner = User.objects.create_user(username="chair", password="p")
    dept = Department.objects.create(owner=dept_owner, name="Marine Bio")
    lab.department = dept
    lab.save(update_fields=["department"])

    client.force_authenticate(dept_owner)
    # Visible (department head) → may read the collections list.
    assert client.get(f"/api/projects/{project.id}/collections/").status_code == 200
    # But not a participant → may not create one.
    assert _make_collection(client, project, name="X").status_code == 403

"""Lab project browsing + self-join / leave / manager-add endpoints."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project, ProjectMember


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="Reyes Lab", slug="reyes-lab")


@pytest.fixture
def pi(db, lab: Lab) -> User:
    user = User.objects.create_user(username="lena", password="p")
    LabMembership.objects.create(
        user=user, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    return user


@pytest.fixture
def member(db, lab: Lab) -> User:
    user = User.objects.create_user(username="jordan", password="p")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    return user


@pytest.fixture
def project(db, lab: Lab) -> Project:
    return Project.objects.create(name="Reef Mapping", scope_lab=lab)


@pytest.mark.django_db
def test_member_browses_all_lab_projects(
    client: APIClient, lab: Lab, member: User, project: Project
) -> None:
    # A second project the member is NOT part of is still listed for browsing.
    Project.objects.create(name="Second", scope_lab=lab)
    client.force_authenticate(member)
    resp = client.get(f"/api/projects/lab/{lab.slug}/")
    assert resp.status_code == 200
    names = {row["name"] for row in resp.data}
    assert names == {"Reef Mapping", "Second"}
    assert all(row["is_member"] is False for row in resp.data)


@pytest.mark.django_db
def test_non_member_cannot_browse_lab_projects(
    client: APIClient, lab: Lab, project: Project
) -> None:
    outsider = User.objects.create_user(username="nope", password="p")
    client.force_authenticate(outsider)
    assert client.get(f"/api/projects/lab/{lab.slug}/").status_code == 403


@pytest.mark.django_db
def test_member_self_joins_and_leaves(
    client: APIClient, member: User, project: Project
) -> None:
    client.force_authenticate(member)
    join = client.post(f"/api/projects/{project.id}/join/")
    assert join.status_code == 200
    assert join.data["is_member"] is True
    assert ProjectMember.objects.filter(project=project, user=member).exists()
    # Now it shows up in their personal visible list.
    assert any(
        row["id"] == str(project.id) for row in client.get("/api/projects/").data
    )
    leave = client.post(f"/api/projects/{project.id}/leave/")
    assert leave.status_code == 200
    assert not ProjectMember.objects.filter(project=project, user=member).exists()


@pytest.mark.django_db
def test_outsider_cannot_join(client: APIClient, project: Project) -> None:
    outsider = User.objects.create_user(username="nope", password="p")
    client.force_authenticate(outsider)
    assert client.post(f"/api/projects/{project.id}/join/").status_code == 403


@pytest.mark.django_db
def test_cannot_join_personal_project(client: APIClient) -> None:
    owner = User.objects.create_user(username="solo", password="p")
    personal = Project.objects.create(name="Mine", scope_user=owner)
    other = User.objects.create_user(username="other", password="p")
    client.force_authenticate(other)
    assert client.post(f"/api/projects/{personal.id}/join/").status_code in (403, 404)


@pytest.mark.django_db
def test_manager_adds_a_lab_member(
    client: APIClient, pi: User, member: User, project: Project
) -> None:
    client.force_authenticate(pi)
    resp = client.post(
        f"/api/projects/{project.id}/members/", {"username": member.username}
    )
    assert resp.status_code == 201
    assert ProjectMember.objects.filter(project=project, user=member).exists()


@pytest.mark.django_db
def test_plain_member_cannot_add_others(
    client: APIClient, member: User, project: Project
) -> None:
    client.force_authenticate(member)
    resp = client.post(
        f"/api/projects/{project.id}/members/", {"username": "someone"}
    )
    assert resp.status_code == 403

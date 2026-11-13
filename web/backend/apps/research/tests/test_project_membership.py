"""Lab project listing (narrowed), no self-join, leave and manager-add."""

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
def test_member_sees_only_their_own_lab_projects(
    client: APIClient, lab: Lab, member: User, project: Project
) -> None:
    """Belonging to the lab no longer exposes its projects (plan Phase 0)."""
    mine = Project.objects.create(name="Mine", scope_lab=lab)
    ProjectMember.objects.create(project=mine, user=member)
    client.force_authenticate(member)
    resp = client.get(f"/api/projects/lab/{lab.slug}/")
    assert resp.status_code == 200
    assert [row["name"] for row in resp.data] == ["Mine"]
    assert resp.data[0]["is_member"] is True


@pytest.mark.django_db
def test_lab_head_sees_every_lab_project(
    client: APIClient, lab: Lab, pi: User, project: Project
) -> None:
    Project.objects.create(name="Second", scope_lab=lab)
    client.force_authenticate(pi)
    resp = client.get(f"/api/projects/lab/{lab.slug}/")
    assert resp.status_code == 200
    assert {row["name"] for row in resp.data} == {"Reef Mapping", "Second"}


@pytest.mark.django_db
def test_lab_endpoint_never_returns_another_labs_projects(
    client: APIClient, lab: Lab, pi: User, project: Project
) -> None:
    other = Lab.objects.create(name="Other", slug="other")
    elsewhere = Project.objects.create(name="Elsewhere", scope_lab=other)
    ProjectMember.objects.create(project=elsewhere, user=pi)
    client.force_authenticate(pi)
    names = {row["name"] for row in client.get(f"/api/projects/lab/{lab.slug}/").data}
    assert "Elsewhere" not in names


@pytest.mark.django_db
def test_non_member_cannot_browse_lab_projects(
    client: APIClient, lab: Lab, project: Project
) -> None:
    outsider = User.objects.create_user(username="nope", password="p")
    client.force_authenticate(outsider)
    assert client.get(f"/api/projects/lab/{lab.slug}/").status_code == 403


@pytest.mark.django_db
def test_self_join_route_is_gone(
    client: APIClient, member: User, project: Project
) -> None:
    """A project is joined by invitation; there is no self-join by id."""
    client.force_authenticate(member)
    for path in (
        f"/api/projects/{project.id}/join/",
        f"/api/projects/{project.id}/join",
    ):
        assert client.post(path).status_code == 404
    assert not ProjectMember.objects.filter(project=project, user=member).exists()


@pytest.mark.django_db
def test_member_cannot_open_an_unjoined_lab_project_by_id(
    client: APIClient, member: User, project: Project
) -> None:
    client.force_authenticate(member)
    assert client.get(f"/api/projects/{project.id}/").status_code == 404


@pytest.mark.django_db
def test_member_leaves_a_project(
    client: APIClient, member: User, project: Project
) -> None:
    ProjectMember.objects.create(project=project, user=member)
    client.force_authenticate(member)
    leave = client.post(f"/api/projects/{project.id}/leave/")
    assert leave.status_code == 200
    assert not ProjectMember.objects.filter(project=project, user=member).exists()


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
    assert resp.status_code == 404


@pytest.mark.django_db
def test_leave_does_not_reveal_a_project_the_caller_cannot_see(
    client: APIClient, project: Project
) -> None:
    """'Leaving' a project you were never on must not return its row."""
    outsider = User.objects.create_user(username="outsider", password="p")
    client.force_authenticate(outsider)
    for path in (
        f"/api/projects/{project.id}/leave/",
        f"/api/projects/{project.id}/leave",
    ):
        resp = client.post(path)
        assert resp.status_code == 404
        assert "goals" not in (resp.data or {})

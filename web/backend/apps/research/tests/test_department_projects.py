"""Department projects are managed by the department's owner and admins.

A department owner or admin can create a department project, and until now
nobody could then edit, archive or invite to it, because the project edit rule
only knew personal and lab projects (plan Phase 0).
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, DeptMembership
from apps.research.models import Project, ProjectInvitation
from apps.research.permissions import user_can_edit_project


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def head(db) -> User:
    return User.objects.create_user(username="head", password="p")


@pytest.fixture
def department(head: User) -> Department:
    return Department.objects.create(owner=head, name="Neuroscience")


@pytest.fixture
def admin(department: Department) -> User:
    user = User.objects.create_user(username="dept-admin", password="p")
    DeptMembership.objects.create(
        user=user, department=department, role=DeptMembership.Role.ADMIN
    )
    return user


@pytest.fixture
def plain(department: Department) -> User:
    user = User.objects.create_user(username="dept-member", password="p")
    DeptMembership.objects.create(
        user=user, department=department, role=DeptMembership.Role.MEMBER
    )
    return user


@pytest.fixture
def project(department: Department) -> Project:
    return Project.objects.create(name="Dept review", scope_department=department)


@pytest.mark.django_db
def test_department_owner_and_admin_may_edit(
    head: User, admin: User, plain: User, project: Project
) -> None:
    assert user_can_edit_project(head, project)
    assert user_can_edit_project(admin, project)
    assert not user_can_edit_project(plain, project)


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["head", "admin"])
def test_department_manager_renames_and_sees_edit_flags(
    client: APIClient, request, who: str, project: Project
) -> None:
    client.force_authenticate(request.getfixturevalue(who))
    resp = client.patch(
        f"/api/projects/{project.id}/", {"name": "Renamed"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["can_edit"] is True
    assert resp.data["can_manage_members"] is True
    project.refresh_from_db()
    assert project.name == "Renamed"


@pytest.mark.django_db
def test_department_manager_archives(
    client: APIClient, head: User, project: Project
) -> None:
    client.force_authenticate(head)
    assert client.post(f"/api/projects/{project.id}/archive/").status_code == 200
    project.refresh_from_db()
    assert project.is_archived


@pytest.mark.django_db
def test_department_manager_invites(
    client: APIClient, admin: User, project: Project
) -> None:
    invitee = User.objects.create_user(username="guest", password="p")
    client.force_authenticate(admin)
    resp = client.post(
        f"/api/projects/{project.id}/invitations/", {"identifier": "guest"}
    )
    assert resp.status_code == 201, resp.data
    assert ProjectInvitation.objects.filter(project=project, invitee=invitee).exists()


@pytest.mark.django_db
def test_plain_department_member_cannot_edit(
    client: APIClient, plain: User, project: Project
) -> None:
    client.force_authenticate(plain)
    # A rank-and-file member does not even see the department's projects.
    resp = client.patch(f"/api/projects/{project.id}/", {"name": "X"}, format="json")
    assert resp.status_code == 404
    assert client.post(f"/api/projects/{project.id}/archive/").status_code == 404
    assert (
        client.post(
            f"/api/projects/{project.id}/invitations/", {"identifier": "head"}
        ).status_code
        == 404
    )

"""Authority in a department runs strictly downward, as it does in a lab.

Before ``DEPT_ROLE_RANK``, ``DeptMembersView.post`` accepted any role from any
manager, so a department admin could create owners and admins — themselves
included — and could remove another admin. These pin the department twin of
the lab rule: only the head creates admins, nobody creates an owner except by
transfer, and authority over a person needs a rank above theirs.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import AuditEvent, DeptMembership, OrgInvite
from apps.accounts.permissions import (
    dept_role_rank,
    user_can_grant_dept_role,
    user_can_manage_department,
)
from apps.billing.services import create_department_workspace

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


def _dept_with(head: User, **roles: str):
    """A department run by ``head``, plus one direct member per ``name=role``."""
    department = create_department_workspace(head, "Earth Sciences").department
    for name, role in roles.items():
        DeptMembership.objects.create(
            department=department, user=_user(name), role=role
        )
    return department


def _add(client: APIClient, department, username: str, role: str):
    return client.post(
        f"/api/auth/departments/{department.id}/members/",
        {"username": username, "role": role},
        format="json",
    )


def _set_role(client: APIClient, department, username: str, role: str):
    return client.patch(
        f"/api/auth/departments/{department.id}/members/{username}/",
        {"role": role},
        format="json",
    )


def _remove(client: APIClient, department, username: str):
    return client.delete(f"/api/auth/departments/{department.id}/members/{username}/")


# -- Adding a member is granting a role ---------------------------------------


@pytest.mark.django_db
def test_an_admin_cannot_add_an_owner(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    newcomer = _user("newcomer")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _add(client, department, "newcomer", "owner").status_code == 403
    assert not DeptMembership.objects.filter(user=newcomer).exists()


@pytest.mark.django_db
def test_an_admin_cannot_add_another_admin(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    newcomer = _user("newcomer")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _add(client, department, "newcomer", "admin").status_code == 403
    assert not DeptMembership.objects.filter(user=newcomer).exists()


@pytest.mark.django_db
def test_an_admin_may_add_members_and_viewers(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    _user("reader")
    _user("researcher")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _add(client, department, "researcher", "member").status_code == 201
    assert _add(client, department, "reader", "viewer").status_code == 201
    roles = dict(
        DeptMembership.objects.filter(department=department).values_list(
            "user__username", "role"
        )
    )
    assert roles["researcher"] == "member"
    assert roles["reader"] == "viewer"


@pytest.mark.django_db
def test_the_head_may_add_an_admin_but_not_an_owner(client: APIClient) -> None:
    head = _user("head")
    department = _dept_with(head)
    _user("deputy")
    _user("rival")
    client.force_authenticate(head)

    assert _add(client, department, "deputy", "admin").status_code == 201
    assert _add(client, department, "rival", "owner").status_code == 403


@pytest.mark.django_db
def test_an_unknown_role_is_a_field_error(client: APIClient) -> None:
    head = _user("head")
    department = _dept_with(head)
    _user("someone")
    client.force_authenticate(head)

    response = _add(client, department, "someone", "emperor")
    assert response.status_code == 400
    assert "role" in response.data


@pytest.mark.django_db
def test_a_refused_add_is_audited(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    _user("newcomer")
    client.force_authenticate(User.objects.get(username="deputy"))

    _add(client, department, "newcomer", "admin")
    assert AuditEvent.objects.filter(action="dept.member.role.refused").exists()


# -- Role edits ----------------------------------------------------------------


@pytest.mark.django_db
def test_the_head_may_promote_a_member_to_admin(client: APIClient) -> None:
    head = _user("head")
    department = _dept_with(head, researcher="member")
    client.force_authenticate(head)

    assert _set_role(client, department, "researcher", "admin").status_code == 200
    assert (
        DeptMembership.objects.get(user__username="researcher").role
        == DeptMembership.Role.ADMIN
    )


@pytest.mark.django_db
def test_an_admin_may_not_promote_themselves(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _set_role(client, department, "deputy", "owner").status_code == 403
    assert DeptMembership.objects.get(user__username="deputy").role == "admin"


@pytest.mark.django_db
def test_an_admin_may_not_re_role_another_admin(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin", other="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _set_role(client, department, "other", "viewer").status_code == 403


@pytest.mark.django_db
def test_an_admin_may_set_the_roles_below_them(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin", researcher="member")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _set_role(client, department, "researcher", "viewer").status_code == 200


@pytest.mark.django_db
def test_nobody_mints_a_second_owner_by_role_edit(client: APIClient) -> None:
    head = _user("head")
    department = _dept_with(head, deputy="admin")
    client.force_authenticate(head)

    assert _set_role(client, department, "deputy", "owner").status_code == 403


@pytest.mark.django_db
def test_the_no_slash_role_route_works(client: APIClient) -> None:
    head = _user("head")
    department = _dept_with(head, researcher="member")
    client.force_authenticate(head)

    response = client.patch(
        f"/api/auth/departments/{department.id}/members/researcher",
        {"role": "viewer"},
        format="json",
    )
    assert response.status_code == 200


# -- Removal -------------------------------------------------------------------


@pytest.mark.django_db
def test_an_admin_may_remove_a_member(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin", researcher="member")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _remove(client, department, "researcher").status_code == 204


@pytest.mark.django_db
def test_an_admin_may_not_remove_another_admin(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin", other="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _remove(client, department, "other").status_code == 403
    assert DeptMembership.objects.filter(user__username="other").exists()
    assert AuditEvent.objects.filter(action="dept.member.remove.refused").exists()


@pytest.mark.django_db
def test_the_head_cannot_be_removed(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _remove(client, department, "head").status_code == 409


@pytest.mark.django_db
def test_an_admin_may_leave(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _remove(client, department, "deputy").status_code == 204


# -- Invitations grant their role too -----------------------------------------


@pytest.mark.django_db
def test_an_admin_cannot_invite_an_admin(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    response = client.post(
        f"/api/auth/departments/{department.id}/invites/",
        {"kind": "link", "role": "admin"},
        format="json",
    )
    assert response.status_code == 403
    assert not OrgInvite.objects.filter(department=department).exists()
    assert AuditEvent.objects.filter(
        action="dept.member.role.refused", target_id=str(department.id)
    ).exists()


@pytest.mark.django_db
def test_an_admin_may_invite_members(client: APIClient) -> None:
    department = _dept_with(_user("head"), deputy="admin")
    client.force_authenticate(User.objects.get(username="deputy"))

    response = client.post(
        f"/api/auth/departments/{department.id}/invites/",
        {"kind": "link", "role": "member"},
        format="json",
    )
    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_the_head_may_invite_an_admin(client: APIClient) -> None:
    head = _user("head")
    department = _dept_with(head)
    client.force_authenticate(head)

    response = client.post(
        f"/api/auth/departments/{department.id}/invites/",
        {"kind": "link", "role": "admin"},
        format="json",
    )
    assert response.status_code == 201, response.data


# -- The rank itself -----------------------------------------------------------


@pytest.mark.django_db
def test_a_stray_owner_row_ranks_as_an_admin_not_a_second_head() -> None:
    head = _user("head")
    department = _dept_with(head, stray="owner")
    stray = User.objects.get(username="stray")

    assert dept_role_rank(head, department) == 3
    assert dept_role_rank(stray, department) == 2
    assert not user_can_grant_dept_role(stray, department, "admin")
    assert user_can_manage_department(stray, department)


@pytest.mark.django_db
def test_a_head_without_a_membership_row_still_ranks_as_head() -> None:
    """Older departments, and fixtures, have only ``Department.owner``."""
    from apps.accounts.models import Department

    head = _user("head")
    department = Department.objects.create(owner=head, name="Legacy")

    assert dept_role_rank(head, department) == 3
    assert user_can_grant_dept_role(head, department, "admin")

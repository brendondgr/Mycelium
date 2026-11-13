"""Handing a department to a new head (account and lab management, item 5b).

The head is ``Department.owner``, a foreign key, with an OWNER membership row
kept in step. Transfer moves both at once, leaves the outgoing head an admin
rather than a stranger, and cannot be undone from the outgoing side.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import AuditEvent, Department, DeptMembership
from apps.billing.services import create_department_workspace

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


def _dept_with(head: User, **roles: str) -> Department:
    department = create_department_workspace(head, "Earth Sciences").department
    for name, role in roles.items():
        DeptMembership.objects.create(
            department=department, user=_user(name), role=role
        )
    return department


def _transfer(client: APIClient, department, username: str, *, slash: bool = True):
    tail = "/" if slash else ""
    return client.post(
        f"/api/auth/departments/{department.id}/transfer-ownership{tail}",
        {"username": username},
        format="json",
    )


@pytest.mark.django_db
def test_transfer_moves_the_head_and_both_rows(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder, chair="member")
    chair = User.objects.get(username="chair")
    client.force_authenticate(founder)

    assert _transfer(client, department, "chair").status_code == 200

    department.refresh_from_db()
    assert department.owner_id == chair.id
    assert DeptMembership.objects.get(department=department, user=chair).role == "owner"
    assert (
        DeptMembership.objects.get(department=department, user=founder).role
        == "admin"
    )


@pytest.mark.django_db
def test_the_department_keeps_exactly_one_owner_row(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder, chair="member", stray="owner")
    client.force_authenticate(founder)

    assert _transfer(client, department, "chair").status_code == 200
    owners = DeptMembership.objects.filter(department=department, role="owner")
    assert list(owners.values_list("user__username", flat=True)) == ["chair"]


@pytest.mark.django_db
def test_a_head_without_a_row_gets_one_as_admin(client: APIClient) -> None:
    founder = _user("founder")
    department = Department.objects.create(owner=founder, name="Legacy")
    DeptMembership.objects.create(
        department=department, user=_user("chair"), role="member"
    )
    client.force_authenticate(founder)

    assert _transfer(client, department, "chair").status_code == 200
    assert (
        DeptMembership.objects.get(department=department, user=founder).role
        == "admin"
    )


@pytest.mark.django_db
def test_the_transfer_cannot_be_undone_from_the_old_heads_side(client) -> None:
    founder = _user("founder")
    department = _dept_with(founder, chair="member")
    client.force_authenticate(founder)
    _transfer(client, department, "chair")

    assert _transfer(client, department, "founder").status_code == 403
    response = client.patch(
        f"/api/auth/departments/{department.id}/members/founder/",
        {"role": "owner"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_only_the_new_head_can_hand_it_back(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder, chair="member")
    client.force_authenticate(founder)
    _transfer(client, department, "chair")

    client.force_authenticate(User.objects.get(username="chair"))
    assert _transfer(client, department, "founder").status_code == 200
    department.refresh_from_db()
    assert department.owner_id == founder.id


@pytest.mark.django_db
def test_an_admin_may_not_transfer_the_department(client: APIClient) -> None:
    department = _dept_with(_user("founder"), deputy="admin", chair="member")
    client.force_authenticate(User.objects.get(username="deputy"))

    assert _transfer(client, department, "chair").status_code == 403


@pytest.mark.django_db
def test_a_stranger_may_not_transfer_the_department(client: APIClient) -> None:
    department = _dept_with(_user("founder"), chair="member")
    client.force_authenticate(_user("stranger"))

    assert _transfer(client, department, "chair").status_code == 403


@pytest.mark.django_db
def test_the_target_must_be_a_direct_member(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder)
    _user("outsider")
    client.force_authenticate(founder)

    response = _transfer(client, department, "outsider")
    assert response.status_code == 400
    assert "username" in response.data


@pytest.mark.django_db
def test_the_target_must_have_verified_their_email(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder)
    unverified = User.objects.create_user(username="unverified", password="p")
    DeptMembership.objects.create(department=department, user=unverified)
    client.force_authenticate(founder)

    response = _transfer(client, department, "unverified")

    assert response.status_code == 400
    assert "verify their email" in str(response.data)
    department.refresh_from_db()
    assert department.owner_id == founder.id


@pytest.mark.django_db
def test_transferring_to_yourself_is_refused(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder)
    client.force_authenticate(founder)

    assert _transfer(client, department, "founder").status_code == 400


@pytest.mark.django_db
def test_a_missing_username_is_a_plain_field_error(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder)
    client.force_authenticate(founder)

    response = _transfer(client, department, "")
    assert response.status_code == 400
    assert "username" in response.data


@pytest.mark.django_db
def test_the_transfer_is_audited_with_both_parties(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder, chair="member")
    chair = User.objects.get(username="chair")
    client.force_authenticate(founder)
    _transfer(client, department, "chair")

    event = AuditEvent.objects.get(action="department.ownership.transfer")
    assert event.metadata["from_user_id"] == founder.id
    assert event.metadata["to_user_id"] == chair.id


@pytest.mark.django_db
def test_the_no_slash_route_works_too(client: APIClient) -> None:
    founder = _user("founder")
    department = _dept_with(founder, chair="member")
    client.force_authenticate(founder)

    assert _transfer(client, department, "chair", slash=False).status_code == 200


@pytest.mark.django_db
def test_the_new_head_reads_as_owner_in_the_department_list(client) -> None:
    founder = _user("founder")
    department = _dept_with(founder, chair="member")
    client.force_authenticate(founder)
    _transfer(client, department, "chair")

    client.force_authenticate(User.objects.get(username="chair"))
    rows = client.get("/api/auth/departments/").data
    row = next(r for r in rows if r["id"] == str(department.id))
    assert row["is_owner"] is True
    assert row["role"] == "owner"

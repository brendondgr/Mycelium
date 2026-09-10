"""Creating a department after the account exists (`/api/auth/departments/`).

Sign-up no longer offers a department account, so this endpoint is the only way
one comes into being — and, like creating a lab, it is behind the activation gate.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import Department, DeptMembership, DeptProfile
from apps.billing.models import Seat, Subscription, Tier

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_create_department_requires_authentication(client: APIClient) -> None:
    response = client.post("/api/auth/departments/", {"name": "Biology"})
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_create_department_requires_a_verified_account(client: APIClient) -> None:
    client.force_authenticate(User.objects.create_user(username="u", password="p"))

    response = client.post(
        "/api/auth/departments/", {"name": "Biology"}, format="json"
    )

    assert response.status_code == 403
    assert Department.objects.count() == 0


@pytest.mark.django_db
def test_create_department_makes_caller_owner(client: APIClient) -> None:
    user = verified(User.objects.create_user(username="head", password="p"))
    client.force_authenticate(user)

    response = client.post(
        "/api/auth/departments/",
        {"name": "Molecular Systems", "institution": "Northgate University"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "Molecular Systems"
    assert response.data["is_owner"] is True
    assert response.data["can_manage"] is True

    dept = Department.objects.get(owner=user)
    assert dept.institution == "Northgate University"
    assert DeptMembership.objects.filter(
        department=dept, user=user, role=DeptMembership.Role.OWNER
    ).exists()
    # Provisioned like a signup department was: interest profile, inactive plan,
    # pending founder seat.
    assert DeptProfile.objects.filter(department=dept).exists()
    sub = Subscription.objects.get(scope_department=dept)
    assert sub.tier == Tier.CANOPY
    assert sub.status == Subscription.Status.INACTIVE
    seat = Seat.objects.get(subscription=sub, member=user)
    assert seat.status == Seat.Status.PENDING


@pytest.mark.django_db
def test_create_department_rejects_a_blank_name(client: APIClient) -> None:
    client.force_authenticate(
        verified(User.objects.create_user(username="head", password="p"))
    )

    response = client.post("/api/auth/departments/", {"name": "  "}, format="json")

    assert response.status_code == 400
    assert "name" in response.data


@pytest.mark.django_db
def test_listing_shows_owned_and_joined_but_not_others(client: APIClient) -> None:
    head = verified(User.objects.create_user(username="head", password="p"))
    member = User.objects.create_user(username="member", password="p")
    stranger = User.objects.create_user(username="stranger", password="p")

    client.force_authenticate(head)
    dept_id = client.post(
        "/api/auth/departments/", {"name": "Biology"}, format="json"
    ).data["id"]
    DeptMembership.objects.create(
        department=Department.objects.get(id=dept_id),
        user=member,
        role=DeptMembership.Role.MEMBER,
    )

    client.force_authenticate(member)
    rows = client.get("/api/auth/departments/").data
    assert [row["id"] for row in rows] == [dept_id]
    assert rows[0]["is_owner"] is False
    assert rows[0]["can_manage"] is False

    client.force_authenticate(stranger)
    assert client.get("/api/auth/departments/").data == []

"""Lab & department member / lab management endpoints (Phase A)."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import DeptMembership, Lab, LabMembership
from apps.billing.entitlements import Tier, effective_tier
from apps.billing.models import Seat
from apps.billing.services import (
    activate_department_subscription,
    activate_lab_subscription,
    create_lab_workspace,
    provision_workspace,
)

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str) -> User:
    return verified(User.objects.create_user(username=name, password="p"))


# -- Lab member management -----------------------------------------------------


@pytest.mark.django_db
def test_manager_adds_lab_member_and_seats_them(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    activate_lab_subscription(lab)
    newbie = _user("student")
    client.force_authenticate(founder)

    resp = client.post(
        f"/api/auth/labs/{lab.slug}/members/",
        {"username": "student", "role": "member"},
        format="json",
    )

    assert resp.status_code == 201
    assert LabMembership.objects.filter(lab=lab, user=newbie).exists()
    assert effective_tier(newbie) == Tier.LAB


@pytest.mark.django_db
def test_non_manager_cannot_add_lab_member(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    activate_lab_subscription(lab)
    member = _user("member")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    _user("outsider_target")
    client.force_authenticate(member)  # a plain member, not a manager

    resp = client.post(
        f"/api/auth/labs/{lab.slug}/members/",
        {"username": "outsider_target"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_remove_lab_member_defers_seat(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    activate_lab_subscription(lab)
    member = _user("student")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    activate_lab_subscription(lab)  # seat the new member
    client.force_authenticate(founder)

    resp = client.delete(f"/api/auth/labs/{lab.slug}/members/student/")

    assert resp.status_code == 204
    assert not LabMembership.objects.filter(lab=lab, user=member).exists()
    seat = Seat.objects.get(member=member)
    assert seat.status == Seat.Status.ACTIVE  # deferred, keeps access until period end
    assert seat.ends_at is not None


@pytest.mark.django_db
def test_cannot_remove_last_owner(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    activate_lab_subscription(lab)
    client.force_authenticate(founder)

    resp = client.delete(f"/api/auth/labs/{lab.slug}/members/pi/")
    assert resp.status_code == 409


@pytest.mark.django_db
def test_change_lab_member_role(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    member = _user("student")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(founder)

    resp = client.patch(
        f"/api/auth/labs/{lab.slug}/members/student/",
        {"role": "admin"},
        format="json",
    )

    assert resp.status_code == 200
    assert LabMembership.objects.get(lab=lab, user=member).role == "admin"


# -- Department member & lab management ----------------------------------------


@pytest.mark.django_db
def test_department_add_member_and_effective_roster(client: APIClient) -> None:
    head = _user("head")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)
    direct = _user("analyst")
    client.force_authenticate(head)

    add = client.post(
        f"/api/auth/departments/{dept.id}/members/",
        {"username": "analyst", "role": "member"},
        format="json",
    )
    assert add.status_code == 201
    assert DeptMembership.objects.filter(department=dept, user=direct).exists()
    assert effective_tier(direct) == Tier.CANOPY

    roster = client.get(f"/api/auth/departments/{dept.id}/members/")
    usernames = {row["username"] for row in roster.data}
    assert {"head", "analyst"} <= usernames


@pytest.mark.django_db
def test_department_attach_lab_lists_and_reseats(client: APIClient) -> None:
    head = _user("head")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)
    pi = _user("pi")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    client.force_authenticate(head)

    resp = client.post(
        f"/api/auth/departments/{dept.id}/labs/",
        {"slug": lab.slug},
        format="json",
    )

    assert resp.status_code == 201
    lab.refresh_from_db()
    assert lab.department_id == dept.id
    # Attach alone does not put the lab on the plan (opt-in).
    assert effective_tier(pi) != Tier.CANOPY
    slugs = {row["slug"] for row in resp.data}
    assert lab.slug in slugs
    assert all(row["included_in_plan"] is False for row in resp.data)

    # The head includes the lab in the plan → its PI is seated department-paid.
    inc = client.patch(
        f"/api/auth/departments/{dept.id}/labs/{lab.slug}/",
        {"included_in_plan": True},
        format="json",
    )
    assert inc.status_code == 200
    assert any(
        row["slug"] == lab.slug and row["included_in_plan"] is True
        for row in inc.data
    )
    assert effective_tier(pi) == Tier.CANOPY


@pytest.mark.django_db
def test_department_create_lab_under_it(client: APIClient) -> None:
    head = _user("head")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)
    client.force_authenticate(head)

    resp = client.post(
        f"/api/auth/departments/{dept.id}/labs/",
        {"name": "New Lab"},
        format="json",
    )

    assert resp.status_code == 201
    lab = Lab.objects.get(name="New Lab")
    assert lab.department_id == dept.id


@pytest.mark.django_db
def test_department_detach_lab(client: APIClient) -> None:
    head = _user("head")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)
    pi = _user("pi")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    lab.department = dept
    lab.save(update_fields=["department"])
    client.force_authenticate(head)

    resp = client.delete(f"/api/auth/departments/{dept.id}/labs/{lab.slug}/")

    assert resp.status_code == 204
    lab.refresh_from_db()
    assert lab.department_id is None


@pytest.mark.django_db
def test_non_manager_cannot_manage_department(client: APIClient) -> None:
    head = _user("head")
    dept = provision_workspace(head, "department", org_name="Systems").department
    outsider = _user("outsider")
    client.force_authenticate(outsider)

    resp = client.get(f"/api/auth/departments/{dept.id}/members/")
    assert resp.status_code == 403

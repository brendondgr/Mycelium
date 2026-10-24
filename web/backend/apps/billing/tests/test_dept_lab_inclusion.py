"""Per-lab opt-in inclusion in the department plan."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import DeptMembership
from apps.accounts.services import plan_member_ids
from apps.billing.seat_sync import paying_scope_for_lab
from apps.billing.services import (
    activate_department_subscription,
    attach_lab_to_department,
    create_lab_workspace,
    provision_workspace,
)


def _dept(username: str):
    head = User.objects.create_user(username=username, password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department
    return head, dept


@pytest.mark.django_db
def test_plan_member_ids_counts_only_included_labs() -> None:
    head, dept = _dept("head")
    pi = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    attach_lab_to_department(lab, dept)  # attached, not included

    # Direct head counts; the un-included lab's PI does not.
    ids = plan_member_ids(dept)
    assert head.id in ids
    assert pi.id not in ids

    lab.department_plan_included = True
    lab.save(update_fields=["department_plan_included"])
    ids = plan_member_ids(dept)
    assert pi.id in ids


@pytest.mark.django_db
def test_paying_scope_falls_back_to_lab_when_not_included() -> None:
    from apps.billing.services import activate_lab_subscription

    _head, dept = _dept("head")
    activate_department_subscription(dept)
    pi = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    activate_lab_subscription(lab)
    attach_lab_to_department(lab, dept)  # under an active dept, but not opted in

    # Not included → the department does not pay; the lab's own plan does.
    kind, sub = paying_scope_for_lab(lab)
    assert kind == "lab"
    assert sub.scope_lab_id == lab.id


@pytest.mark.django_db
def test_direct_dept_member_unaffected_by_lab_inclusion() -> None:
    """A direct department member is on the plan regardless of any lab flag."""
    head, dept = _dept("head")
    member = User.objects.create_user(username="m", password="p")
    DeptMembership.objects.create(
        user=member, department=dept, role=DeptMembership.Role.MEMBER
    )
    assert member.id in plan_member_ids(dept)


@pytest.mark.django_db
def test_inclusion_toggle_requires_department_manager() -> None:
    head, dept = _dept("head")
    pi = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    attach_lab_to_department(lab, dept)

    client = APIClient()
    client.force_authenticate(pi)  # a lab PI, not a department manager
    resp = client.patch(
        f"/api/auth/departments/{dept.id}/labs/{lab.slug}/",
        {"included_in_plan": True},
        format="json",
    )
    assert resp.status_code == 403
    lab.refresh_from_db()
    assert lab.department_plan_included is False


@pytest.mark.django_db
def test_inclusion_toggle_requires_the_field() -> None:
    head, dept = _dept("head")
    pi = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    attach_lab_to_department(lab, dept)

    client = APIClient()
    client.force_authenticate(head)
    resp = client.patch(
        f"/api/auth/departments/{dept.id}/labs/{lab.slug}/", {}, format="json"
    )
    assert resp.status_code == 400

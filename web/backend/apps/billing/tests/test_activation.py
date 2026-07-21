"""Activation: inactive-by-default (L1) and effective-membership seeding (L2)."""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import LabMembership
from apps.billing.entitlements import effective_tier
from apps.billing.models import Seat, Subscription, Tier
from apps.billing.services import (
    activate_department_subscription,
    activate_lab_subscription,
    attach_lab_to_department,
    create_lab_workspace,
    provision_workspace,
)


@pytest.mark.django_db
def test_new_lab_is_inactive_and_founder_is_free() -> None:
    founder = User.objects.create_user(username="pi", password="p")
    result = create_lab_workspace(founder, "Rivera Lab")

    assert result.subscription.status == Subscription.Status.INACTIVE
    assert result.seat.status == Seat.Status.PENDING
    assert effective_tier(founder) == Tier.FREE  # structure is free until activated


@pytest.mark.django_db
def test_activating_lab_seats_all_members() -> None:
    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    member = User.objects.create_user(username="student", password="p")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)

    activate_lab_subscription(lab)

    assert effective_tier(founder) == Tier.LAB
    assert effective_tier(member) == Tier.LAB
    for user in (founder, member):
        seat = Seat.objects.get(member=user, subscription__scope_lab=lab)
        assert seat.status == Seat.Status.ACTIVE
        assert seat.payer_type == "lab"


@pytest.mark.django_db
def test_new_department_is_inactive_effective_members_are_free() -> None:
    head = User.objects.create_user(username="head", password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department
    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    attach_lab_to_department(lab, dept)  # dept inactive → no seating happens

    assert effective_tier(head) == Tier.FREE
    assert effective_tier(founder) == Tier.FREE


@pytest.mark.django_db
def test_activating_department_seats_effective_membership() -> None:
    """Rule 2: activating a department entitles every member of every lab under it."""
    head = User.objects.create_user(username="head", password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department

    # A lab under the department, with its own founder + a student, attached while the
    # department is still inactive (so nobody is seated yet).
    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    attach_lab_to_department(lab, dept)
    student = User.objects.create_user(username="student", password="p")
    LabMembership.objects.create(user=student, lab=lab, role=LabMembership.Role.MEMBER)

    activate_department_subscription(dept)

    # The direct head AND both members of the lab under the department are entitled.
    for user in (head, founder, student):
        assert effective_tier(user) == Tier.CANOPY, user.username
        seat = Seat.objects.get(
            member=user, subscription__scope_department=dept, status=Seat.Status.ACTIVE
        )
        assert seat.payer_type == "department"


@pytest.mark.django_db
def test_attach_lab_to_active_department_moves_members_to_dept() -> None:
    """B2: attaching a lab to an active dept re-seats members, defers the lab seat."""
    head = User.objects.create_user(username="head", password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)

    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    activate_lab_subscription(lab)  # standalone active lab first
    assert effective_tier(founder) == Tier.LAB

    attach_lab_to_department(lab, dept)

    # Now department-paid; the old lab seat is scheduled to end (deferred).
    dept_seat = Seat.objects.get(
        member=founder, subscription__scope_department=dept, status=Seat.Status.ACTIVE
    )
    assert dept_seat.payer_type == "department"
    lab_seat = Seat.objects.get(member=founder, subscription__scope_lab=lab)
    assert lab_seat.ends_at is not None
    assert effective_tier(founder) == Tier.CANOPY

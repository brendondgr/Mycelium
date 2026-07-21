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
def test_activating_department_seats_included_labs() -> None:
    """Rule 2 (opt-in): activating a department entitles direct members + members of
    every lab the head has **included** in the plan; a non-included lab is untouched."""
    from apps.billing.services import set_lab_plan_inclusion

    head = User.objects.create_user(username="head", password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department

    # An included lab (opted in while the dept is still inactive — flag only, no seats
    # yet) and a separate lab left opt-out.
    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    attach_lab_to_department(lab, dept)
    set_lab_plan_inclusion(lab, True)
    student = User.objects.create_user(username="student", password="p")
    LabMembership.objects.create(user=student, lab=lab, role=LabMembership.Role.MEMBER)

    excluded_pi = User.objects.create_user(username="excluded", password="p")
    excluded_lab = create_lab_workspace(excluded_pi, "Excluded Lab").lab
    attach_lab_to_department(excluded_lab, dept)  # attached but not opted in

    activate_department_subscription(dept)

    # The direct head AND both members of the included lab are entitled.
    for user in (head, founder, student):
        assert effective_tier(user) == Tier.CANOPY, user.username
        seat = Seat.objects.get(
            member=user, subscription__scope_department=dept, status=Seat.Status.ACTIVE
        )
        assert seat.payer_type == "department"
    # The excluded lab's founder is NOT on the department plan.
    assert not Seat.objects.filter(
        member=excluded_pi, subscription__scope_department=dept
    ).exists()


@pytest.mark.django_db
def test_including_lab_in_active_department_moves_members_to_dept() -> None:
    """B2: including a lab in an active dept re-seats members, defers the lab seat."""
    from apps.billing.services import set_lab_plan_inclusion

    head = User.objects.create_user(username="head", password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)

    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    activate_lab_subscription(lab)  # standalone active lab first
    assert effective_tier(founder) == Tier.LAB

    attach_lab_to_department(lab, dept)
    assert effective_tier(founder) == Tier.LAB  # attach alone doesn't move them (opt-in)

    set_lab_plan_inclusion(lab, True)

    # Now department-paid; the old lab seat is scheduled to end (deferred).
    dept_seat = Seat.objects.get(
        member=founder, subscription__scope_department=dept, status=Seat.Status.ACTIVE
    )
    assert dept_seat.payer_type == "department"
    lab_seat = Seat.objects.get(member=founder, subscription__scope_lab=lab)
    assert lab_seat.ends_at is not None
    assert effective_tier(founder) == Tier.CANOPY


@pytest.mark.django_db
def test_excluding_lab_defers_the_department_seat() -> None:
    """Excluding an included lab schedules its members' department seat to end
    (deferred, L3 — still ACTIVE + billed through the period, no inline lab re-seat,
    so a member is never double-billed). The lab-paid fallback is picked up later by
    the normal seat sync, matching detach."""
    from apps.billing.services import set_lab_plan_inclusion

    head = User.objects.create_user(username="head", password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)

    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    activate_lab_subscription(lab)
    attach_lab_to_department(lab, dept)
    set_lab_plan_inclusion(lab, True)
    assert effective_tier(founder) == Tier.CANOPY

    set_lab_plan_inclusion(lab, False)

    # The dept seat is scheduled to end (deferred), so entitlement holds this period.
    dept_seat = Seat.objects.get(member=founder, subscription__scope_department=dept)
    assert dept_seat.ends_at is not None
    assert effective_tier(founder) == Tier.CANOPY  # deferred: no immediate downgrade

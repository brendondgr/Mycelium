"""Seat-sync wiring (rules 1 & 2, decision B2: one paying scope per member)."""

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import LabMembership
from apps.billing.entitlements import effective_tier
from apps.billing.models import Seat, Tier
from apps.billing.seat_sync import (
    paying_scope_for_lab,
    sync_lab_member,
    unsync_lab_member,
)
from apps.billing.services import (
    activate_department_subscription,
    activate_lab_subscription,
    attach_lab_to_department,
    create_lab_workspace,
    provision_workspace,
)


def _active_department(username: str) -> tuple[User, object]:
    head = User.objects.create_user(username=username, password="p")
    result = provision_workspace(head, "department", org_name=f"{username} Dept")
    activate_department_subscription(result.department)
    return head, result.department


def _active_standalone_lab(username: str) -> tuple[User, object]:
    founder = User.objects.create_user(username=username, password="p")
    lab = create_lab_workspace(founder, f"{username} Lab").lab
    activate_lab_subscription(lab)
    return founder, lab


@pytest.mark.django_db
def test_lab_under_active_dept_member_seated_on_dept_not_lab() -> None:
    """B2: a lab belonging to an active department seats its members department-paid."""
    _head, dept = _active_department("head")
    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    attach_lab_to_department(lab, dept)  # lab is under the active department now

    member = User.objects.create_user(username="student", password="p")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    sync_lab_member(member, lab)

    kind, sub = paying_scope_for_lab(lab)
    assert kind == "department"
    seat = Seat.objects.get(member=member, status=Seat.Status.ACTIVE)
    assert seat.subscription.scope_department_id == dept.id
    assert seat.payer_type == "department"
    # No lab-scoped seat was created for them (one paying scope).
    assert not Seat.objects.filter(
        member=member, subscription__scope_lab=lab
    ).exists()
    assert effective_tier(member) == Tier.CANOPY


@pytest.mark.django_db
def test_standalone_lab_member_seated_on_lab() -> None:
    _founder, lab = _active_standalone_lab("owner")
    member = User.objects.create_user(username="student", password="p")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)

    sync_lab_member(member, lab)

    seat = Seat.objects.get(member=member, status=Seat.Status.ACTIVE)
    assert seat.subscription.scope_lab_id == lab.id
    assert seat.payer_type == "lab"
    assert effective_tier(member) == Tier.LAB


@pytest.mark.django_db
def test_sync_is_noop_on_inactive_lab() -> None:
    founder = User.objects.create_user(username="owner", password="p")
    lab = create_lab_workspace(founder, "Dormant Lab").lab  # never activated
    member = User.objects.create_user(username="student", password="p")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)

    assert sync_lab_member(member, lab) is None
    assert not Seat.objects.filter(member=member, status=Seat.Status.ACTIVE).exists()
    assert effective_tier(member) == Tier.FREE


@pytest.mark.django_db
def test_unsync_defers_seat_removal() -> None:
    _founder, lab = _active_standalone_lab("owner")
    member = User.objects.create_user(username="student", password="p")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    sync_lab_member(member, lab)

    unsync_lab_member(member, lab)

    seat = Seat.objects.get(member=member)
    assert seat.status == Seat.Status.ACTIVE  # deferred, not revoked
    assert seat.ends_at is not None
    assert effective_tier(member) == Tier.LAB  # access retained until period end


@pytest.mark.django_db
def test_reconcile_backfills_lab_under_dept_member() -> None:
    """The backstop: a lab-under-dept member with no seat is backfilled to CANOPY."""
    _head, dept = _active_department("head")
    founder = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(founder, "Sub Lab").lab
    attach_lab_to_department(lab, dept)
    # A member added directly (a seed / pre-fix scenario) with no seat.
    stranded = User.objects.create_user(username="stranded", password="p")
    LabMembership.objects.create(user=stranded, lab=lab, role=LabMembership.Role.MEMBER)
    assert effective_tier(stranded) == Tier.FREE

    call_command("reconcile_seats")

    assert effective_tier(stranded) == Tier.CANOPY
    seat = Seat.objects.get(
        member=stranded, subscription__scope_department=dept, status=Seat.Status.ACTIVE
    )
    assert seat.payer_type == "department"

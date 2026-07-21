"""When a department seat lapses, members fall back to their lab's own plan."""

from datetime import date

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import LabMembership
from apps.billing.entitlements import Tier, effective_tier
from apps.billing.models import Seat
from apps.billing.period import end_lapsed_seats
from apps.accounts.services import detach_lab_from_department
from apps.billing.services import (
    activate_department_subscription,
    activate_lab_subscription,
    attach_lab_to_department,
    create_lab_workspace,
    provision_workspace,
    set_lab_plan_inclusion,
)

# Well past any monthly period opened during the test, so the deferred cutoff lapses.
FUTURE = date(2027, 1, 1)


def _dept(username: str):
    head = User.objects.create_user(username=username, password="p")
    dept = provision_workspace(head, "department", org_name="Systems").department
    activate_department_subscription(dept)
    return head, dept


def _included_lab_with_own_plan(dept, pi_name="pi"):
    pi = User.objects.create_user(username=pi_name, password="p")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    activate_lab_subscription(lab)  # the lab carries its own active plan
    attach_lab_to_department(lab, dept)
    set_lab_plan_inclusion(lab, True)
    return pi, lab


@pytest.mark.django_db
def test_excluded_lab_member_falls_back_to_lab_plan_after_lapse() -> None:
    _head, dept = _dept("head")
    pi, lab = _included_lab_with_own_plan(dept)
    assert effective_tier(pi) == Tier.CANOPY

    set_lab_plan_inclusion(lab, False)  # dept seat deferred, still CANOPY this period
    assert effective_tier(pi) == Tier.CANOPY

    end_lapsed_seats(now=FUTURE)  # the tick: the dept seat lapses

    # The department seat is revoked; the member is now on the lab-paid seat.
    dept_seat = Seat.objects.get(member=pi, subscription__scope_department=dept)
    assert dept_seat.status == Seat.Status.REVOKED
    lab_seat = Seat.objects.get(member=pi, subscription__scope_lab=lab)
    assert lab_seat.status == Seat.Status.ACTIVE
    assert effective_tier(pi) == Tier.LAB  # fell back, did not drop to Free


@pytest.mark.django_db
def test_detached_lab_member_falls_back_to_lab_plan_after_lapse() -> None:
    _head, dept = _dept("head")
    pi, lab = _included_lab_with_own_plan(dept)
    assert effective_tier(pi) == Tier.CANOPY

    detach_lab_from_department(dept, lab)  # leaves the dept; dept seat deferred
    end_lapsed_seats(now=FUTURE)

    assert effective_tier(pi) == Tier.LAB


@pytest.mark.django_db
def test_excluded_lab_without_own_plan_drops_to_free() -> None:
    """No lab plan to fall back to → the member correctly drops to Free (no phantom seat)."""
    _head, dept = _dept("head")
    pi = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(pi, "Sub Lab").lab  # NOT activated — no own plan
    attach_lab_to_department(lab, dept)
    set_lab_plan_inclusion(lab, True)
    assert effective_tier(pi) == Tier.CANOPY

    set_lab_plan_inclusion(lab, False)
    end_lapsed_seats(now=FUTURE)

    assert effective_tier(pi) == Tier.FREE
    assert not Seat.objects.filter(
        member=pi, subscription__scope_lab=lab, status=Seat.Status.ACTIVE
    ).exists()


@pytest.mark.django_db
def test_removed_lab_member_is_not_re_seated() -> None:
    """A member removed from a standalone lab (their lab seat lapses) is not handed a
    new seat by the fallback — the fallback only fires for department-paid lapses."""
    from apps.billing.seat_sync import unsync_lab_member

    pi = User.objects.create_user(username="pi", password="p")
    lab = create_lab_workspace(pi, "Solo Lab").lab
    activate_lab_subscription(lab)
    member = User.objects.create_user(username="m", password="p")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    from apps.billing.seat_sync import sync_lab_member

    sync_lab_member(member, lab)
    assert effective_tier(member) == Tier.LAB

    # Remove them from the lab, then lapse the seat.
    LabMembership.objects.filter(user=member, lab=lab).delete()
    unsync_lab_member(member, lab)
    end_lapsed_seats(now=FUTURE)

    assert effective_tier(member) == Tier.FREE
    assert not Seat.objects.filter(
        member=member, status=Seat.Status.ACTIVE
    ).exists()

"""Seat integrity (P0): membership grants a seat; removal defers, never deletes."""

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.accounts.models import Lab, LabInvitation, LabMembership
from apps.accounts.services import accept_invitation
from apps.billing import period
from apps.billing.entitlements import Feature, effective_tier, has_feature
from apps.billing.models import Seat, Tier
from apps.billing.seats import (
    SeatCeilingExceeded,
    grant_seat_for_lab_member,
    revoke_seat_for_lab_member,
)
from apps.billing.services import activate_lab_subscription, create_lab_workspace


@pytest.fixture
def paying_lab(db: None) -> tuple[User, Lab]:
    """A lab on an ACTIVE LAB subscription, with its founder already seated.

    Labs are provisioned INACTIVE (decision L1), so the fixture activates the plan —
    which opens the billing period and seats the founder ACTIVE.
    """
    founder = User.objects.create_user(username="founder", password="p")
    result = create_lab_workspace(founder, "Rivera Lab")
    activate_lab_subscription(result.lab)
    return founder, result.lab


def _invite(lab: Lab, inviter: User, invitee: User) -> LabInvitation:
    return LabInvitation.objects.create(
        lab=lab, inviter=inviter, invitee=invitee, role=LabMembership.Role.MEMBER
    )


@pytest.mark.django_db
def test_invited_lab_member_resolves_to_lab_tier(paying_lab) -> None:
    """The P0 bug, pinned: an accepted invite must seat the member."""
    founder, lab = paying_lab
    invitee = User.objects.create_user(username="member", password="p")

    accept_invitation(_invite(lab, founder, invitee), invitee)

    assert LabMembership.objects.filter(user=invitee, lab=lab).exists()
    seat = Seat.objects.get(subscription__scope_lab=lab, member=invitee)
    assert seat.status == Seat.Status.ACTIVE
    assert seat.payer_type == "lab"  # lab-sponsored, not self-paid
    assert effective_tier(invitee) == Tier.LAB
    assert has_feature(invitee, Feature.SHARED_EVIDENCE_GRAPH)


@pytest.mark.django_db
def test_membership_removal_defers_to_period_end_then_tick_revokes(paying_lab) -> None:
    """Removal keeps access until period end (L3), then the tick revokes — no delete."""
    founder, lab = paying_lab
    member = User.objects.create_user(username="member", password="p")
    grant_seat_for_lab_member(member, lab)
    assert effective_tier(member) == Tier.LAB
    sub = lab.subscriptions.get()

    revoke_seat_for_lab_member(member, lab)

    # Deferred: the seat is still ACTIVE (access retained) with a removal cutoff.
    seat = Seat.objects.get(subscription__scope_lab=lab, member=member)
    assert seat.status == Seat.Status.ACTIVE
    assert seat.ends_at == sub.current_period_end
    assert effective_tier(member) == Tier.LAB

    # The tick at period end flips it to REVOKED (row survives) and access ends.
    period.end_lapsed_seats(now=sub.current_period_end)
    seat.refresh_from_db()
    assert seat.status == Seat.Status.REVOKED
    assert effective_tier(member) == Tier.FREE


@pytest.mark.django_db
def test_lab_seat_creation_refused_past_15_members(paying_lab) -> None:
    founder, lab = paying_lab  # founder is seat #1

    # 14 more members bring the active count to 15 (the Lab ceiling).
    for i in range(14):
        grant_seat_for_lab_member(
            User.objects.create_user(username=f"m{i}", password="p"), lab
        )
    assert Seat.objects.filter(
        subscription__scope_lab=lab, status=Seat.Status.ACTIVE
    ).count() == 15

    # The 16th is refused, not silently seated.
    with pytest.raises(SeatCeilingExceeded):
        grant_seat_for_lab_member(
            User.objects.create_user(username="over", password="p"), lab
        )


@pytest.mark.django_db
def test_grant_seat_is_idempotent(paying_lab) -> None:
    founder, lab = paying_lab
    member = User.objects.create_user(username="member", password="p")

    grant_seat_for_lab_member(member, lab)
    grant_seat_for_lab_member(member, lab)

    assert Seat.objects.filter(
        subscription__scope_lab=lab, member=member
    ).count() == 1


@pytest.mark.django_db
def test_free_lab_membership_grants_no_seat(db: None) -> None:
    """A lab with no active subscription has nothing to seat."""
    member = User.objects.create_user(username="member", password="p")
    lab = Lab.objects.create(name="Free Lab", slug="free-lab")
    assert grant_seat_for_lab_member(member, lab) is None
    assert not Seat.objects.filter(member=member).exists()


@pytest.mark.django_db
def test_re_adding_before_period_end_clears_removal(paying_lab) -> None:
    """Re-adding a member scheduled for removal un-schedules it (clears ends_at)."""
    founder, lab = paying_lab
    member = User.objects.create_user(username="member", password="p")
    grant_seat_for_lab_member(member, lab)
    revoke_seat_for_lab_member(member, lab)  # deferred removal
    seat = Seat.objects.get(subscription__scope_lab=lab, member=member)
    assert seat.ends_at is not None

    grant_seat_for_lab_member(member, lab)  # changed their mind

    seat.refresh_from_db()
    assert seat.status == Seat.Status.ACTIVE
    assert seat.ends_at is None
    assert Seat.objects.filter(subscription__scope_lab=lab, member=member).count() == 1
    assert effective_tier(member) == Tier.LAB


@pytest.mark.django_db
def test_reactivating_a_revoked_seat_restores_tier(paying_lab) -> None:
    """A fully REVOKED seat (past the tick) can be re-granted on the same row."""
    founder, lab = paying_lab
    member = User.objects.create_user(username="member", password="p")
    grant_seat_for_lab_member(member, lab)
    revoke_seat_for_lab_member(member, lab)
    sub = lab.subscriptions.get()
    period.end_lapsed_seats(now=sub.current_period_end)  # actually revoke
    assert effective_tier(member) == Tier.FREE

    grant_seat_for_lab_member(member, lab)  # re-activate the same row

    assert Seat.objects.filter(subscription__scope_lab=lab, member=member).count() == 1
    assert effective_tier(member) == Tier.LAB


@pytest.mark.django_db
def test_reconcile_seats_backfills_unseated_membership(paying_lab) -> None:
    """Simulate the pre-fix bug: a membership with no seat, then reconcile it."""
    founder, lab = paying_lab
    stranded = User.objects.create_user(username="stranded", password="p")
    # Membership exists but (the old bug) no seat was created.
    LabMembership.objects.create(
        user=stranded, lab=lab, role=LabMembership.Role.MEMBER
    )
    assert effective_tier(stranded) == Tier.FREE

    # A dry run reports it without writing.
    call_command("reconcile_seats", "--dry-run")
    assert not Seat.objects.filter(member=stranded).exists()

    call_command("reconcile_seats")
    assert effective_tier(stranded) == Tier.LAB


@pytest.mark.django_db
def test_accept_invitation_refused_past_ceiling(paying_lab) -> None:
    """A 16th member accepting is refused (400) rather than over-seated."""
    from rest_framework.serializers import ValidationError

    founder, lab = paying_lab
    for i in range(14):  # fill to the 15-seat ceiling
        grant_seat_for_lab_member(
            User.objects.create_user(username=f"m{i}", password="p"), lab
        )
    invitee = User.objects.create_user(username="sixteenth", password="p")

    with pytest.raises(ValidationError):
        accept_invitation(_invite(lab, founder, invitee), invitee)

    # The membership was rolled back with the refused seat (atomic block).
    assert not LabMembership.objects.filter(user=invitee, lab=lab).exists()
    assert not Seat.objects.filter(member=invitee).exists()

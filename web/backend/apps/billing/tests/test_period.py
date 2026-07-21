"""Billing-period lifecycle: activation window, rolling, and deferred-seat expiry."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User

from apps.billing import period
from apps.billing.models import Seat, SeatEvent, Subscription, Tier


def _sub(status=Subscription.Status.INACTIVE, **kwargs) -> Subscription:
    user = User.objects.create_user(username=f"u{User.objects.count()}", password="p")
    return Subscription.objects.create(
        tier=Tier.LAB, scope_user=user, status=status, **kwargs
    )


@pytest.mark.django_db
def test_inactive_plan_is_not_current() -> None:
    sub = _sub()
    assert sub.is_current() is False


@pytest.mark.django_db
def test_activate_opens_one_month_window() -> None:
    sub = _sub()
    start = date(2026, 7, 21)

    period.activate(sub, on=start)

    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE
    assert sub.activated_at is not None
    assert sub.current_period_start == start
    assert sub.current_period_end == date(2026, 8, 21)
    assert sub.is_current() is True


@pytest.mark.django_db
def test_activate_is_idempotent_and_does_not_shift_window() -> None:
    sub = _sub()
    start = date(2026, 7, 21)
    period.activate(sub, on=start)
    first_activated = Subscription.objects.get(pk=sub.pk).activated_at

    period.activate(sub, on=date(2026, 7, 25))  # a second click, later date

    sub.refresh_from_db()
    assert sub.current_period_start == start  # window unchanged
    assert sub.current_period_end == date(2026, 8, 21)
    assert sub.activated_at == first_activated  # not re-stamped


@pytest.mark.django_db
def test_add_one_month_clamps_to_end_of_short_month() -> None:
    assert period.add_one_month(date(2026, 1, 31)) == date(2026, 2, 28)
    assert period.add_one_month(date(2024, 1, 31)) == date(2024, 2, 29)  # leap
    assert period.add_one_month(date(2026, 12, 15)) == date(2027, 1, 15)  # year roll


@pytest.mark.django_db
def test_roll_periods_advances_only_ended_windows() -> None:
    today = period.today()
    ended = _sub(
        status=Subscription.Status.ACTIVE,
        current_period_start=today - timedelta(days=40),
        current_period_end=today - timedelta(days=10),
    )
    current = _sub(
        status=Subscription.Status.ACTIVE,
        current_period_start=today - timedelta(days=5),
        current_period_end=today + timedelta(days=25),
    )

    rolled = period.roll_periods(now=today)

    assert rolled == 1
    ended.refresh_from_db()
    current.refresh_from_db()
    assert ended.current_period_end > today  # advanced past today
    assert current.current_period_end == today + timedelta(days=25)  # untouched


@pytest.mark.django_db
def test_roll_periods_closes_a_multi_month_gap() -> None:
    today = date(2026, 7, 21)
    sub = _sub(
        status=Subscription.Status.ACTIVE,
        current_period_start=date(2026, 4, 1),
        current_period_end=date(2026, 5, 1),
    )

    period.roll_periods(now=today)

    sub.refresh_from_db()
    assert sub.current_period_start <= today < sub.current_period_end


@pytest.mark.django_db
def test_end_lapsed_seats_revokes_only_past_cutoff() -> None:
    today = period.today()
    sub = _sub(status=Subscription.Status.ACTIVE)
    m1 = User.objects.create_user(username="lapsed", password="p")
    m2 = User.objects.create_user(username="future", password="p")
    lapsed = Seat.objects.create(
        subscription=sub, member=m1, payer_user=m1,
        status=Seat.Status.ACTIVE, ends_at=today - timedelta(days=1),
    )
    future = Seat.objects.create(
        subscription=sub, member=m2, payer_user=m2,
        status=Seat.Status.ACTIVE, ends_at=today + timedelta(days=5),
    )

    revoked = period.end_lapsed_seats(now=today)

    assert revoked == 1
    lapsed.refresh_from_db()
    future.refresh_from_db()
    assert lapsed.status == Seat.Status.REVOKED
    assert future.status == Seat.Status.ACTIVE
    assert SeatEvent.objects.filter(
        seat=lapsed, kind=SeatEvent.Kind.EXPIRED
    ).exists()

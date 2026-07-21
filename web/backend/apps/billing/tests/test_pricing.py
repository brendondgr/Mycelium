"""Seat pricing + mid-cycle proration (L3: prorate adds, no credit on removal)."""

from datetime import date

import pytest
from django.contrib.auth.models import User

from apps.billing import pricing
from apps.billing.models import Seat, Subscription, Tier


def _lab_sub(**kwargs) -> Subscription:
    user = User.objects.create_user(username=f"u{User.objects.count()}", password="p")
    return Subscription.objects.create(
        tier=Tier.LAB, scope_user=user, status=Subscription.Status.ACTIVE, **kwargs
    )


def _seat(sub: Subscription, *, status=Seat.Status.ACTIVE, ends_at=None) -> Seat:
    member = User.objects.create_user(username=f"m{User.objects.count()}", password="p")
    return Seat.objects.create(
        subscription=sub, member=member, payer_user=member,
        status=status, ends_at=ends_at,
    )


@pytest.mark.django_db
def test_seat_price_matches_matrix() -> None:
    assert pricing.seat_price_cents(Tier.FREE) == 0
    assert pricing.seat_price_cents(Tier.SPORE) == 1000
    assert pricing.seat_price_cents(Tier.LAB) == 1250
    assert pricing.seat_price_cents(Tier.CANOPY) == 2000


@pytest.mark.django_db
def test_recurring_monthly_is_active_seats_times_price() -> None:
    sub = _lab_sub()
    for _ in range(3):
        _seat(sub)
    assert pricing.recurring_monthly_cents(sub) == 3 * 1250


@pytest.mark.django_db
def test_pending_removal_seat_still_billed_no_credit() -> None:
    """A seat scheduled for removal is still ACTIVE, so it still counts (L3)."""
    sub = _lab_sub()
    _seat(sub)  # normal active seat
    _seat(sub, ends_at=date(2026, 12, 31))  # pending removal, still ACTIVE
    # Both count — removal grants no mid-cycle credit.
    assert pricing.recurring_monthly_cents(sub) == 2 * 1250


@pytest.mark.django_db
def test_prorate_full_period_add_is_full_price() -> None:
    cents = pricing.prorate_add(
        Tier.LAB,
        added_on=date(2026, 7, 1),
        period_start=date(2026, 7, 1),
        period_end=date(2026, 8, 1),
    )
    assert cents == 1250


@pytest.mark.django_db
def test_prorate_before_start_full_after_end_zero() -> None:
    kw = dict(period_start=date(2026, 7, 10), period_end=date(2026, 8, 10))
    assert pricing.prorate_add(Tier.LAB, added_on=date(2026, 7, 1), **kw) == 1250
    assert pricing.prorate_add(Tier.LAB, added_on=date(2026, 8, 20), **kw) == 0


@pytest.mark.django_db
def test_prorate_midcycle_add_is_fraction_of_price() -> None:
    # 31-day period; added with 15 days remaining → ~15/31 of $12.50.
    cents = pricing.prorate_add(
        Tier.LAB,
        added_on=date(2026, 7, 17),
        period_start=date(2026, 7, 1),
        period_end=date(2026, 8, 1),
    )
    assert cents == round(1250 * 15 / 31)
    assert 0 < cents < 1250


@pytest.mark.django_db
def test_free_tier_never_prorates() -> None:
    cents = pricing.prorate_add(
        Tier.FREE,
        added_on=date(2026, 7, 17),
        period_start=date(2026, 7, 1),
        period_end=date(2026, 8, 1),
    )
    assert cents == 0


@pytest.mark.django_db
def test_activation_quote_is_full_period() -> None:
    sub = _lab_sub()
    quote = pricing.activation_quote(sub, seat_count=4)
    assert quote == {
        "tier": Tier.LAB,
        "seat_count": 4,
        "seat_price_cents": 1250,
        "recurring_monthly_cents": 5000,
    }


@pytest.mark.django_db
def test_add_members_quote_inactive_plan_is_full_price() -> None:
    user = User.objects.create_user(username="head", password="p")
    inactive = Subscription.objects.create(
        tier=Tier.CANOPY, scope_user=user, status=Subscription.Status.INACTIVE
    )
    quote = pricing.add_members_quote(inactive, count=2, added_on=date(2026, 7, 21))
    assert quote == {"count": 2, "prorated_cents": 2 * 2000, "prorated": False}

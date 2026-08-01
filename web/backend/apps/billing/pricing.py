"""Seat-based pricing + mid-cycle proration for lab & department plans.

Amounts are computed and ledgered only — there is no charging here (payment processing
is out of scope, no Stripe coupling). Prices mirror briefing §7 and live as data beside
the other caps. Policy (decision L3): a seat added mid-cycle is prorated for the
remaining days of the period; a removed seat is billed through period end with **no
credit**.
"""

from __future__ import annotations

from datetime import date

from .entitlements import active_seat_count
from .models import Subscription, Tier

# Per-member monthly price in cents (briefing §7). Informational; never charged.
TIER_PRICE_CENTS: dict[str, int] = {
    Tier.FREE: 0,
    Tier.SPORE: 1000,  # $10 / user / mo
    Tier.LAB: 1250,  # $12.50 / member / mo
    Tier.CANOPY: 2000,  # $20 / member / mo
}


def seat_price_cents(tier: str) -> int:
    """The per-member monthly price for a tier (0 for Free / unknown)."""
    return TIER_PRICE_CENTS.get(tier, 0)


def recurring_monthly_cents(subscription: Subscription) -> int:
    """The steady-state monthly total: active seats × per-seat price.

    A seat pending deferred removal is still ACTIVE, so it still counts this cycle
    (billed through period end, no credit — L3). A **comped** plan totals zero however
    many seats it holds — the list price stays readable via :func:`seat_price_cents`
    so the plan page can strike it through rather than hide it.
    """
    if getattr(subscription, "is_comped", False):
        return 0
    return active_seat_count(subscription) * seat_price_cents(subscription.tier)


def _period_days(start: date, end: date) -> int:
    return max((end - start).days, 1)


def prorate_add(
    tier: str, *, added_on: date, period_start: date, period_end: date
) -> int:
    """Prorated cents for a seat added mid-cycle — the remaining-days fraction (L3).

    A member added on (or before) the period start pays the full price; one added on the
    last day pays ~one day's worth; one added at/after period end pays nothing. Never
    negative.
    """
    price = seat_price_cents(tier)
    if price == 0:
        return 0
    if added_on <= period_start:
        return price
    if added_on >= period_end:
        return 0
    total_days = _period_days(period_start, period_end)
    remaining = (period_end - added_on).days
    return round(price * remaining / total_days)


def activation_quote(
    subscription: Subscription, *, seat_count: int | None = None
) -> dict:
    """A full-period cost preview for activating a plan with ``seat_count`` seats."""
    count = seat_count if seat_count is not None else active_seat_count(subscription)
    price = seat_price_cents(subscription.tier)
    return {
        "tier": subscription.tier,
        "seat_count": count,
        "seat_price_cents": price,
        "recurring_monthly_cents": count * price,
    }


def add_members_quote(
    subscription: Subscription, *, count: int, added_on: date
) -> dict:
    """A cost preview for adding ``count`` members mid-cycle (prorated, L3).

    On an inactive plan there is no open period, so the adds fold into the eventual
    activation at full price (``prorated=False``).
    """
    start = subscription.current_period_start
    end = subscription.current_period_end
    if not (start and end):
        per = seat_price_cents(subscription.tier)
        return {"count": count, "prorated_cents": per * count, "prorated": False}
    per = prorate_add(
        subscription.tier, added_on=added_on, period_start=start, period_end=end
    )
    return {"count": count, "prorated_cents": per * count, "prorated": True}

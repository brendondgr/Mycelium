"""Entitlement resolution (briefing §7).

Single source of truth for what each tier unlocks. Gate features by resolving
the effective subscriptions covering a user (their personal plan plus any plan
where they hold an active seat) and checking the entitlement matrix — never by
hard-coding tier-name checks scattered through the codebase.
"""

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from .models import Seat, Subscription, Tier


class Feature:
    """Named capabilities gated by subscription tier."""

    ACCOUNT = "account"
    BASIC_SEARCH = "basic_search"
    PERSONALIZED_RECOMMENDATIONS = "personalized_recommendations"
    DAILY_DIGESTS = "daily_digests"
    SEMANTIC_SEARCH = "semantic_search"
    WEEKLY_PULSE = "weekly_pulse"
    TEAM_WORKSPACE = "team_workspace"
    MEMBER_PROFILES = "member_profiles"
    SHARED_EVIDENCE_GRAPH = "shared_evidence_graph"
    GRANT_ALERTS = "grant_alerts"
    BOT = "bot"
    DEPARTMENT_ROUTING = "department_routing"
    ADVANCED_ADMIN = "advanced_admin"
    PRIORITY_SUPPORT = "priority_support"
    FLEXIBLE_SEAT_BILLING = "flexible_seat_billing"


# Free is the baseline (account + basic, non-personalized search). Spore adds the
# personalization line; Lab adds the shared line; Canopy adds department scope.
_FREE = frozenset({Feature.ACCOUNT, Feature.BASIC_SEARCH})
_SPORE = _FREE | {
    Feature.PERSONALIZED_RECOMMENDATIONS,
    Feature.DAILY_DIGESTS,
    Feature.SEMANTIC_SEARCH,
    Feature.WEEKLY_PULSE,
}
_LAB = _SPORE | {
    Feature.TEAM_WORKSPACE,
    Feature.MEMBER_PROFILES,
    Feature.SHARED_EVIDENCE_GRAPH,
    Feature.GRANT_ALERTS,
    Feature.BOT,
}
_CANOPY = _LAB | {
    Feature.DEPARTMENT_ROUTING,
    Feature.ADVANCED_ADMIN,
    Feature.PRIORITY_SUPPORT,
    Feature.FLEXIBLE_SEAT_BILLING,
}

TIER_FEATURES: dict[str, frozenset[str]] = {
    Tier.FREE: _FREE,
    Tier.SPORE: frozenset(_SPORE),
    Tier.LAB: frozenset(_LAB),
    Tier.CANOPY: frozenset(_CANOPY),
}

# Per-tier PI caps (briefing §5). ``None`` means unlimited.
PI_CAPS: dict[str, int | None] = {
    Tier.FREE: 1,
    Tier.SPORE: 1,
    Tier.LAB: 5,
    Tier.CANOPY: None,
}

_TIER_RANK = {Tier.FREE: 0, Tier.SPORE: 1, Tier.LAB: 2, Tier.CANOPY: 3}


def features_for_tier(tier: str) -> frozenset[str]:
    return TIER_FEATURES.get(tier, _FREE)


def covering_subscriptions(user: User) -> QuerySet[Subscription]:
    """Active subscriptions that cover a user: their own plan or any plan where
    they hold an active seat."""
    return (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE)
        .filter(
            Q(scope_user=user)
            | Q(seats__member=user, seats__status=Seat.Status.ACTIVE)
        )
        .distinct()
    )


def effective_features(user: User) -> frozenset[str]:
    """The union of features the user is entitled to, defaulting to Free."""
    features = set(_FREE)
    for tier in covering_subscriptions(user).values_list("tier", flat=True):
        features |= TIER_FEATURES.get(tier, _FREE)
    return frozenset(features)


def effective_tier(user: User) -> str:
    """The highest-ranked tier covering the user, or Free if none."""
    tiers = list(covering_subscriptions(user).values_list("tier", flat=True))
    if not tiers:
        return Tier.FREE
    return max(tiers, key=lambda tier: _TIER_RANK.get(tier, 0))


def has_feature(user: User, feature: str) -> bool:
    return feature in effective_features(user)


def active_seat_count(subscription: Subscription) -> int:
    """Number of active seats — the billable seat count for a subscription."""
    return subscription.seats.filter(status=Seat.Status.ACTIVE).count()


def pi_cap(tier: str) -> int | None:
    return PI_CAPS.get(tier, 1)


def within_pi_cap(lead_count: int, tier: str) -> bool:
    """Whether ``lead_count`` PIs is allowed under ``tier`` (None cap = unlimited)."""
    cap = pi_cap(tier)
    return cap is None or lead_count <= cap

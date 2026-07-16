"""Entitlement resolution — the single read path for what a tier unlocks.

Gate features by resolving the effective subscriptions covering a user (their
personal plan plus any plan where they hold an active seat), unioning the tier
matrix with any active add-ons, and checking the result — never by hard-coding
tier-name checks scattered through the codebase (architecture decision A1).

The vocabulary mirrors the pricing matrix:

    Free   account + semantic search/scoring only (an on-demand product — it
           searches and scores when asked and pushes nothing)
    Spore  + LLM fit scoring, scheduled reports, grant/conference alerts,
           fellowship matching, Mylo DM
    Lab    + team workspace, member profiles, shared evidence graph
    Canopy + department routing, custom topic feeds, API access

Add-ons are orthogonal to tiers (A4): the Mylo-server capability is granted by a
:class:`~apps.billing.models.SubscriptionAddOn`, never by a tier.
"""

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from .models import AddOn, Seat, Subscription, SubscriptionAddOn, Tier


class Feature:
    """Named capabilities gated by subscription tier or add-on."""

    # Baseline — every tier, including Free.
    ACCOUNT = "account"
    BASIC_SEARCH = "basic_search"
    SEMANTIC_SEARCH = "semantic_search"
    SEMANTIC_RELEVANCE_SCORING = "semantic_relevance_scoring"

    # The intelligence line — Spore and up.
    LLM_FIT_SCORING = "llm_fit_scoring"  # reasoned match verdict; Free = semantic only
    SCHEDULED_REPORTS = "scheduled_reports"  # master gate: any timer-driven delivery
    GRANT_ALERTS = "grant_alerts"
    FELLOWSHIP_MATCHING = "fellowship_matching"
    CONFERENCE_ALERTS = "conference_alerts"
    BOT_DM = "bot_dm"  # Mylo DMs you on a linked Discord account

    # The team line — Lab and up.
    TEAM_WORKSPACE = "team_workspace"
    MEMBER_PROFILES = "member_profiles"
    SHARED_EVIDENCE_GRAPH = "shared_evidence_graph"

    # The department line — Canopy only.
    DEPARTMENT_ROUTING = "department_routing"
    ADVANCED_ADMIN = "advanced_admin"
    PRIORITY_SUPPORT = "priority_support"
    FLEXIBLE_SEAT_BILLING = "flexible_seat_billing"
    CUSTOM_TOPIC_FEEDS = "custom_topic_feeds"
    API_ACCESS = "api_access"

    # Add-on granted — never tier-granted (A4).
    BOT_SERVER = "bot_server"  # Mylo joins your guild


# Free is the baseline: account + semantic search/scoring, but explicitly **no**
# LLM fit scoring and **no** scheduled reports — it is an on-demand product.
_FREE = frozenset(
    {
        Feature.ACCOUNT,
        Feature.BASIC_SEARCH,
        Feature.SEMANTIC_SEARCH,
        Feature.SEMANTIC_RELEVANCE_SCORING,
    }
)
# Spore adds the whole intelligence line (LLM verdicts, scheduled delivery, grant /
# conference alerts, personal fellowship matching, Mylo DMs).
_SPORE = _FREE | {
    Feature.LLM_FIT_SCORING,
    Feature.SCHEDULED_REPORTS,
    Feature.GRANT_ALERTS,
    Feature.FELLOWSHIP_MATCHING,
    Feature.CONFERENCE_ALERTS,
    Feature.BOT_DM,
}
# Lab adds the shared/team line. It does **not** add BOT_SERVER — that is an add-on.
_LAB = _SPORE | {
    Feature.TEAM_WORKSPACE,
    Feature.MEMBER_PROFILES,
    Feature.SHARED_EVIDENCE_GRAPH,
}
# Canopy adds department scope plus the two Canopy-only power features.
_CANOPY = _LAB | {
    Feature.DEPARTMENT_ROUTING,
    Feature.ADVANCED_ADMIN,
    Feature.PRIORITY_SUPPORT,
    Feature.FLEXIBLE_SEAT_BILLING,
    Feature.CUSTOM_TOPIC_FEEDS,
    Feature.API_ACCESS,
}

TIER_FEATURES: dict[str, frozenset[str]] = {
    Tier.FREE: _FREE,
    Tier.SPORE: frozenset(_SPORE),
    Tier.LAB: frozenset(_LAB),
    Tier.CANOPY: frozenset(_CANOPY),
}

# Per-tier PI caps (how many lab leads a tier allows). ``None`` means unlimited.
PI_CAPS: dict[str, int | None] = {
    Tier.FREE: 1,
    Tier.SPORE: 1,
    Tier.LAB: 5,
    Tier.CANOPY: None,
}

# Per-tier watch-topic caps — **per member** for Lab/Canopy, so the same number
# applies to each user's own WatchPreference and the lookup stays uniform (A5).
TOPIC_CAPS: dict[str, int] = {
    Tier.FREE: 3,
    Tier.SPORE: 10,
    Tier.LAB: 15,
    Tier.CANOPY: 15,
}

# Per-tier member ceilings — the hard cap on how many seats a subscription may
# hold. ``None`` means unlimited (Canopy). Used to guard seat creation (P0).
TIER_MEMBER_CAPS: dict[str, int | None] = {
    Tier.FREE: 1,
    Tier.SPORE: 1,
    Tier.LAB: 15,
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


def addon_features_for_subscriptions(subscriptions) -> frozenset[str]:
    """The features granted by active add-ons on the given subscriptions (A4)."""
    subs = list(subscriptions)
    if not subs:
        return frozenset()
    granted = SubscriptionAddOn.objects.filter(
        subscription__in=subs, status=SubscriptionAddOn.Status.ACTIVE
    ).values_list("add_on__feature", flat=True)
    return frozenset(feature for feature in granted if feature)


def effective_features(user: User) -> frozenset[str]:
    """The union of features the user is entitled to (tier ∪ add-ons), Free default."""
    subs = list(covering_subscriptions(user))
    features = set(_FREE)
    for tier in (sub.tier for sub in subs):
        features |= TIER_FEATURES.get(tier, _FREE)
    features |= addon_features_for_subscriptions(subs)
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


def topic_cap_for_tier(tier: str) -> int:
    return TOPIC_CAPS.get(tier, TOPIC_CAPS[Tier.FREE])


def topic_cap(user: User) -> int:
    """The watch-topic cap for a user's effective tier (per member for Lab/Canopy)."""
    return topic_cap_for_tier(effective_tier(user))


def within_topic_cap(user: User, count: int) -> bool:
    """Whether ``count`` watch topics is allowed under the user's tier cap."""
    return count <= topic_cap(user)


def member_cap(tier: str) -> int | None:
    """The seat ceiling for a tier (``None`` = unlimited)."""
    return TIER_MEMBER_CAPS.get(tier, 1)


def within_member_cap(seat_count: int, tier: str) -> bool:
    """Whether ``seat_count`` seats is allowed under ``tier`` (None cap = unlimited)."""
    cap = member_cap(tier)
    return cap is None or seat_count <= cap


def bot_server_addon() -> AddOn | None:
    """The canonical Mylo-server add-on row (seeded by migration), if present."""
    return AddOn.objects.filter(feature=Feature.BOT_SERVER).first()

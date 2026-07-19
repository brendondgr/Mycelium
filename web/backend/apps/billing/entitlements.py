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
from django.utils import timezone

from .models import AddOn, Seat, Subscription, SubscriptionAddOn, Tier


def _unexpired() -> Q:
    """Q matching subscriptions that have not passed their ``expires_at``.

    A null ``expires_at`` is open-ended (never expires); a set one only counts
    while it is still in the future. Combined with a ``status=ACTIVE`` filter this
    is the full "currently grants entitlements" predicate, so a timed grant reverts
    to Free the instant it lapses — no cleanup job, matching read-time enforcement.
    """
    return Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())


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
    """Active, unexpired subscriptions that cover a user: their own plan or any
    plan where they hold an active seat."""
    return (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE)
        .filter(_unexpired())
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


def users_with_feature(feature: str, user_ids=None) -> set[int]:
    """Bulk-resolve which users are entitled to ``feature`` in a few queries.

    The per-user :func:`has_feature` path issues 1-2 queries each, so the daily
    pipelines (which run over every user) would N+1. This resolves the whole
    entitled set at once: every active subscription that grants ``feature`` (by tier
    **or** by an active add-on), then the users that subscription covers (its
    ``scope_user`` plus every active seat-holder). ``user_ids`` narrows the scan.

    ``feature`` in the Free baseline covers everyone, so this short-circuits to the
    full id set (or all active users) for baseline features.
    """
    if feature in _FREE:
        base = User.objects.filter(is_active=True)
        if user_ids is not None:
            base = base.filter(id__in=user_ids)
        return set(base.values_list("id", flat=True))

    granting_tiers = [t for t, feats in TIER_FEATURES.items() if feature in feats]
    addon_sub_ids = SubscriptionAddOn.objects.filter(
        status=SubscriptionAddOn.Status.ACTIVE, add_on__feature=feature
    ).values_list("subscription_id", flat=True)
    granting_subs = (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE)
        .filter(_unexpired())
        .filter(Q(tier__in=granting_tiers) | Q(id__in=addon_sub_ids))
    )

    covered: set[int] = set(
        granting_subs.filter(scope_user__isnull=False).values_list(
            "scope_user_id", flat=True
        )
    )
    covered |= set(
        Seat.objects.filter(
            status=Seat.Status.ACTIVE, subscription__in=granting_subs
        ).values_list("member_id", flat=True)
    )
    if user_ids is not None:
        covered &= set(user_ids)
    return covered


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


def watch_topic_override(user: User) -> int | None:
    """An admin-granted per-user watch-topic cap, or ``None`` for the tier default.

    Stored on ``Profile.watch_topic_limit`` and set only from the admin dashboard;
    when present it wins over the tier cap so an operator can widen (or narrow) how
    many subjects one user may monitor without changing their plan.
    """
    profile = getattr(user, "profile", None)
    limit = getattr(profile, "watch_topic_limit", None)
    return limit if isinstance(limit, int) else None


def topic_cap(user: User) -> int:
    """The watch-topic cap for a user: the admin override if set, else the tier cap
    (per member for Lab/Canopy)."""
    override = watch_topic_override(user)
    if override is not None:
        return override
    return topic_cap_for_tier(effective_tier(user))


def within_topic_cap(user: User, count: int) -> bool:
    """Whether ``count`` watch topics is allowed under the user's tier cap."""
    return count <= topic_cap(user)


def effective_watch_topics(user: User) -> list[str]:
    """The watch topics a user is entitled to act on — the first ``topic_cap`` of
    their stored topics.

    A downgrade (e.g. Spore → Free) can leave more stored topics than the new cap
    allows. We never delete the excess (that would be unrecoverable data loss on a
    billing event); instead every consumer reads through here, honouring only the
    first N. :func:`topics_over_cap` reports the overflow so the UI can surface it.
    """
    watch = getattr(user, "watch", None)
    topics = list(getattr(watch, "topics", None) or [])
    return topics[: topic_cap(user)]


def topics_over_cap(user: User) -> bool:
    """Whether a user has more stored watch topics than their current tier allows."""
    watch = getattr(user, "watch", None)
    topics = getattr(watch, "topics", None) or []
    return len(topics) > topic_cap(user)


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


def _lab_subscriptions(lab) -> QuerySet[Subscription]:
    """Active subscriptions covering a lab: its own plan or its department's."""
    query = Q(scope_lab=lab)
    dept_id = getattr(lab, "department_id", None)
    if dept_id:
        query |= Q(scope_department_id=dept_id)
    return (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE)
        .filter(_unexpired())
        .filter(query)
    )


def lab_features(lab) -> frozenset[str]:
    """The features a lab is entitled to (its subscription's tier ∪ add-ons).

    Used to gate lab-scoped capabilities like the Mylo-server add-on, which attach
    to the lab's (or its department's) subscription rather than to a single user.
    """
    subs = list(_lab_subscriptions(lab))
    features = set(_FREE)
    for sub in subs:
        features |= TIER_FEATURES.get(sub.tier, _FREE)
    features |= addon_features_for_subscriptions(subs)
    return frozenset(features)


def lab_has_feature(lab, feature: str) -> bool:
    return feature in lab_features(lab)


def can_dm(user: User) -> bool:
    """Whether Mylo may DM this user — the gate any DM-delivery path must check.

    Today the only DM action is the link-time reachability probe; a future daily-
    digest DM must call this before sending so Free accounts are never messaged.
    """
    return has_feature(user, Feature.BOT_DM)

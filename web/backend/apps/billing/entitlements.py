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

**Gating is currently off.** ``BILLING_ENFORCE_ENTITLEMENTS`` defaults to false, and
while it is false the three resolvers here return :data:`ALL_FEATURES` for everyone —
see :func:`enforcing`. Plans are still created, priced and billed; a tier simply
cannot withhold a capability. The numeric caps below (watch topics, clusters, PIs,
seats, projects) are *not* part of that switch and stay enforced, because they bound
how much work the nightly run does rather than what a plan is worth.
"""

from django.conf import settings
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
    # TypeSafe reorders the head of each theme's slate (RERANK_METHOD=typesafe);
    # Free keeps the local order.
    TYPESAFE_RERANK = "typesafe_rerank"
    SCHEDULED_REPORTS = "scheduled_reports"  # master gate: any timer-driven delivery
    GRANT_ALERTS = "grant_alerts"
    FELLOWSHIP_MATCHING = "fellowship_matching"
    CONFERENCE_ALERTS = "conference_alerts"
    BOT_DM = "bot_dm"  # Mylo DMs you on a linked Discord account
    # Deadline reminders — Mylo nudges you (DM) or your lab (channel) ahead of an
    # application/abstract/event date. Discord-delivered, so it is paid-only; the
    # matching Discord-sync half of the gate lives in ``content.reminder_access``.
    DEADLINE_REMINDERS = "deadline_reminders"

    # The team line — Lab and up.
    TEAM_WORKSPACE = "team_workspace"
    MEMBER_PROFILES = "member_profiles"
    SHARED_EVIDENCE_GRAPH = "shared_evidence_graph"
    # One Discord thread per newly fitting grant, fellowship or conference. Posting
    # also needs BOT_SERVER, the add-on that puts Mylo in the server.
    OPPORTUNITY_ANNOUNCEMENTS = "opportunity_announcements"

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
# conference alerts, personal fellowship matching, Mylo DMs, deadline reminders).
_SPORE = _FREE | {
    Feature.LLM_FIT_SCORING,
    Feature.TYPESAFE_RERANK,
    Feature.SCHEDULED_REPORTS,
    Feature.GRANT_ALERTS,
    Feature.FELLOWSHIP_MATCHING,
    Feature.CONFERENCE_ALERTS,
    Feature.BOT_DM,
    Feature.DEADLINE_REMINDERS,
}
# Lab adds the shared/team line. It does **not** add BOT_SERVER — that is an add-on.
_LAB = _SPORE | {
    Feature.TEAM_WORKSPACE,
    Feature.MEMBER_PROFILES,
    Feature.SHARED_EVIDENCE_GRAPH,
    Feature.OPPORTUNITY_ANNOUNCEMENTS,
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

#: Every named capability, tier-granted or add-on-granted. Derived from
#: :class:`Feature` rather than from the tier matrix so a feature that is only
#: ever sold as an add-on (``BOT_SERVER``) is included too.
ALL_FEATURES: frozenset[str] = frozenset(
    value
    for name, value in vars(Feature).items()
    if not name.startswith("_") and isinstance(value, str)
)


def enforcing() -> bool:
    """Whether a tier may currently *withhold* a feature.

    Off by default (``BILLING_ENFORCE_ENTITLEMENTS``). While off, the three
    resolvers below hand back :data:`ALL_FEATURES` for every user, lab and
    department, so every ``has_feature`` call site in the codebase sees a granted
    capability without any of them being edited — which is the whole reason this
    module is the single read path (decision A1).

    Deliberately *not* cached in a module global: it is read per call so a test
    (or a running process) can flip the setting with ``override_settings`` and see
    the change immediately. Subscriptions, seats, prices, invoices and the numeric
    caps further down are untouched by this — billing still bills.
    """
    return bool(getattr(settings, "BILLING_ENFORCE_ENTITLEMENTS", False))


# Per-tier PI caps (how many lab leads a tier allows). ``None`` means unlimited.
PI_CAPS: dict[str, int | None] = {
    Tier.FREE: 1,
    Tier.SPORE: 1,
    Tier.LAB: 5,
    Tier.CANOPY: None,
}

# Per-tier interest-cluster caps. Mylo runs one literature search per cluster, so
# ``CLUSTER_CAPS`` is "how many distinct searches you get" and ``CLUSTER_TOPIC_CAPS``
# is "how many search terms each of those searches may carry". Free is deliberately
# tight — 3 clusters × 2 terms — and ``TOPIC_CAPS`` below is the flat projection of
# that (clusters × per-cluster) so the two limits never disagree. Paid tiers keep
# the structural cluster ceiling and let the flat topic cap govern per-cluster
# breadth (so no paid user is newly boxed in by the per-cluster number).
CLUSTER_CAPS: dict[str, int] = {
    Tier.FREE: 3,
    Tier.SPORE: 6,
    Tier.LAB: 6,
    Tier.CANOPY: 6,
}

CLUSTER_TOPIC_CAPS: dict[str, int] = {
    Tier.FREE: 2,
    Tier.SPORE: 10,
    Tier.LAB: 15,
    Tier.CANOPY: 15,
}

# Per-tier watch-topic caps — **per member** for Lab/Canopy, so the same number
# applies to each user's own WatchPreference and the lookup stays uniform (A5).
# Free is CLUSTER_CAPS × CLUSTER_TOPIC_CAPS (3 × 2 = 6): the flat count a user who
# fills every cluster to the brim lands on, so the watch-save never rejects a
# grouping the organizer let them build.
TOPIC_CAPS: dict[str, int] = {
    Tier.FREE: 6,
    # Spore is what sign-up grants now (``SIGNUP_GRANT_TIER``), so this is the
    # number almost every real account lands on. 20 rather than the original 10:
    # each topic is one more literature search per night, so it is a cost ceiling
    # rather than a tier boundary, and it stays enforced while feature gating does
    # not (see :func:`enforcing`).
    Tier.SPORE: 20,
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
    """The union of features the user is entitled to (tier ∪ add-ons), Free default.

    Returns everything while :func:`enforcing` is off.
    """
    if not enforcing():
        return ALL_FEATURES
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
    full id set (or all active users) for baseline features — as does *any* feature
    while :func:`enforcing` is off.
    """
    if feature in _FREE or not enforcing():
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


def cluster_cap_for_tier(tier: str) -> int:
    """How many interest clusters (distinct searches) ``tier`` allows."""
    return CLUSTER_CAPS.get(tier, CLUSTER_CAPS[Tier.FREE])


def cluster_cap(user: User) -> int:
    """The interest-cluster cap for a user's effective tier."""
    return cluster_cap_for_tier(effective_tier(user))


def cluster_topic_cap_for_tier(tier: str) -> int:
    """How many search terms one cluster may hold under ``tier``."""
    return CLUSTER_TOPIC_CAPS.get(tier, CLUSTER_TOPIC_CAPS[Tier.FREE])


def cluster_topic_cap(user: User) -> int:
    """The per-cluster search-term cap for a user's effective tier."""
    return cluster_topic_cap_for_tier(effective_tier(user))


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


# --------------------------------------------------------------------------- #
# Project caps
#
# A project is a *scored target* — each active project runs the daily retrieve →
# fuse → LLM-fit pipeline, so its cost scales with the active project count, not
# the row count. The cap is therefore a compute budget: it counts **active
# (non-archived)** projects, and archiving frees a slot. Personal caps key on the
# user's effective tier; lab/department caps require the owning org to actually
# carry the team / department feature, so a Free or unsubscribed org gets 0 (no
# project creation) while an individual keeps a small personal allowance even on
# Free. The counting + enforcement live in ``apps.research.limits`` so this module
# stays free of a research import; here we only publish the numbers.
# --------------------------------------------------------------------------- #

PERSONAL_PROJECT_CAPS: dict[str, int] = {
    Tier.FREE: 2,
    Tier.SPORE: 5,
    Tier.LAB: 5,
    Tier.CANOPY: 5,
}
LAB_PROJECT_CAP = 10
DEPARTMENT_PROJECT_CAP = 30


def personal_project_cap(user: User) -> int:
    """How many active personal projects a user's effective tier allows."""
    return PERSONAL_PROJECT_CAPS.get(
        effective_tier(user), PERSONAL_PROJECT_CAPS[Tier.FREE]
    )


def lab_project_cap(lab) -> int:
    """A lab may hold projects only while it carries the team-workspace feature."""
    return LAB_PROJECT_CAP if lab_has_feature(lab, Feature.TEAM_WORKSPACE) else 0


def _department_subscriptions(department) -> QuerySet[Subscription]:
    """Active, unexpired subscriptions scoped to a department."""
    return (
        Subscription.objects.filter(status=Subscription.Status.ACTIVE)
        .filter(_unexpired())
        .filter(scope_department=department)
    )


def department_features(department) -> frozenset[str]:
    """The features a department is entitled to (its subscription's tier ∪ add-ons).

    Returns everything while :func:`enforcing` is off.
    """
    if not enforcing():
        return ALL_FEATURES
    subs = list(_department_subscriptions(department))
    features = set(_FREE)
    for sub in subs:
        features |= TIER_FEATURES.get(sub.tier, _FREE)
    features |= addon_features_for_subscriptions(subs)
    return frozenset(features)


def department_has_feature(department, feature: str) -> bool:
    return feature in department_features(department)


def department_project_cap(department) -> int:
    """A department may hold projects only while it carries department routing."""
    return (
        DEPARTMENT_PROJECT_CAP
        if department_has_feature(department, Feature.DEPARTMENT_ROUTING)
        else 0
    )


def bot_server_addon() -> AddOn | None:
    """The canonical Mylo-server add-on row (seeded by migration), if present."""
    return AddOn.objects.filter(feature=Feature.BOT_SERVER).first()


def _lab_subscriptions(lab) -> QuerySet[Subscription]:
    """Active subscriptions covering a lab: its own plan, or its department's when
    the department head has opted the lab into that plan
    (``Lab.department_plan_included``). Seat billing honours the same flag, so a
    department never pays for a capability in a lab it excluded."""
    query = Q(scope_lab=lab)
    dept_id = getattr(lab, "department_id", None)
    if dept_id and getattr(lab, "department_plan_included", False):
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

    Returns everything while :func:`enforcing` is off — including ``BOT_SERVER``,
    so a lab can have Mylo join its guild without buying the add-on first.
    """
    if not enforcing():
        return ALL_FEATURES
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


def ambient_enabled(tier: str) -> bool:
    """Whether ``tier`` includes the ambient profile: listening, suggestions,
    questions (ambient Plan 06, step 15). Every paid tier does; free does not.

    Not a :class:`Feature`: it must hold whatever ``BILLING_ENFORCE_ENTITLEMENTS``
    says, because it bounds whose conversation is read at all.
    """
    return tier != Tier.FREE

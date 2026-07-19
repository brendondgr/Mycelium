import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Department, Lab
from apps.billing.entitlements import (
    Feature,
    active_seat_count,
    effective_features,
    effective_tier,
    has_feature,
    pi_cap,
    topic_cap,
    within_member_cap,
    within_pi_cap,
    within_topic_cap,
)
from apps.billing.models import AddOn, Seat, Subscription, SubscriptionAddOn, Tier


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(username="researcher", password="pass-123")


@pytest.fixture
def department(db: None) -> Department:
    owner = User.objects.create_user(username="owner", password="pass-123")
    return Department.objects.create(owner=owner, name="Neuroscience")


@pytest.mark.django_db
def test_free_user_has_only_baseline(user: User) -> None:
    assert effective_tier(user) == Tier.FREE
    assert has_feature(user, Feature.BASIC_SEARCH)
    assert has_feature(user, Feature.SEMANTIC_SEARCH)
    assert has_feature(user, Feature.SEMANTIC_RELEVANCE_SCORING)
    # Free is an on-demand product: no LLM verdicts, no scheduled delivery.
    assert not has_feature(user, Feature.LLM_FIT_SCORING)
    assert not has_feature(user, Feature.SCHEDULED_REPORTS)
    assert not has_feature(user, Feature.SHARED_EVIDENCE_GRAPH)


@pytest.mark.django_db
def test_spore_unlocks_intelligence_not_sharing(user: User) -> None:
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)

    assert effective_tier(user) == Tier.SPORE
    assert has_feature(user, Feature.LLM_FIT_SCORING)
    assert has_feature(user, Feature.SCHEDULED_REPORTS)
    assert has_feature(user, Feature.SEMANTIC_SEARCH)
    assert has_feature(user, Feature.GRANT_ALERTS)
    assert has_feature(user, Feature.CONFERENCE_ALERTS)
    assert has_feature(user, Feature.FELLOWSHIP_MATCHING)
    assert has_feature(user, Feature.BOT_DM)
    # Not the team line, not the Mylo-server add-on.
    assert not has_feature(user, Feature.SHARED_EVIDENCE_GRAPH)
    assert not has_feature(user, Feature.BOT_SERVER)


@pytest.mark.django_db
def test_lab_seat_unlocks_shared_features(user: User) -> None:
    lab = Lab.objects.create(name="Forest Lab", slug="forest")
    sub = Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    Seat.objects.create(subscription=sub, member=user, payer_lab=lab)

    assert effective_tier(user) == Tier.LAB
    assert has_feature(user, Feature.SHARED_EVIDENCE_GRAPH)
    assert has_feature(user, Feature.TEAM_WORKSPACE)
    # BOT_SERVER is an add-on, never tier-granted (A4).
    assert not has_feature(user, Feature.BOT_SERVER)
    assert not has_feature(user, Feature.DEPARTMENT_ROUTING)


@pytest.mark.django_db
def test_canopy_seat_unlocks_department_features(
    user: User, department: Department
) -> None:
    sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=department)
    Seat.objects.create(subscription=sub, member=user, payer_department=department)

    assert effective_tier(user) == Tier.CANOPY
    assert has_feature(user, Feature.DEPARTMENT_ROUTING)
    assert has_feature(user, Feature.FLEXIBLE_SEAT_BILLING)
    assert has_feature(user, Feature.CUSTOM_TOPIC_FEEDS)
    assert has_feature(user, Feature.API_ACCESS)


@pytest.mark.django_db
def test_inactive_seat_does_not_grant_features(
    user: User, department: Department
) -> None:
    sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=department)
    Seat.objects.create(
        subscription=sub,
        member=user,
        payer_department=department,
        status=Seat.Status.REVOKED,
    )

    assert effective_tier(user) == Tier.FREE
    assert not has_feature(user, Feature.DEPARTMENT_ROUTING)


@pytest.mark.django_db
def test_past_due_subscription_does_not_cover(user: User) -> None:
    Subscription.objects.create(
        tier=Tier.SPORE, scope_user=user, status=Subscription.Status.PAST_DUE
    )

    assert effective_features(user) == effective_features(
        User.objects.create_user(username="fresh", password="p")
    )
    assert not has_feature(user, Feature.SCHEDULED_REPORTS)


@pytest.mark.django_db
def test_past_due_subscription_resolution(user: User) -> None:
    """D3: a PAST_DUE plan does not cover (hard cutoff). A grace window needs
    dunning, which is deferred to P7; this pins the current resolver behaviour."""
    Subscription.objects.create(
        tier=Tier.LAB, scope_user=user, status=Subscription.Status.PAST_DUE
    )
    assert effective_tier(user) == Tier.FREE
    assert not has_feature(user, Feature.LLM_FIT_SCORING)


@pytest.mark.django_db
def test_active_seat_count(user: User, department: Department) -> None:
    sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=department)
    Seat.objects.create(subscription=sub, member=user, payer_department=department)
    Seat.objects.create(
        subscription=sub,
        member=User.objects.create_user(username="m2", password="p"),
        payer_department=department,
        status=Seat.Status.REVOKED,
    )

    assert active_seat_count(sub) == 1


@pytest.mark.django_db
def test_highest_tier_wins_across_subscriptions(
    user: User, department: Department
) -> None:
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    sub = Subscription.objects.create(tier=Tier.CANOPY, scope_department=department)
    Seat.objects.create(subscription=sub, member=user, payer_department=department)

    assert effective_tier(user) == Tier.CANOPY


@pytest.mark.django_db
def test_addon_grants_bot_server_tier_alone_does_not(user: User) -> None:
    lab = Lab.objects.create(name="Add Lab", slug="add-lab")
    sub = Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    Seat.objects.create(subscription=sub, member=user, payer_lab=lab)

    # Lab tier alone does not grant the Mylo-server capability.
    assert not has_feature(user, Feature.BOT_SERVER)

    # Use the canonical add-on seeded by migration 0003.
    addon = AddOn.objects.get(slug="bot_server")
    assert addon.feature == Feature.BOT_SERVER
    SubscriptionAddOn.objects.create(subscription=sub, add_on=addon)

    # The add-on is the grant (A4): now the lab's members have BOT_SERVER.
    assert has_feature(user, Feature.BOT_SERVER)

    # A canceled add-on stops granting.
    SubscriptionAddOn.objects.update(status=SubscriptionAddOn.Status.CANCELED)
    assert not has_feature(user, Feature.BOT_SERVER)


@pytest.mark.django_db
def test_topic_cap_rejects_over_limit_per_tier(user: User) -> None:
    # Free: cap 6 (3 clusters × 2 terms).
    assert topic_cap(user) == 6
    assert within_topic_cap(user, 6)
    assert not within_topic_cap(user, 7)

    # Spore: cap 10.
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    assert topic_cap(user) == 10
    assert within_topic_cap(user, 10)
    assert not within_topic_cap(user, 11)


def test_pi_caps() -> None:
    assert pi_cap(Tier.SPORE) == 1
    assert pi_cap(Tier.LAB) == 5
    assert pi_cap(Tier.CANOPY) is None

    assert within_pi_cap(5, Tier.LAB)
    assert not within_pi_cap(6, Tier.LAB)
    assert within_pi_cap(100, Tier.CANOPY)


def test_member_caps() -> None:
    assert within_member_cap(15, Tier.LAB)
    assert not within_member_cap(16, Tier.LAB)
    assert within_member_cap(1, Tier.SPORE)
    assert not within_member_cap(2, Tier.SPORE)
    assert within_member_cap(9999, Tier.CANOPY)

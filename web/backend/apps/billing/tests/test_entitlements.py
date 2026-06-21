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
    within_pi_cap,
)
from apps.billing.models import Seat, Subscription, Tier


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
    assert not has_feature(user, Feature.DAILY_DIGESTS)
    assert not has_feature(user, Feature.SHARED_EVIDENCE_GRAPH)


@pytest.mark.django_db
def test_spore_unlocks_personalization_not_sharing(user: User) -> None:
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)

    assert effective_tier(user) == Tier.SPORE
    assert has_feature(user, Feature.DAILY_DIGESTS)
    assert has_feature(user, Feature.SEMANTIC_SEARCH)
    assert not has_feature(user, Feature.SHARED_EVIDENCE_GRAPH)


@pytest.mark.django_db
def test_lab_seat_unlocks_shared_features(user: User) -> None:
    lab = Lab.objects.create(name="Forest Lab", slug="forest")
    sub = Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    Seat.objects.create(subscription=sub, member=user, payer_lab=lab)

    assert effective_tier(user) == Tier.LAB
    assert has_feature(user, Feature.SHARED_EVIDENCE_GRAPH)
    assert has_feature(user, Feature.BOT)
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
    assert not has_feature(user, Feature.DAILY_DIGESTS)


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


def test_pi_caps() -> None:
    assert pi_cap(Tier.SPORE) == 1
    assert pi_cap(Tier.LAB) == 5
    assert pi_cap(Tier.CANOPY) is None

    assert within_pi_cap(5, Tier.LAB)
    assert not within_pi_cap(6, Tier.LAB)
    assert within_pi_cap(100, Tier.CANOPY)

"""Timed subscriptions: an expired plan stops granting entitlements at read-time.

An admin can assign a plan with a duration (``Subscription.expires_at``). Expiry is
enforced by the entitlement read path — no cleanup job — so the moment a grant
lapses the user reverts to Free, while their stored data (topics, saves) is left
untouched.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab
from apps.billing.entitlements import (
    Feature,
    effective_tier,
    has_feature,
    lab_has_feature,
    users_with_feature,
)
from apps.billing.models import Subscription, Tier


@pytest.mark.django_db
def test_future_expiry_still_grants() -> None:
    user = User.objects.create_user(username="future", password="p")
    Subscription.objects.create(
        tier=Tier.SPORE,
        scope_user=user,
        expires_at=timezone.now() + timedelta(days=30),
    )
    assert effective_tier(user) == Tier.SPORE
    assert has_feature(user, Feature.LLM_FIT_SCORING) is True


@pytest.mark.django_db
def test_null_expiry_is_open_ended() -> None:
    user = User.objects.create_user(username="openended", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user, expires_at=None)
    assert effective_tier(user) == Tier.SPORE


@pytest.mark.django_db
def test_past_expiry_reverts_to_free() -> None:
    user = User.objects.create_user(username="lapsed", password="p")
    Subscription.objects.create(
        tier=Tier.SPORE,
        scope_user=user,
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    # Read-time enforcement: the active-but-expired plan is treated as absent.
    assert effective_tier(user) == Tier.FREE
    assert has_feature(user, Feature.LLM_FIT_SCORING) is False


@pytest.mark.django_db
def test_users_with_feature_excludes_expired() -> None:
    live = User.objects.create_user(username="live", password="p")
    lapsed = User.objects.create_user(username="expired", password="p")
    Subscription.objects.create(
        tier=Tier.SPORE,
        scope_user=live,
        expires_at=timezone.now() + timedelta(days=1),
    )
    Subscription.objects.create(
        tier=Tier.SPORE,
        scope_user=lapsed,
        expires_at=timezone.now() - timedelta(days=1),
    )
    entitled = users_with_feature(Feature.FELLOWSHIP_MATCHING)
    assert live.id in entitled
    assert lapsed.id not in entitled


@pytest.mark.django_db
def test_lab_feature_excludes_expired() -> None:
    lab = Lab.objects.create(name="Expiry Lab", slug="expiry-lab")
    sub = Subscription.objects.create(
        tier=Tier.LAB,
        scope_lab=lab,
        expires_at=timezone.now() + timedelta(days=1),
    )
    assert lab_has_feature(lab, Feature.TEAM_WORKSPACE) is True

    sub.expires_at = timezone.now() - timedelta(days=1)
    sub.save(update_fields=["expires_at"])
    assert lab_has_feature(lab, Feature.TEAM_WORKSPACE) is False

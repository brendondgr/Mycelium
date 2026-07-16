"""Request-time enforcement: the RequiresFeature permission (P3)."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory

from apps.billing.entitlements import Feature
from apps.billing.models import Subscription, Tier
from apps.billing.permissions import (
    FeatureRequired,
    minimum_tier_for,
    requires_feature,
)


def _request(user):
    request = APIRequestFactory().get("/x")
    request.user = user
    return request


def test_minimum_tier_for() -> None:
    assert minimum_tier_for(Feature.LLM_FIT_SCORING) == Tier.SPORE
    assert minimum_tier_for(Feature.SHARED_EVIDENCE_GRAPH) == Tier.LAB
    assert minimum_tier_for(Feature.API_ACCESS) == Tier.CANOPY
    # Add-on-only features have no tier that grants them.
    assert minimum_tier_for(Feature.BOT_SERVER) is None


@pytest.mark.django_db
def test_requires_feature_denies_free_user_with_upgrade_hint() -> None:
    user = User.objects.create_user(username="free", password="p")
    perm = requires_feature(Feature.LLM_FIT_SCORING)()

    with pytest.raises(FeatureRequired) as exc:
        perm.has_permission(_request(user), None)

    body = exc.value.detail
    assert body["required_tier"] == Tier.SPORE
    assert body["feature"] == Feature.LLM_FIT_SCORING
    assert "upgrade_url" in body


@pytest.mark.django_db
def test_requires_feature_allows_entitled_user() -> None:
    user = User.objects.create_user(username="spore", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    perm = requires_feature(Feature.LLM_FIT_SCORING)()

    assert perm.has_permission(_request(user), None) is True


@pytest.mark.django_db
def test_requires_feature_denies_anonymous() -> None:
    from django.contrib.auth.models import AnonymousUser

    perm = requires_feature(Feature.LLM_FIT_SCORING)()
    assert perm.has_permission(_request(AnonymousUser()), None) is False

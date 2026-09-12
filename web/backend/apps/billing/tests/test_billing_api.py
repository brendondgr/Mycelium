"""The billing read surface: GET /api/billing/me/."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import WatchPreference
from apps.billing.models import Subscription, Tier


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_me_requires_auth(client: APIClient) -> None:
    assert client.get("/api/billing/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_free_me_endpoint(client: APIClient) -> None:
    user = User.objects.create_user(username="free", password="p")
    client.force_authenticate(user)

    resp = client.get("/api/billing/me/")
    assert resp.status_code == 200
    body = resp.data
    assert body["tier"] == "free"
    assert body["topic_cap"] == 6
    assert body["cluster_cap"] == 3
    assert body["cluster_topic_cap"] == 2
    assert body["topics_used"] == 0
    assert "llm_fit_scoring" not in body["features"]
    assert "semantic_search" in body["features"]
    assert body["addons"] == []


@pytest.mark.django_db
def test_spore_me_endpoint_reports_intelligence_and_topics(client: APIClient) -> None:
    user = User.objects.create_user(username="spore", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    WatchPreference.objects.create(user=user, topics=["neuro", "vision"])
    client.force_authenticate(user)

    body = client.get("/api/billing/me/").data
    assert body["tier"] == "spore"
    assert body["topic_cap"] == 20
    assert body["topics_used"] == 2
    assert "llm_fit_scoring" in body["features"]

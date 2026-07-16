"""Per-tier watch-topic caps + the no-data-loss downgrade edge (P3)."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import WatchPreference
from apps.billing.entitlements import effective_watch_topics, topics_over_cap
from apps.billing.models import Subscription, Tier

URL = "/api/auth/watch/me/"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_free_user_rejected_over_three_topics(client: APIClient) -> None:
    user = User.objects.create_user(username="free", password="p")
    client.force_authenticate(user)

    ok = client.patch(URL, {"topics": ["a", "b", "c"]}, format="json")
    assert ok.status_code == 200

    over = client.patch(URL, {"topics": ["a", "b", "c", "d"]}, format="json")
    assert over.status_code == 400
    assert "topics" in over.data
    # Not silently truncated — the prior 3 stand.
    assert WatchPreference.objects.get(user=user).topics == ["a", "b", "c"]


@pytest.mark.django_db
def test_spore_user_cap_is_ten(client: APIClient) -> None:
    user = User.objects.create_user(username="spore", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    client.force_authenticate(user)

    ten = [f"t{n}" for n in range(10)]
    assert client.patch(URL, {"topics": ten}, format="json").status_code == 200
    eleven = [f"t{n}" for n in range(11)]
    assert client.patch(URL, {"topics": eleven}, format="json").status_code == 400


@pytest.mark.django_db
def test_downgrade_does_not_delete_topics_over_cap(client: APIClient) -> None:
    user = User.objects.create_user(username="lapsed", password="p")
    sub = Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    client.force_authenticate(user)

    ten = [f"t{n}" for n in range(10)]
    assert client.patch(URL, {"topics": ten}, format="json").status_code == 200

    # The plan lapses to Free (no data destruction on the billing event).
    sub.status = Subscription.Status.CANCELED
    sub.save(update_fields=["status"])

    # Stored topics are untouched...
    assert WatchPreference.objects.get(user=user).topics == ten
    # ...but only the first 3 are honoured, and the overflow is reported.
    assert effective_watch_topics(user) == ten[:3]
    assert topics_over_cap(user) is True

    body = client.get(URL).data
    assert body["topic_cap"] == 3
    assert body["topics_over_cap"] is True
    assert body["topics"] == ten  # never deleted

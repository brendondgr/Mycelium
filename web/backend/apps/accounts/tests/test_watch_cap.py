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
def test_free_user_rejected_over_six_topics(client: APIClient) -> None:
    # Free = 3 clusters × 2 terms = 6 flat watch topics.
    user = User.objects.create_user(username="free", password="p")
    client.force_authenticate(user)

    six = ["a", "b", "c", "d", "e", "f"]
    ok = client.patch(URL, {"topics": six}, format="json")
    assert ok.status_code == 200

    over = client.patch(URL, {"topics": [*six, "g"]}, format="json")
    assert over.status_code == 400
    assert "topics" in over.data
    # Not silently truncated — the prior 6 stand.
    assert WatchPreference.objects.get(user=user).topics == six


@pytest.mark.django_db
def test_spore_user_cap_is_twenty(client: APIClient) -> None:
    user = User.objects.create_user(username="spore", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    client.force_authenticate(user)

    at_cap = [f"t{n}" for n in range(20)]
    assert client.patch(URL, {"topics": at_cap}, format="json").status_code == 200
    over_cap = [f"t{n}" for n in range(21)]
    assert client.patch(URL, {"topics": over_cap}, format="json").status_code == 400


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
    # ...but only the first 6 (the Free cap) are honoured, overflow is reported.
    assert effective_watch_topics(user) == ten[:6]
    assert topics_over_cap(user) is True

    body = client.get(URL).data
    assert body["topic_cap"] == 6
    assert body["topics_over_cap"] is True
    assert body["topics"] == ten  # never deleted

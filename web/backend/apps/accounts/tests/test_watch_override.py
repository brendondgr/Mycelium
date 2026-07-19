"""Per-user watch-topic override — the admin-granted quota that wins over the tier.

An operator can widen or narrow how many subjects one user may monitor by setting
``Profile.watch_topic_limit``. It is read through the single entitlement path
(``entitlements.topic_cap``), so the watch-save endpoint honours it too. A null
override falls back to the plan's per-tier cap (whatever that is), so this test
never hardcodes the Free default and survives a tier-cap change.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.billing.entitlements import (
    effective_tier,
    topic_cap,
    topic_cap_for_tier,
)

URL = "/api/auth/watch/me/"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_no_override_uses_tier_cap() -> None:
    user = User.objects.create_user(username="default", password="p")
    assert user.profile.watch_topic_limit is None
    assert topic_cap(user) == topic_cap_for_tier(effective_tier(user))


@pytest.mark.django_db
def test_override_widens_cap(client: APIClient) -> None:
    user = User.objects.create_user(username="widened", password="p")
    profile = user.profile
    profile.watch_topic_limit = 20
    profile.save(update_fields=["watch_topic_limit"])
    assert topic_cap(user) == 20

    client.force_authenticate(user)
    twenty = [f"t{n}" for n in range(20)]
    assert client.patch(URL, {"topics": twenty}, format="json").status_code == 200
    twenty_one = [f"t{n}" for n in range(21)]
    assert client.patch(URL, {"topics": twenty_one}, format="json").status_code == 400


@pytest.mark.django_db
def test_override_narrows_cap(client: APIClient) -> None:
    user = User.objects.create_user(username="narrowed", password="p")
    profile = user.profile
    profile.watch_topic_limit = 1
    profile.save(update_fields=["watch_topic_limit"])
    assert topic_cap(user) == 1

    client.force_authenticate(user)
    assert client.patch(URL, {"topics": ["only"]}, format="json").status_code == 200
    assert (
        client.patch(URL, {"topics": ["one", "two"]}, format="json").status_code
        == 400
    )


@pytest.mark.django_db
def test_clearing_override_restores_tier_cap() -> None:
    user = User.objects.create_user(username="restored", password="p")
    profile = user.profile
    profile.watch_topic_limit = 99
    profile.save(update_fields=["watch_topic_limit"])
    assert topic_cap(user) == 99

    profile.watch_topic_limit = None
    profile.save(update_fields=["watch_topic_limit"])
    assert topic_cap(user) == topic_cap_for_tier(effective_tier(user))

"""Admin dashboard API — the permission gate + the user/subscription/watch flows.

This is the checkpoint the plan requires *before* any UI: prove that only staff or
superusers reach the endpoints, and that an assignment actually flows through the
single entitlement read path (tier + duration -> effective_tier/expiry; watch limit
-> topic_cap).
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuditEvent
from apps.billing.entitlements import effective_tier, topic_cap
from apps.billing.models import Subscription, Tier

LIST_URL = "/api/admin/users/"


def detail_url(user: User) -> str:
    return f"/api/admin/users/{user.pk}/"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff() -> User:
    user = User.objects.create_user(username="staffer", password="p")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def superuser() -> User:
    return User.objects.create_superuser(username="root", password="p")


@pytest.fixture
def member() -> User:
    return User.objects.create_user(username="regular", password="p")


# -- permission gate -----------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_is_blocked(client: APIClient, member: User) -> None:
    assert client.get(LIST_URL).status_code in (401, 403)
    assert client.get(detail_url(member)).status_code in (401, 403)
    assert client.patch(
        detail_url(member), {"tier": Tier.SPORE}, format="json"
    ).status_code in (401, 403)


@pytest.mark.django_db
def test_regular_user_forbidden(client: APIClient, member: User) -> None:
    client.force_authenticate(member)
    assert client.get(LIST_URL).status_code == 403
    assert client.get(detail_url(member)).status_code == 403
    assert (
        client.patch(
            detail_url(member), {"tier": Tier.SPORE}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_staff_allowed(client: APIClient, staff: User) -> None:
    client.force_authenticate(staff)
    assert client.get(LIST_URL).status_code == 200
    assert client.get(detail_url(staff)).status_code == 200


@pytest.mark.django_db
def test_superuser_allowed(client: APIClient, superuser: User) -> None:
    client.force_authenticate(superuser)
    assert client.get(LIST_URL).status_code == 200
    assert client.get(detail_url(superuser)).status_code == 200


# -- listing: pagination + search ----------------------------------------------


@pytest.mark.django_db
def test_list_is_paginated(client: APIClient, staff: User) -> None:
    for n in range(30):
        User.objects.create_user(username=f"u{n}", password="p")
    client.force_authenticate(staff)

    body = client.get(LIST_URL).data
    assert body["count"] == 31  # 30 + the staff user
    assert len(body["results"]) == 25  # default page size
    assert body["next"] is not None

    page2 = client.get(LIST_URL, {"page": 2}).data
    assert len(page2["results"]) == 6

    smaller = client.get(LIST_URL, {"page_size": 10}).data
    assert len(smaller["results"]) == 10


@pytest.mark.django_db
def test_list_search(client: APIClient, staff: User) -> None:
    User.objects.create_user(username="marie.curie", email="mc@lab.test", password="p")
    User.objects.create_user(username="alan.turing", email="at@lab.test", password="p")
    client.force_authenticate(staff)

    body = client.get(LIST_URL, {"q": "curie"}).data
    usernames = [row["username"] for row in body["results"]]
    assert usernames == ["marie.curie"]


@pytest.mark.django_db
def test_row_shape(client: APIClient, staff: User, member: User) -> None:
    client.force_authenticate(staff)
    body = client.get(LIST_URL, {"q": "regular"}).data
    row = body["results"][0]
    for key in (
        "id", "username", "email", "effective_tier", "subscription",
        "watch_topics_used", "watch_topic_cap", "watch_topic_limit",
    ):
        assert key in row


# -- writes: subscription tier + duration --------------------------------------


@pytest.mark.django_db
def test_assign_tier_with_duration(
    client: APIClient, superuser: User, member: User
) -> None:
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(member),
        {"tier": Tier.SPORE, "duration_days": 30},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["subscription"]["tier"] == Tier.SPORE

    sub = Subscription.objects.get(scope_user=member)
    assert sub.tier == Tier.SPORE
    expected = timezone.now() + timedelta(days=30)
    assert sub.expires_at is not None
    assert abs((sub.expires_at - expected).total_seconds()) < 60
    # Flows through the single entitlement read path.
    assert effective_tier(member) == Tier.SPORE
    assert AuditEvent.objects.filter(action="admin.subscription.assign").exists()


@pytest.mark.django_db
def test_clear_duration_sets_open_ended(
    client: APIClient, superuser: User, member: User
) -> None:
    Subscription.objects.create(
        tier=Tier.SPORE,
        scope_user=member,
        expires_at=timezone.now() + timedelta(days=5),
    )
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(member), {"duration_days": None}, format="json"
    )
    assert resp.status_code == 200
    member.refresh_from_db()
    sub = Subscription.objects.get(scope_user=member)
    assert sub.expires_at is None
    assert effective_tier(member) == Tier.SPORE  # still granted, now open-ended


@pytest.mark.django_db
def test_expired_grant_reverts_via_read_path(
    client: APIClient, superuser: User, member: User
) -> None:
    client.force_authenticate(superuser)
    past = timezone.now() - timedelta(days=1)
    resp = client.patch(
        detail_url(member),
        {"tier": Tier.LAB, "expires_at": past.isoformat()},
        format="json",
    )
    assert resp.status_code == 200
    # Persisted as LAB but already expired -> resolves to Free.
    assert Subscription.objects.get(scope_user=member).tier == Tier.LAB
    assert effective_tier(member) == Tier.FREE


# -- writes: watch topic override ----------------------------------------------


@pytest.mark.django_db
def test_set_and_clear_watch_limit(
    client: APIClient, superuser: User, member: User
) -> None:
    client.force_authenticate(superuser)

    resp = client.patch(
        detail_url(member), {"watch_topic_limit": 25}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["watch_topic_limit"] == 25
    assert resp.data["watch_topic_cap"] == 25
    member.refresh_from_db()
    assert member.profile.watch_topic_limit == 25
    assert topic_cap(member) == 25

    cleared = client.patch(
        detail_url(member), {"watch_topic_limit": None}, format="json"
    )
    assert cleared.status_code == 200
    member.refresh_from_db()
    assert member.profile.watch_topic_limit is None


# -- write validation ----------------------------------------------------------


@pytest.mark.django_db
def test_empty_patch_rejected(
    client: APIClient, superuser: User, member: User
) -> None:
    client.force_authenticate(superuser)
    assert client.patch(detail_url(member), {}, format="json").status_code == 400


@pytest.mark.django_db
def test_duration_and_expires_together_rejected(
    client: APIClient, superuser: User, member: User
) -> None:
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(member),
        {
            "duration_days": 30,
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_watch_limit_over_max_rejected(
    client: APIClient, superuser: User, member: User
) -> None:
    client.force_authenticate(superuser)
    resp = client.patch(
        detail_url(member), {"watch_topic_limit": 9999}, format="json"
    )
    assert resp.status_code == 400

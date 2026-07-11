"""The watch endpoint: what Mylo keeps an eye on, own-only read/update."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

URL = "/api/auth/watch/me/"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(username="u", password="p")


@pytest.mark.django_db
def test_get_creates_defaults(client, user) -> None:
    client.force_authenticate(user)
    resp = client.get(URL)
    assert resp.status_code == 200
    assert resp.data["cadence"] == "weekly"
    assert resp.data["topics"] == []
    assert resp.data["categories"] == []


@pytest.mark.django_db
def test_update_persists(client, user) -> None:
    client.force_authenticate(user)
    resp = client.patch(
        URL,
        {
            "topics": ["post-quantum cryptography", "intrusion detection"],
            "categories": ["papers", "grants"],
            "cadence": "daily",
        },
        format="json",
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    watch = user.watch
    assert watch.cadence == "daily"
    assert "post-quantum cryptography" in watch.topics
    assert "grants" in watch.categories


@pytest.mark.django_db
def test_dedupes_and_trims_topics(client, user) -> None:
    client.force_authenticate(user)
    resp = client.patch(
        URL,
        {"topics": ["Genomics", "genomics", "  Genomics  ", "RNA"]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["topics"] == ["Genomics", "RNA"]


@pytest.mark.django_db
def test_rejects_non_list_topics(client, user) -> None:
    client.force_authenticate(user)
    resp = client.patch(URL, {"topics": "not-a-list"}, format="json")
    assert resp.status_code == 400
    assert "topics" in resp.data


@pytest.mark.django_db
def test_rejects_unknown_cadence(client, user) -> None:
    client.force_authenticate(user)
    resp = client.patch(URL, {"cadence": "hourly"}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_caps_item_count(client, user) -> None:
    client.force_authenticate(user)
    resp = client.patch(
        URL, {"topics": [f"topic-{n}" for n in range(51)]}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_requires_authentication(client) -> None:
    resp = client.get(URL)
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_watch_is_per_user(client) -> None:
    alice = User.objects.create_user(username="alice", password="p")
    bob = User.objects.create_user(username="bob", password="p")

    client.force_authenticate(alice)
    client.patch(URL, {"topics": ["alice-topic"]}, format="json")

    client.force_authenticate(bob)
    resp = client.get(URL)
    # Bob sees his own freshly-created defaults, never Alice's topics.
    assert resp.data["topics"] == []

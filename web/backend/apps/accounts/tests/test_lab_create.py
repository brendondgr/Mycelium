"""Creating a lab after the account already exists (POST /api/auth/labs/)."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import LabMembership, LabProfile
from apps.billing.models import Seat, Subscription, Tier

from .conftest import verified


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_create_lab_requires_authentication(client: APIClient) -> None:
    assert client.post("/api/auth/labs/", {"name": "New Lab"}).status_code in (401, 403)


@pytest.mark.django_db
def test_create_lab_makes_caller_pi_owner(client: APIClient) -> None:
    user = verified(User.objects.create_user(username="u", password="p"))
    client.force_authenticate(user)

    resp = client.post("/api/auth/labs/", {"name": "Ocean Lab"}, format="json")

    assert resp.status_code == 201
    assert resp.data["name"] == "Ocean Lab"
    assert resp.data["role"] == "owner"
    assert resp.data["is_lead"] is True
    slug = resp.data["slug"]

    membership = LabMembership.objects.get(user=user, lab__slug=slug)
    assert membership.role == LabMembership.Role.OWNER
    assert membership.is_lead is True
    # The interest profile + billing rows are provisioned like a signup lab.
    assert LabProfile.objects.filter(lab__slug=slug).exists()
    sub = Subscription.objects.get(scope_lab__slug=slug)
    assert sub.tier == Tier.LAB
    assert Seat.objects.filter(subscription=sub, member=user).exists()


@pytest.mark.django_db
def test_created_lab_appears_in_my_labs(client: APIClient) -> None:
    user = verified(User.objects.create_user(username="u", password="p"))
    client.force_authenticate(user)
    slug = client.post("/api/auth/labs/", {"name": "Ocean Lab"}, format="json").data[
        "slug"
    ]

    listing = client.get("/api/auth/labs/")
    assert any(row["slug"] == slug for row in listing.data)


@pytest.mark.django_db
def test_create_lab_rejects_blank_name(client: APIClient) -> None:
    user = verified(User.objects.create_user(username="u", password="p"))
    client.force_authenticate(user)
    resp = client.post("/api/auth/labs/", {"name": "   "}, format="json")
    assert resp.status_code == 400
    assert "name" in resp.data

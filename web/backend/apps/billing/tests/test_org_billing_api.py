"""Lab & department billing state + activation endpoints, and account visibility."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts.models import LabMembership
from apps.billing.entitlements import Tier, effective_tier
from apps.billing.services import create_lab_workspace, provision_workspace


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _user(name: str) -> User:
    return User.objects.create_user(username=name, password="p")


@pytest.mark.django_db
def test_lab_billing_state_and_activation(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    member = _user("student")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(founder)

    # Inactive to start (L1).
    state = client.get(f"/api/labs/{lab.slug}/billing/")
    assert state.status_code == 200
    assert state.data["is_active"] is False
    assert state.data["tier"] == "lab"
    assert state.data["can_manage"] is True

    # Activate → seats both members, priced at $12.50 each.
    resp = client.post(f"/api/labs/{lab.slug}/billing/activate/")
    assert resp.status_code == 200
    assert resp.data["is_active"] is True
    assert resp.data["seat_count"] == 2
    assert resp.data["seat_price_cents"] == 1250
    assert resp.data["recurring_monthly_cents"] == 2500
    assert resp.data["current_period_end"] is not None
    assert effective_tier(member) == Tier.LAB


@pytest.mark.django_db
def test_non_manager_cannot_activate_lab(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    member = _user("student")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    client.force_authenticate(member)

    resp = client.post(f"/api/labs/{lab.slug}/billing/activate/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_department_billing_activation_seats_effective(client: APIClient) -> None:
    head = _user("head")
    dept = provision_workspace(head, "department", org_name="Systems").department
    pi = _user("pi")
    lab = create_lab_workspace(pi, "Sub Lab").lab
    lab.department = dept
    lab.save(update_fields=["department"])
    client.force_authenticate(head)

    resp = client.post(f"/api/departments/{dept.id}/billing/activate/")

    assert resp.status_code == 200
    assert resp.data["is_active"] is True
    assert resp.data["tier"] == "canopy"
    assert resp.data["seat_price_cents"] == 2000
    # The head and the lab-under-dept PI are both entitled (rule 2).
    assert effective_tier(head) == Tier.CANOPY
    assert effective_tier(pi) == Tier.CANOPY


@pytest.mark.django_db
def test_billing_me_lists_active_plans(client: APIClient) -> None:
    founder = _user("pi")
    lab = create_lab_workspace(founder, "Rivera Lab").lab
    from apps.billing.services import activate_lab_subscription

    activate_lab_subscription(lab)
    client.force_authenticate(founder)

    body = client.get("/api/billing/me/").data
    lab_plans = [p for p in body["plans"] if p["scope_type"] == "lab"]
    assert len(lab_plans) == 1
    plan = lab_plans[0]
    assert plan["tier"] == "lab"
    assert plan["seat_status"] == "active"
    assert plan["payer_type"] == "lab"
    assert plan["scope_name"] == "Rivera Lab"

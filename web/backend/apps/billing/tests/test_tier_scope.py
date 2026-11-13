"""A tier belongs to a scope — Mycelium Lab is bought on a lab, never on a person.

The rule (``apps.billing.tiers``) exists because a Lab plan is priced *per member*: on a
lab there is a roster to count, on a personal account there is nobody but the buyer. So
every point that *grants* a plan refuses an out-of-scope tier, and the lab's own billing
endpoint is the surface that both prices and activates it.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.test import APIClient

from apps.accounts.models import Department, Lab, LabMembership
from apps.billing.models import Seat, Subscription, Tier
from apps.billing.services import (
    activate_lab_subscription,
    provision_workspace,
)
from apps.billing.tiers import (
    TierScopeError,
    tier_allowed_for_scope,
    validate_tier_for_scope,
)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _lab_with_members(count: int) -> tuple[Lab, list[User]]:
    """A lab with an INACTIVE Lab plan and ``count`` members (the first is the PI)."""
    lab = Lab.objects.create(name="Fungal Ecology", slug="fungal-ecology")
    Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.INACTIVE
    )
    members = []
    for n in range(count):
        user = User.objects.create_user(username=f"member{n}", password="p")
        LabMembership.objects.create(
            user=user,
            lab=lab,
            role=LabMembership.Role.OWNER if n == 0 else LabMembership.Role.MEMBER,
            is_lead=(n == 0),
        )
        members.append(user)
    return lab, members


# -- the rule itself -----------------------------------------------------------


def test_personal_scope_sells_only_personal_tiers() -> None:
    assert tier_allowed_for_scope("user", Tier.FREE)
    assert tier_allowed_for_scope("user", Tier.SPORE)
    assert not tier_allowed_for_scope("user", Tier.LAB)
    assert not tier_allowed_for_scope("user", Tier.CANOPY)


def test_lab_scope_sells_only_team_tiers() -> None:
    assert tier_allowed_for_scope("lab", Tier.LAB)
    assert tier_allowed_for_scope("lab", Tier.CANOPY)
    assert not tier_allowed_for_scope("lab", Tier.FREE)
    assert not tier_allowed_for_scope("lab", Tier.SPORE)


def test_department_scope_is_canopy_only() -> None:
    assert tier_allowed_for_scope("department", Tier.CANOPY)
    assert not tier_allowed_for_scope("department", Tier.LAB)


def test_personal_lab_tier_error_names_where_to_buy_it() -> None:
    """The usual cause is aiming a team plan at one person; say what to do instead."""
    with pytest.raises(TierScopeError) as exc:
        validate_tier_for_scope("user", Tier.LAB)
    assert "lab" in str(exc.value).lower()


# -- enforced where plans are granted ------------------------------------------


@pytest.mark.django_db
def test_model_clean_rejects_a_personal_lab_plan() -> None:
    user = User.objects.create_user(username="solo", password="p")
    sub = Subscription(tier=Tier.LAB, scope_user=user)
    with pytest.raises(DjangoValidationError) as exc:
        sub.full_clean(exclude=["id"])
    assert "tier" in exc.value.message_dict


@pytest.mark.django_db
def test_provisioning_refuses_a_personal_lab_tier() -> None:
    user = User.objects.create_user(username="solo", password="p")
    with pytest.raises(TierScopeError):
        provision_workspace(user, "personal", personal_tier=Tier.LAB)
    assert not Subscription.objects.filter(scope_user=user).exists()


@pytest.mark.django_db
def test_signup_provisioning_still_yields_a_free_personal_plan() -> None:
    user = User.objects.create_user(username="solo", password="p")
    result = provision_workspace(user, "personal")
    assert result.subscription.tier == Tier.FREE


@pytest.mark.django_db
def test_activation_refuses_a_lab_plan_on_a_personal_tier() -> None:
    """A mis-tiered lab plan cannot be switched on, however it got there."""
    lab, _ = _lab_with_members(1)
    sub = Subscription.objects.get(scope_lab=lab)
    Subscription.objects.filter(pk=sub.pk).update(tier=Tier.SPORE)  # bypass validation
    with pytest.raises(TierScopeError):
        activate_lab_subscription(lab)
    assert Subscription.objects.get(scope_lab=lab).activated_at is None


# -- the admin dashboard honours it --------------------------------------------


@pytest.mark.django_db
def test_admin_cannot_grant_a_person_a_lab_plan(client: APIClient) -> None:
    admin = User.objects.create_superuser(username="root", password="p")
    member = User.objects.create_user(username="regular", password="p")
    client.force_authenticate(admin)

    resp = client.patch(
        f"/api/admin/users/{member.pk}/", {"tier": Tier.LAB}, format="json"
    )
    assert resp.status_code == 400
    assert "tier" in resp.data
    assert not Subscription.objects.filter(
        scope_user=member, tier=Tier.LAB
    ).exists()

    # The personal paid tier still goes through.
    ok = client.patch(
        f"/api/admin/users/{member.pk}/", {"tier": Tier.SPORE}, format="json"
    )
    assert ok.status_code == 200


@pytest.mark.django_db
def test_admin_cannot_put_a_lab_on_a_personal_tier(client: APIClient) -> None:
    admin = User.objects.create_superuser(username="root", password="p")
    lab, _ = _lab_with_members(1)
    client.force_authenticate(admin)

    resp = client.patch(
        f"/api/admin/labs/{lab.slug}/", {"tier": Tier.SPORE}, format="json"
    )
    assert resp.status_code == 400
    assert Subscription.objects.get(scope_lab=lab).tier == Tier.LAB


# -- the lab page is the purchase surface --------------------------------------


@pytest.mark.django_db
def test_lab_billing_quotes_the_roster_before_activation(client: APIClient) -> None:
    """The whole point of buying on the lab: the price reflects who is actually in it.

    Before activation every seat is still PENDING, so ``seat_count`` is 0 — the quote
    has to come from the roster or a PI would be shown $0 for a five-person lab.
    """
    lab, members = _lab_with_members(5)
    client.force_authenticate(members[0])

    body = client.get(f"/api/labs/{lab.slug}/billing/").data
    assert body["is_active"] is False
    assert body["seat_count"] == 0
    assert body["member_count"] == 5
    assert body["activation_monthly_cents"] == 5 * body["seat_price_cents"]
    assert body["can_manage"] is True


@pytest.mark.django_db
def test_activating_on_the_lab_seats_everyone_and_bills_the_roster(
    client: APIClient,
) -> None:
    lab, members = _lab_with_members(5)
    # With billing on, activation needs a staff account (who manages the lab).
    members[0].is_staff = True
    members[0].save(update_fields=["is_staff"])
    client.force_authenticate(members[0])

    resp = client.post(f"/api/labs/{lab.slug}/billing/activate/")
    assert resp.status_code == 200
    assert resp.data["is_active"] is True
    assert resp.data["seat_count"] == 5
    assert resp.data["recurring_monthly_cents"] == 5 * resp.data["seat_price_cents"]

    sub = Subscription.objects.get(scope_lab=lab)
    assert (
        Seat.objects.filter(subscription=sub, status=Seat.Status.ACTIVE).count() == 5
    )
    # Everyone in the lab, PI included, is covered by the one plan.
    for member in members:
        assert (
            Subscription.objects.filter(
                seats__member=member,
                seats__status=Seat.Status.ACTIVE,
                scope_lab=lab,
            ).exists()
        )


@pytest.mark.django_db
def test_a_non_manager_cannot_activate_the_lab_plan(client: APIClient) -> None:
    lab, members = _lab_with_members(3)
    client.force_authenticate(members[2])
    resp = client.post(f"/api/labs/{lab.slug}/billing/activate/")
    assert resp.status_code == 403
    assert Subscription.objects.get(scope_lab=lab).activated_at is None


@pytest.mark.django_db
def test_department_plan_quotes_its_plan_membership(client: APIClient) -> None:
    head = User.objects.create_user(username="head", password="p")
    result = provision_workspace(head, "department", org_name="Biology")
    department = result.department
    assert Department.objects.filter(pk=department.pk).exists()

    client.force_authenticate(head)
    body = client.get(f"/api/departments/{department.id}/billing/").data
    assert body["member_count"] == 1
    assert body["activation_monthly_cents"] == body["seat_price_cents"]

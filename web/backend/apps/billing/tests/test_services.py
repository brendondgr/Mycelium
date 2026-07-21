import pytest
from django.contrib.auth.models import User

from apps.accounts.models import (
    Department,
    DeptMembership,
    Lab,
    LabMembership,
)
from apps.billing.models import Seat, Subscription, Tier
from apps.billing.services import ProvisionResult, provision_workspace


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(username="founder", password="pass-123")


@pytest.mark.django_db
def test_provision_personal_creates_self_paid_seat_and_no_org(user: User) -> None:
    result = provision_workspace(user, "personal")

    assert isinstance(result, ProvisionResult)
    assert result.lab is None
    assert result.department is None

    assert result.subscription.tier == Tier.FREE
    assert result.subscription.scope_user == user
    assert result.subscription.scope_type == "user"

    assert result.seat.member == user
    assert result.seat.payer_user == user
    assert result.seat.payer_type == "self"

    # No organization rows for a personal account.
    assert Lab.objects.count() == 0
    assert Department.objects.count() == 0
    assert Subscription.objects.count() == 1
    assert Seat.objects.count() == 1


@pytest.mark.django_db
def test_provision_personal_respects_personal_tier(user: User) -> None:
    result = provision_workspace(user, "personal", personal_tier=Tier.SPORE)
    assert result.subscription.tier == Tier.SPORE


@pytest.mark.django_db
def test_provision_lab_makes_founder_owner_pi(user: User) -> None:
    result = provision_workspace(user, "lab", org_name="Rivera Lab")

    assert result.lab is not None
    assert result.lab.name == "Rivera Lab"
    assert result.lab.slug == "rivera-lab"

    membership = LabMembership.objects.get(user=user, lab=result.lab)
    assert membership.role == LabMembership.Role.OWNER
    assert membership.is_lead is True

    # Labs start INACTIVE (L1): the plan + founder seat are provisioned but dormant.
    assert result.subscription.tier == Tier.LAB
    assert result.subscription.scope_lab == result.lab
    assert result.subscription.status == Subscription.Status.INACTIVE
    assert result.seat.member == user
    assert result.seat.payer_lab == result.lab
    assert result.seat.payer_type == "lab"
    assert result.seat.status == Seat.Status.PENDING

    assert Department.objects.count() == 0


@pytest.mark.django_db
def test_provision_department_makes_founder_owner(user: User) -> None:
    result = provision_workspace(
        user, "department", org_name="Molecular Systems", institution="Northgate"
    )

    assert result.department is not None
    assert result.department.owner == user
    assert result.department.name == "Molecular Systems"
    assert result.department.institution == "Northgate"

    membership = DeptMembership.objects.get(user=user, department=result.department)
    assert membership.role == DeptMembership.Role.OWNER

    # Departments start INACTIVE (L1): inactive until the head activates the plan.
    assert result.subscription.tier == Tier.CANOPY
    assert result.subscription.scope_department == result.department
    assert result.subscription.status == Subscription.Status.INACTIVE
    assert result.seat.member == user
    assert result.seat.payer_department == result.department
    assert result.seat.payer_type == "department"
    assert result.seat.status == Seat.Status.PENDING

    assert Lab.objects.count() == 0


@pytest.mark.django_db
def test_lab_slug_unique_when_names_collide(user: User) -> None:
    other = User.objects.create_user(username="founder2", password="pass-123")

    first = provision_workspace(user, "lab", org_name="Forest Lab")
    second = provision_workspace(other, "lab", org_name="Forest Lab")

    assert first.lab is not None and second.lab is not None
    assert first.lab.slug != second.lab.slug
    assert first.lab.slug == "forest-lab"
    assert second.lab.slug == "forest-lab-2"


@pytest.mark.django_db
def test_unknown_account_type_raises(user: User) -> None:
    with pytest.raises(ValueError, match="Unknown account_type"):
        provision_workspace(user, "enterprise")

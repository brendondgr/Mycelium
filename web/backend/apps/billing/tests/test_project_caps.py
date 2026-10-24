"""Per-plan project caps published by billing.entitlements."""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Department, Lab
from apps.billing.entitlements import (
    DEPARTMENT_PROJECT_CAP,
    LAB_PROJECT_CAP,
    department_project_cap,
    lab_project_cap,
    personal_project_cap,
)
from apps.billing.models import Subscription, Tier


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(username="researcher", password="pass-123")


@pytest.mark.django_db
def test_personal_cap_by_tier(user: User) -> None:
    assert personal_project_cap(user) == 2  # Free
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    assert personal_project_cap(user) == 5


@pytest.mark.django_db
def test_lab_cap_requires_team_workspace() -> None:
    lab = Lab.objects.create(name="Forest Lab", slug="forest")
    # No subscription — a Free lab cannot hold projects.
    assert lab_project_cap(lab) == 0
    Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    assert lab_project_cap(lab) == LAB_PROJECT_CAP == 10


@pytest.mark.django_db
def test_department_cap_requires_department_routing() -> None:
    owner = User.objects.create_user(username="owner", password="p")
    dept = Department.objects.create(owner=owner, name="Neuroscience")
    assert department_project_cap(dept) == 0
    Subscription.objects.create(tier=Tier.CANOPY, scope_department=dept)
    assert department_project_cap(dept) == DEPARTMENT_PROJECT_CAP == 30


@pytest.mark.django_db
def test_lab_tier_below_lab_does_not_grant_projects() -> None:
    """A Spore-scoped lab (no team workspace) still gets a 0 project cap."""
    lab = Lab.objects.create(name="Small Lab", slug="small")
    Subscription.objects.create(tier=Tier.SPORE, scope_lab=lab)
    assert lab_project_cap(lab) == 0


@pytest.mark.django_db
def test_expired_subscription_drops_lab_cap_to_zero() -> None:
    from django.utils import timezone

    lab = Lab.objects.create(name="Lapsed Lab", slug="lapsed")
    Subscription.objects.create(
        tier=Tier.LAB,
        scope_lab=lab,
        expires_at=timezone.now() - timezone.timedelta(days=1),
    )
    assert lab_project_cap(lab) == 0

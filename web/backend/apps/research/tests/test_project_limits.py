"""Counting + cap headroom for project scopes (apps.research.limits)."""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab
from apps.billing.models import Subscription, Tier
from apps.research.limits import in_cap_ids, lab_scope_cap, personal_scope_cap
from apps.research.models import Project


@pytest.mark.django_db
def test_personal_scope_cap_counts_only_active() -> None:
    user = User.objects.create_user(username="solo", password="p")
    Project.objects.create(scope_user=user, name="A")
    Project.objects.create(scope_user=user, name="B")
    archived = Project.objects.create(scope_user=user, name="C", is_archived=True)

    cap = personal_scope_cap(user)
    assert cap.cap == 2  # Free
    assert cap.active == 2  # archived C does not count
    assert not cap.has_headroom  # at the Free limit
    assert archived.is_archived


@pytest.mark.django_db
def test_archiving_frees_a_slot() -> None:
    user = User.objects.create_user(username="solo", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    for i in range(5):
        Project.objects.create(scope_user=user, name=f"P{i}")
    assert not personal_scope_cap(user).has_headroom  # 5/5

    Project.objects.filter(name="P0").update(is_archived=True)
    cap = personal_scope_cap(user)
    assert cap.active == 4
    assert cap.has_headroom and cap.remaining == 1


@pytest.mark.django_db
def test_in_cap_ids_keeps_oldest_first() -> None:
    lab = Lab.objects.create(name="Forest", slug="forest")
    Subscription.objects.create(tier=Tier.LAB, scope_lab=lab)
    projects = [Project.objects.create(scope_lab=lab, name=f"L{i}") for i in range(3)]

    # Simulate a downgrade to a cap of 2: the two oldest survive.
    ids = in_cap_ids("scope_lab", lab.id, cap=2)
    assert ids == {projects[0].id, projects[1].id}

    # A zero cap (unentitled org) keeps nothing in budget.
    assert in_cap_ids("scope_lab", lab.id, cap=0) == set()


@pytest.mark.django_db
def test_lab_scope_cap_zero_without_subscription() -> None:
    lab = Lab.objects.create(name="Free Lab", slug="free-lab")
    Project.objects.create(scope_lab=lab, name="X")
    cap = lab_scope_cap(lab)
    assert cap.cap == 0
    assert not cap.has_headroom

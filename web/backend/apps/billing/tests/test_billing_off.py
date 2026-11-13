"""A default instance: ``billing.mode = "off"`` and every limit unlimited.

The rest of the suite runs as the ``institution`` profile (see the root
conftest); these tests opt into the default ``lab`` profile with ``billing_off``
and check that nothing subscription-shaped decides anything there, and that a
single limit set in ``[limits]`` is honoured on its own.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.serializers import ValidationError

from apps.accounts.models import Department, Lab, LabMembership
from apps.accounts.services import ensure_lab_has_room
from apps.billing.entitlements import (
    ALL_FEATURES,
    ambient_enabled,
    billing_enabled,
    cluster_cap,
    cluster_topic_cap,
    department_project_cap,
    effective_features,
    enforcing,
    lab_lead_cap,
    lab_project_cap,
    personal_project_cap,
    topic_cap,
    topics_over_cap,
)
from apps.billing.models import Tier
from apps.research.limits import in_cap_ids, personal_scope_cap


@pytest.fixture
def free_user(db) -> User:
    # No subscription at all: under subscriptions this is the Free tier.
    return User.objects.create_user(username="solo", password="pass-123")


@pytest.mark.django_db
def test_nothing_is_limited_or_withheld(billing_off, free_user):
    assert not billing_enabled()
    assert not enforcing()
    assert effective_features(free_user) == ALL_FEATURES
    assert cluster_cap(free_user) is None
    assert cluster_topic_cap(free_user) is None
    assert topic_cap(free_user) is None
    assert personal_project_cap(free_user) is None
    assert ambient_enabled(Tier.FREE)

    lab = Lab.objects.create(name="Forest Lab", slug="forest")
    dept = Department.objects.create(owner=free_user, name="Biology")
    # No plan, inactive plan — it does not matter with billing off.
    assert lab_project_cap(lab) is None
    assert department_project_cap(dept) is None
    assert lab_lead_cap(lab) is None


@pytest.mark.django_db
def test_the_same_user_is_limited_under_subscriptions(free_user):
    # The suite default (institution): a planless user is Free.
    assert billing_enabled()
    assert cluster_cap(free_user) == 3
    assert topic_cap(free_user) == 6
    assert not ambient_enabled(Tier.FREE)


@pytest.mark.django_db
def test_one_limit_can_be_switched_back_on(billing_off, free_user):
    billing_off.INSTANCE_LIMITS = {**billing_off.INSTANCE_LIMITS, "clusters": 4}
    assert cluster_cap(free_user) == 4
    assert cluster_topic_cap(free_user) is None  # the others stay off


@pytest.mark.django_db
def test_admin_override_still_wins(billing_off, free_user):
    free_user.profile.watch_topic_limit = 3
    free_user.profile.save(update_fields=["watch_topic_limit"])
    assert topic_cap(free_user) == 3


@pytest.mark.django_db
def test_unlimited_topics_are_never_over_cap(billing_off, free_user):
    from apps.accounts.models import WatchPreference

    WatchPreference.objects.create(user=free_user, topics=[f"t{i}" for i in range(80)])
    free_user.refresh_from_db()
    assert not topics_over_cap(free_user)


@pytest.mark.django_db
def test_unlimited_project_scope(billing_off, free_user):
    cap = personal_scope_cap(free_user)
    assert cap.cap is None and cap.has_headroom and cap.remaining is None
    assert in_cap_ids("scope_user", free_user.id, None) == set()


@pytest.mark.django_db
def test_lab_member_limit(billing_off):
    lab = Lab.objects.create(name="Tiny Lab", slug="tiny")
    first = User.objects.create_user(username="a", password="p")
    second = User.objects.create_user(username="b", password="p")
    LabMembership.objects.create(lab=lab, user=first)

    ensure_lab_has_room(lab, second)  # unlimited: fine

    billing_off.INSTANCE_LIMITS = {**billing_off.INSTANCE_LIMITS, "lab_members": 1}
    ensure_lab_has_room(lab, first)  # an existing member is never refused
    with pytest.raises(ValidationError) as exc:
        ensure_lab_has_room(lab, second)
    assert "limits.lab_members" in str(exc.value.detail)


@pytest.mark.django_db
def test_lab_lead_limit(billing_off):
    from django.core.exceptions import ValidationError as DjangoValidationError

    lab = Lab.objects.create(name="Lead Lab", slug="lead")
    one = User.objects.create_user(username="pi1", password="p")
    two = User.objects.create_user(username="pi2", password="p")
    LabMembership.objects.create(lab=lab, user=one, is_lead=True)
    second = LabMembership(lab=lab, user=two, is_lead=True)
    second.clean()  # unlimited

    billing_off.INSTANCE_LIMITS = {**billing_off.INSTANCE_LIMITS, "lab_leads": 1}
    with pytest.raises(DjangoValidationError):
        second.clean()


@pytest.mark.django_db
def test_profile_save_takes_more_than_six_clusters_when_unlimited(
    billing_off, free_user
):
    """Regression: the contract validator used to ignore the person and cap at 6."""
    from apps.accounts.interests import validate_interests

    areas = [f"area {i}" for i in range(8)]
    interests = {
        "areas": areas,
        "clusters": [{"id": f"c-{i}", "label": f"T{i}", "areas": [a]}
                     for i, a in enumerate(areas)],
    }
    assert len(validate_interests(interests, user=free_user)["clusters"]) == 8
    assert len(validate_interests(interests)["clusters"]) == 8  # no person: instance

    billing_off.INSTANCE_LIMITS = {**billing_off.INSTANCE_LIMITS, "clusters": 6}
    with pytest.raises(ValidationError):
        validate_interests(interests, user=free_user)


@pytest.mark.django_db
def test_free_user_is_capped_at_three_clusters_under_subscriptions(free_user):
    from apps.accounts.interests import validate_interests

    areas = [f"area {i}" for i in range(4)]
    interests = {
        "areas": areas,
        "clusters": [{"id": f"c-{i}", "label": f"T{i}", "areas": [a]}
                     for i, a in enumerate(areas)],
    }
    with pytest.raises(ValidationError):
        validate_interests(interests, user=free_user)
    # A lab or project focus is nobody's personal profile: the historical 6.
    assert len(validate_interests(interests)["clusters"]) == 4

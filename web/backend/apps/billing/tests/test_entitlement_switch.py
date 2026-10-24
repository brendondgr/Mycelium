"""The ``BILLING_ENFORCE_ENTITLEMENTS`` switch — the *off* half of the contract.

The rest of the suite runs with gating on (see ``web/backend/conftest.py``), because
the tier matrix is the product's contract and deleting those tests to match a
temporary operational choice would leave nothing to turn back on. These tests cover
the other state: the deployment default, where a tier may not withhold anything.

The thing worth pinning is *scope*. Turning gating off must reach every entitlement
read path — per-user, per-lab, per-department, the bulk resolver the nightly run uses,
and the add-on question the lab settings card asks — because a half-applied switch is
worse than no switch: the API would allow an install the UI still refuses to offer.
What it must **not** reach is the numeric caps, which bound nightly cost rather than
plan value.
"""

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from apps.accounts.models import Lab
from apps.billing.addons import mylo_included
from apps.billing.entitlements import (
    ALL_FEATURES,
    Feature,
    department_has_feature,
    effective_features,
    enforcing,
    has_feature,
    lab_has_feature,
    topic_cap,
    users_with_feature,
)
from apps.billing.models import Subscription, Tier

ungated = override_settings(BILLING_ENFORCE_ENTITLEMENTS=False)


def test_the_switch_defaults_to_off_in_the_deployment() -> None:
    """The suite pins it on; the shipped setting is off."""
    from django.conf import settings

    with override_settings():
        del settings.BILLING_ENFORCE_ENTITLEMENTS
        # Absent entirely, the read path must still fail open, not crash.
        assert enforcing() is False


@pytest.mark.django_db
@ungated
def test_a_free_user_holds_every_feature() -> None:
    user = User.objects.create_user(username="free", password="p")
    assert effective_features(user) == ALL_FEATURES
    assert has_feature(user, Feature.LLM_FIT_SCORING)
    assert has_feature(user, Feature.SCHEDULED_REPORTS)
    # Including the one feature no tier has ever granted.
    assert has_feature(user, Feature.BOT_SERVER)


@pytest.mark.django_db
@ungated
def test_a_lab_with_no_plan_may_still_have_mylo_join_it() -> None:
    """The case that sent us here: a lab whose plan is INACTIVE wanting the bot.

    ``lab_has_feature`` is what ``complete_guild_link`` checks, and ``mylo_included``
    is what the lab settings card reads. They have to agree, or the card says "Not on
    plan" while the API underneath would have allowed the install.
    """
    lab = Lab.objects.create(name="Unpaid", slug="unpaid")
    sub = Subscription.objects.create(
        tier=Tier.LAB, scope_lab=lab, status=Subscription.Status.INACTIVE
    )
    assert lab_has_feature(lab, Feature.BOT_SERVER)
    assert mylo_included(sub) is True
    assert mylo_included(None) is True


@pytest.mark.django_db
@ungated
def test_a_department_with_no_plan_holds_every_feature() -> None:
    from apps.accounts.models import Department

    owner = User.objects.create_user(username="head", password="p")
    dept = Department.objects.create(owner=owner, name="SC")
    assert department_has_feature(dept, Feature.DEPARTMENT_ROUTING)


@pytest.mark.django_db
@ungated
def test_the_bulk_resolver_covers_everyone_not_just_the_baseline() -> None:
    """``users_with_feature`` bypasses ``effective_features``; it needs its own branch.

    The nightly run selects targets through here. Had it kept filtering by tier while
    the per-user path returned everything, the two would disagree and a reader would
    hold a feature the run never scheduled them for.
    """
    paid = User.objects.create_user(username="paid", password="p")
    unpaid = User.objects.create_user(username="unpaid", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=paid)

    covered = users_with_feature(Feature.SCHEDULED_REPORTS)
    assert {paid.id, unpaid.id} <= covered

    # An inactive user is still excluded — this is about entitlement, not liveness.
    unpaid.is_active = False
    unpaid.save(update_fields=["is_active"])
    assert unpaid.id not in users_with_feature(Feature.SCHEDULED_REPORTS)


@pytest.mark.django_db
@ungated
def test_numeric_caps_are_not_part_of_the_switch() -> None:
    """Caps bound nightly work, so they stay enforced while feature gating does not."""
    free = User.objects.create_user(username="capped", password="p")
    assert topic_cap(free) == 6

    spore = User.objects.create_user(username="granted", password="p")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=spore)
    assert topic_cap(spore) == 20


@pytest.mark.django_db
def test_turning_it_on_restores_the_tier_matrix() -> None:
    """With gating on (the suite default) a free account is back to the baseline."""
    user = User.objects.create_user(username="gated", password="p")
    assert enforcing() is True
    assert not has_feature(user, Feature.LLM_FIT_SCORING)
    assert not has_feature(user, Feature.BOT_SERVER)
    assert has_feature(user, Feature.SEMANTIC_SEARCH)

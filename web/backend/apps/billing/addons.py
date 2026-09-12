"""Attach / detach an add-on on one subscription — the write side of A4.

:mod:`apps.billing.entitlements` reads the union of a subscription's ACTIVE add-ons on
top of its tier; this is the only place that flips one on or off. Detaching **cancels**
the :class:`~apps.billing.models.SubscriptionAddOn` rather than deleting it, so the
grant history survives (mirroring the no-data-loss rule the rest of billing follows).
"""

from __future__ import annotations

from django.db import transaction

from .entitlements import Feature
from .models import AddOn, Subscription, SubscriptionAddOn


def addon_for_feature(feature: str) -> AddOn | None:
    """The catalogue row granting ``feature`` (seeded by migration), if present."""
    return AddOn.objects.filter(feature=feature).first()


def has_active_addon(subscription: Subscription | None, feature: str) -> bool:
    """Whether ``subscription`` carries an ACTIVE add-on granting ``feature``."""
    if subscription is None:
        return False
    return SubscriptionAddOn.objects.filter(
        subscription=subscription,
        add_on__feature=feature,
        status=SubscriptionAddOn.Status.ACTIVE,
    ).exists()


@transaction.atomic
def set_addon(subscription: Subscription, feature: str, enabled: bool) -> bool:
    """Grant or revoke the add-on for ``feature`` on ``subscription``.

    Returns whether anything changed, so callers can keep their audit trail honest.
    A no-op (and ``False``) when the feature has no catalogue row — an unseeded add-on
    is a deployment problem, not something to invent a row for.
    """
    add_on = addon_for_feature(feature)
    if add_on is None:
        return False
    status = SubscriptionAddOn.Status
    target = status.ACTIVE if enabled else status.CANCELED
    link = SubscriptionAddOn.objects.filter(
        subscription=subscription, add_on=add_on
    ).first()
    if link is None:
        if not enabled:
            return False
        SubscriptionAddOn.objects.create(
            subscription=subscription, add_on=add_on, status=target
        )
        return True
    if link.status == target:
        return False
    link.status = target
    link.save(update_fields=["status", "updated_at"])
    return True


def set_mylo_included(subscription: Subscription, included: bool) -> bool:
    """Grant or revoke the Mylo-server add-on — "is Mylo part of this plan?"."""
    return set_addon(subscription, Feature.BOT_SERVER, included)


def mylo_included(subscription: Subscription | None) -> bool:
    """Whether this plan includes Mylo on Discord (the ``bot_server`` add-on).

    Answers the *effective* question the UI asks — "can this lab put Mylo in its
    server?" — not the narrower "does an add-on row exist?". While feature gating
    is off (:func:`apps.billing.entitlements.enforcing`) the answer is yes for
    every plan, which is what keeps this consistent with
    :func:`~apps.billing.entitlements.lab_has_feature`. Reporting the bare add-on
    row here instead would leave the lab settings card saying "Not on plan" and
    refusing to offer the install, while the API underneath happily allowed it.
    """
    from .entitlements import enforcing

    if not enforcing():
        return True
    return has_active_addon(subscription, Feature.BOT_SERVER)

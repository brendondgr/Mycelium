"""Request-time enforcement — a DRF permission that gates on an entitlement (A2).

Use :func:`requires_feature` in a view's ``permission_classes``; a caller without
the feature gets a ``403`` whose body carries ``required_tier`` and ``upgrade_url``
so the UI can render an upgrade prompt rather than a generic error.

    class CustomFeedView(APIView):
        permission_classes = [requires_feature(Feature.CUSTOM_TOPIC_FEEDS)]
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .entitlements import TIER_FEATURES, Tier, has_feature

# Tiers in ascending rank — the first that grants a feature is its minimum tier.
_TIER_ORDER = (Tier.SPORE, Tier.LAB, Tier.CANOPY)


def minimum_tier_for(feature: str) -> str | None:
    """The lowest tier that grants ``feature``, or ``None`` if only an add-on does."""
    for tier in _TIER_ORDER:
        if feature in TIER_FEATURES.get(tier, frozenset()):
            return tier
    return None


class FeatureRequired(PermissionDenied):
    """A 403 that tells the client which upgrade unlocks the blocked feature."""

    def __init__(self, feature: str) -> None:
        upgrade_url = getattr(settings, "BILLING_UPGRADE_URL", "/pricing")
        super().__init__(
            {
                "detail": "Your plan does not include this feature.",
                "feature": feature,
                "required_tier": minimum_tier_for(feature),
                "upgrade_url": upgrade_url,
            }
        )


def requires_feature(feature: str) -> type[BasePermission]:
    """Build a permission class that requires ``feature`` of the request user."""

    class RequiresFeature(BasePermission):
        def has_permission(self, request, view) -> bool:
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return False
            if has_feature(user, feature):
                return True
            # Raise (not return False) so the response body carries the upgrade hint.
            raise FeatureRequired(feature)

    return RequiresFeature

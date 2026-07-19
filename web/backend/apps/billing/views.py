"""Billing read surface — the read-time enforcement layer (architecture A2)."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .entitlements import (
    active_seat_count,
    cluster_cap,
    cluster_topic_cap,
    covering_subscriptions,
    effective_features,
    effective_tier,
    pi_cap,
    topic_cap,
)
from .models import SubscriptionAddOn
from .serializers import EntitlementSerializer


def entitlements_payload(user) -> dict:
    """The resolved entitlement snapshot for one user."""
    subscriptions = list(covering_subscriptions(user))
    tier = effective_tier(user)
    watch = getattr(user, "watch", None)
    topics_used = len(getattr(watch, "topics", None) or [])
    seat_count = max((active_seat_count(sub) for sub in subscriptions), default=0)
    addon_slugs = list(
        SubscriptionAddOn.objects.filter(
            subscription__in=subscriptions,
            status=SubscriptionAddOn.Status.ACTIVE,
        )
        .values_list("add_on__slug", flat=True)
        .distinct()
    )
    return {
        "tier": tier,
        "features": sorted(effective_features(user)),
        "topic_cap": topic_cap(user),
        "cluster_cap": cluster_cap(user),
        "cluster_topic_cap": cluster_topic_cap(user),
        "topics_used": topics_used,
        "seat_count": seat_count,
        "pi_cap": pi_cap(tier),
        "addons": addon_slugs,
    }


class EntitlementsView(APIView):
    """``GET /api/billing/me/`` — the signed-in user's entitlements."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = EntitlementSerializer(entitlements_payload(request.user))
        return Response(serializer.data)

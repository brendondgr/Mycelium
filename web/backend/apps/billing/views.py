"""Billing read + activation surface (architecture A2).

``/api/billing/me/`` resolves the signed-in user's entitlements and lists every plan
covering them (account visibility). The lab/department billing endpoints expose a plan's
seat-priced state and let a PI/head **activate** an inactive plan — the boundary this
project stops at (no charging).
"""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Department, Lab
from apps.accounts.permissions import (
    user_can_edit_lab_profile,
    user_can_manage_department,
    user_has_department_access,
    user_has_lab_access,
)

from .addons import mylo_included
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
from .models import Seat, Subscription, SubscriptionAddOn
from .period import today
from .pricing import prorate_add, recurring_monthly_cents, seat_price_cents
from .seats import SeatCeilingExceeded
from .serializers import EntitlementSerializer, OrgBillingSerializer
from .services import (
    activate_department_subscription,
    activate_lab_subscription,
    department_subscription,
    lab_subscription,
)


def user_plans_payload(user) -> list[dict]:
    """Every plan covering the user: their personal plan + each lab/dept seat they hold.

    The answer to "which of Spore / Lab / Canopy do I have active in total" — one entry
    per plan, with the seat's status and who pays for it.
    """
    entries: list[dict] = []
    personal = (
        Subscription.objects.filter(scope_user=user).order_by("-created_at").first()
    )
    if personal is not None:
        entries.append(
            {
                "scope_type": "personal",
                "scope_slug": None,
                "scope_name": "Personal",
                "tier": personal.tier,
                "status": personal.status,
                "seat_status": None,
                "payer_type": "self",
                "current_period_end": personal.current_period_end,
            }
        )
    seats = (
        Seat.objects.filter(member=user)
        .exclude(status=Seat.Status.REVOKED)
        .select_related(
            "subscription",
            "subscription__scope_lab",
            "subscription__scope_department",
        )
    )
    for seat in seats:
        sub = seat.subscription
        scope = sub.scope_lab or sub.scope_department
        slug = sub.scope_lab.slug if sub.scope_lab_id else str(sub.scope_department_id)
        entries.append(
            {
                "scope_type": sub.scope_type,
                "scope_slug": slug,
                "scope_name": getattr(scope, "name", "—"),
                "tier": sub.tier,
                "status": sub.status,
                "seat_status": seat.status,
                "payer_type": seat.payer_type,
                "current_period_end": sub.current_period_end,
            }
        )
    return entries


def entitlements_payload(user) -> dict:
    """The resolved entitlement snapshot for one user, plus their active plans."""
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
        "plans": user_plans_payload(user),
    }


class EntitlementsView(APIView):
    """``GET /api/billing/me/`` — the signed-in user's entitlements + active plans."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = EntitlementSerializer(entitlements_payload(request.user))
        return Response(serializer.data)


def org_billing_payload(
    subscription, *, scope_type: str, scope_slug, scope_name: str, can_manage: bool
) -> dict:
    """The seat-priced state of one org plan (empty-ish when there is no plan yet)."""
    if subscription is None:
        return {
            "scope_type": scope_type,
            "scope_slug": scope_slug,
            "scope_name": scope_name,
            "tier": None,
            "status": None,
            "is_active": False,
            "is_comped": False,
            "mylo_included": False,
            "seat_count": 0,
            "seat_price_cents": 0,
            "recurring_monthly_cents": 0,
            "add_member_proration_cents": 0,
            "current_period_start": None,
            "current_period_end": None,
            "expires_at": None,
            "activated_at": None,
            "can_manage": can_manage,
        }
    price = seat_price_cents(subscription.tier)
    is_active = subscription.status == Subscription.Status.ACTIVE
    comped = subscription.is_comped
    start, end = subscription.current_period_start, subscription.current_period_end
    if comped:
        # Nothing is billed on a complimentary plan, so adding a member costs nothing.
        # ``seat_price_cents`` stays the list price — the plan page strikes it through.
        add_proration = 0
    elif is_active and start and end:
        add_proration = prorate_add(
            subscription.tier, added_on=today(), period_start=start, period_end=end
        )
    else:
        add_proration = price  # a new member would join the eventual full period
    return {
        "scope_type": scope_type,
        "scope_slug": scope_slug,
        "scope_name": scope_name,
        "tier": subscription.tier,
        "status": subscription.status,
        "is_active": is_active,
        "is_comped": comped,
        "mylo_included": mylo_included(subscription),
        "seat_count": active_seat_count(subscription),
        "seat_price_cents": price,
        "recurring_monthly_cents": recurring_monthly_cents(subscription),
        "add_member_proration_cents": add_proration,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "expires_at": subscription.expires_at,
        "activated_at": subscription.activated_at,
        "can_manage": can_manage,
    }


class LabBillingView(APIView):
    """``GET /api/labs/<slug>/billing/`` — a lab's plan state (any member reads)."""

    def get(self, request: Request, slug: str) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_has_lab_access(request.user, lab):
            raise PermissionDenied("You do not have access to this lab.")
        payload = org_billing_payload(
            lab_subscription(lab),
            scope_type="lab",
            scope_slug=lab.slug,
            scope_name=lab.name,
            can_manage=user_can_edit_lab_profile(request.user, lab),
        )
        return Response(OrgBillingSerializer(payload).data)


class LabBillingActivateView(APIView):
    """``POST /api/labs/<slug>/billing/activate/`` — a PI/manager activates the plan."""

    def post(self, request: Request, slug: str) -> Response:
        lab = get_object_or_404(Lab, slug=slug)
        if not user_can_edit_lab_profile(request.user, lab):
            raise PermissionDenied("Only a lab lead or owner/admin can activate.")
        try:
            activate_lab_subscription(lab)
        except SeatCeilingExceeded as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        payload = org_billing_payload(
            lab_subscription(lab),
            scope_type="lab",
            scope_slug=lab.slug,
            scope_name=lab.name,
            can_manage=True,
        )
        return Response(OrgBillingSerializer(payload).data)


class DeptBillingView(APIView):
    """``GET /api/departments/<id>/billing/`` — a department's plan state."""

    def get(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_has_department_access(request.user, department):
            raise PermissionDenied("You do not have access to this department.")
        payload = org_billing_payload(
            department_subscription(department),
            scope_type="department",
            scope_slug=str(department.id),
            scope_name=department.name,
            can_manage=user_can_manage_department(request.user, department),
        )
        return Response(OrgBillingSerializer(payload).data)


class DeptBillingActivateView(APIView):
    """``POST /api/departments/<id>/billing/activate/`` — head activates."""

    def post(self, request: Request, pk) -> Response:
        department = get_object_or_404(Department, id=pk)
        if not user_can_manage_department(request.user, department):
            raise PermissionDenied("Only an owner or admin can activate.")
        try:
            activate_department_subscription(department)
        except SeatCeilingExceeded as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        payload = org_billing_payload(
            department_subscription(department),
            scope_type="department",
            scope_slug=str(department.id),
            scope_name=department.name,
            can_manage=True,
        )
        return Response(OrgBillingSerializer(payload).data)

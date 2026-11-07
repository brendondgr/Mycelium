"""Read + write shapes for the admin dashboard.

Read serializers build from a ``User`` instance and lean on the single
entitlement read path (``apps.billing.entitlements``) so the tier and watch cap an
admin sees are exactly what the user is actually granted. The write serializer
validates a partial PATCH; only the keys the client sends reach ``validated_data``,
which is how the service tells "leave unchanged" from "clear".
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import LabMembership
from apps.billing.addons import mylo_included
from apps.billing.entitlements import active_seat_count, effective_tier, topic_cap
from apps.billing.models import Subscription, Tier
from apps.billing.pricing import recurring_monthly_cents, seat_price_cents
from apps.billing.services import lab_subscription
from apps.billing.tiers import LAB_TIERS, PERSONAL_TIERS
from apps.core.people import display_name

from .services import personal_subscription

#: The override can never usefully exceed the WatchPreference structural ceiling
#: (WatchPreferenceSerializer._MAX_ITEMS = 50), so cap the grant there.
WATCH_TOPIC_LIMIT_MAX = 200  # matches the watch serializer's sanity bound


def _tier_choices(allowed: frozenset[str]) -> list[tuple[str, str]]:
    """``Tier.choices`` narrowed to the tiers a scope is actually sold, in tier order.

    Narrowing the *choices* (rather than validating afterwards) means an out-of-scope
    tier is rejected by the serializer with the field named, and the browsable API only
    ever offers what that surface can grant.
    """
    return [(value, label) for value, label in Tier.choices if value in allowed]


def _watch_topics(user) -> list[str]:
    watch = getattr(user, "watch", None)
    return list(getattr(watch, "topics", None) or [])


class AdminUserRowSerializer(serializers.Serializer):
    """One user as a row in the admin table."""

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.CharField(read_only=True)
    name = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)
    effective_tier = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()
    watch_topics_used = serializers.SerializerMethodField()
    watch_topic_cap = serializers.SerializerMethodField()
    watch_topic_limit = serializers.SerializerMethodField()

    def get_name(self, user) -> str:
        return display_name(user)

    def get_effective_tier(self, user) -> str:
        return effective_tier(user)

    def get_subscription(self, user) -> dict | None:
        sub = personal_subscription(user)
        if sub is None:
            return None
        return {
            "tier": sub.tier,
            "status": sub.status,
            "expires_at": sub.expires_at,
        }

    def get_watch_topics_used(self, user) -> int:
        return len(_watch_topics(user))

    def get_watch_topic_cap(self, user) -> int:
        return topic_cap(user)

    def get_watch_topic_limit(self, user) -> int | None:
        profile = getattr(user, "profile", None)
        return getattr(profile, "watch_topic_limit", None)


class AdminUserDetailSerializer(AdminUserRowSerializer):
    """A single user's full admin view — the row plus watch + membership detail."""

    academic_title = serializers.SerializerMethodField()
    watch_topics = serializers.SerializerMethodField()
    watch_categories = serializers.SerializerMethodField()
    lab_memberships = serializers.SerializerMethodField()

    def get_academic_title(self, user) -> str:
        profile = getattr(user, "profile", None)
        return getattr(profile, "academic_title", "") or ""

    def get_watch_topics(self, user) -> list[str]:
        return _watch_topics(user)

    def get_watch_categories(self, user) -> list[str]:
        watch = getattr(user, "watch", None)
        return list(getattr(watch, "categories", None) or [])

    def get_lab_memberships(self, user) -> list[dict]:
        memberships = (
            LabMembership.objects.filter(user=user)
            .select_related("lab")
            .order_by("lab__name")
        )
        return [
            {
                "slug": m.lab.slug,
                "name": m.lab.name,
                "role": m.role,
                "is_lead": m.is_lead,
            }
            for m in memberships
        ]


class AdminUserUpdateSerializer(serializers.Serializer):
    """A partial admin PATCH over one user's plan + watch quota.

    Every field is optional; a request must carry at least one. ``duration_days``
    and ``expires_at`` are mutually exclusive ways to set the plan's expiry, and
    either sent as ``null`` clears it (open-ended).
    """

    # Personal tiers only. Mycelium Lab and Canopy are team plans priced per member,
    # so they are granted on the lab (or department) that has the roster — see the
    # Labs context and ``apps.billing.tiers``.
    tier = serializers.ChoiceField(
        choices=_tier_choices(PERSONAL_TIERS), required=False
    )
    duration_days = serializers.IntegerField(
        min_value=1, required=False, allow_null=True
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    subscription_status = serializers.ChoiceField(
        choices=Subscription.Status.choices, required=False
    )
    watch_topic_limit = serializers.IntegerField(
        min_value=0, max_value=WATCH_TOPIC_LIMIT_MAX, required=False, allow_null=True
    )

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError(
                "Provide at least one field to update."
            )
        if "duration_days" in attrs and "expires_at" in attrs:
            raise serializers.ValidationError(
                "Provide either duration_days or expires_at, not both."
            )
        return attrs


# --------------------------------------------------------------------------- #
# Labs
# --------------------------------------------------------------------------- #


class AdminLabRowSerializer(serializers.Serializer):
    """One lab as a row in the admin table — identity plus its plan at a glance."""

    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    department = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()

    def get_department(self, lab) -> dict | None:
        department = getattr(lab, "department", None)
        if department is None:
            return None
        return {
            "id": str(department.id),
            "name": department.name,
            "included_in_plan": lab.department_plan_included,
        }

    def get_member_count(self, lab) -> int:
        return LabMembership.objects.filter(lab=lab).count()

    def get_subscription(self, lab) -> dict | None:
        sub = lab_subscription(lab)
        if sub is None:
            return None
        return {
            "tier": sub.tier,
            "status": sub.status,
            "expires_at": sub.expires_at,
            "is_comped": sub.is_comped,
            "mylo_included": mylo_included(sub),
            "seat_count": active_seat_count(sub),
            "seat_price_cents": seat_price_cents(sub.tier),
            "recurring_monthly_cents": recurring_monthly_cents(sub),
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "activated_at": sub.activated_at,
            "billing_interval": sub.billing_interval,
        }


class AdminLabDetailSerializer(AdminLabRowSerializer):
    """One lab's full admin view — the row plus its leads and watch configuration."""

    timezone = serializers.CharField(read_only=True)
    limits = serializers.SerializerMethodField()
    leads = serializers.SerializerMethodField()
    watch_topics = serializers.SerializerMethodField()
    watch_categories = serializers.SerializerMethodField()

    def get_limits(self, lab) -> dict:
        """This lab's staff overrides and the limits in effect (``None`` =
        unlimited) — the override if set, else the instance/tier value."""
        from apps.billing.entitlements import lab_member_cap, lab_project_cap

        return {
            "project_limit": lab.project_limit,
            "member_limit": lab.member_limit,
            "project_cap": lab_project_cap(lab),
            "member_cap": lab_member_cap(lab),
        }

    def get_leads(self, lab) -> list[dict]:
        memberships = (
            LabMembership.objects.filter(lab=lab)
            .select_related("user")
            .order_by("-is_lead", "user__username")
        )
        return [
            {
                "username": m.user.username,
                "name": display_name(m.user),
                "role": m.role,
                "is_lead": m.is_lead,
            }
            for m in memberships
        ]

    def get_watch_topics(self, lab) -> list[str]:
        watch = getattr(lab, "watch", None)
        return list(getattr(watch, "topics", None) or [])

    def get_watch_categories(self, lab) -> list[str]:
        watch = getattr(lab, "watch", None)
        return list(getattr(watch, "categories", None) or [])


class AdminLabUpdateSerializer(serializers.Serializer):
    """A partial admin PATCH over one lab's plan.

    Every field is optional; a request must carry at least one. ``duration_days`` and
    ``expires_at`` are mutually exclusive ways to say when the plan ends, and either
    sent as ``null`` means it never does. A never-ending plan is normally also
    ``is_comped`` — that pairing is what makes a lab free — but the two are separate
    fields so an operator can grant an open-ended *paid* plan if they mean to.
    """

    tier = serializers.ChoiceField(choices=_tier_choices(LAB_TIERS), required=False)
    status = serializers.ChoiceField(
        choices=Subscription.Status.choices, required=False
    )
    duration_days = serializers.IntegerField(
        min_value=1, required=False, allow_null=True
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    is_comped = serializers.BooleanField(required=False)
    mylo_included = serializers.BooleanField(required=False)
    # Per-lab overrides of the instance limits; null clears the override.
    project_limit = serializers.IntegerField(
        min_value=0, max_value=10_000, required=False, allow_null=True
    )
    member_limit = serializers.IntegerField(
        min_value=0, max_value=100_000, required=False, allow_null=True
    )

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        if "duration_days" in attrs and "expires_at" in attrs:
            raise serializers.ValidationError(
                "Provide either duration_days or expires_at, not both."
            )
        return attrs

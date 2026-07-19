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
from apps.billing.entitlements import effective_tier, topic_cap
from apps.billing.models import Subscription, Tier
from apps.core.people import display_name

from .services import personal_subscription

#: The override can never usefully exceed the WatchPreference structural ceiling
#: (WatchPreferenceSerializer._MAX_ITEMS = 50), so cap the grant there.
WATCH_TOPIC_LIMIT_MAX = 50


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

    tier = serializers.ChoiceField(choices=Tier.choices, required=False)
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

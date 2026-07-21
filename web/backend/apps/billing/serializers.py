"""Serializers for the billing read surface."""

from rest_framework import serializers


class PlanSerializer(serializers.Serializer):
    """One plan covering a user — their personal plan or a lab/department seat."""

    scope_type = serializers.CharField()
    scope_name = serializers.CharField()
    tier = serializers.CharField()
    status = serializers.CharField()
    seat_status = serializers.CharField(allow_null=True)
    payer_type = serializers.CharField(allow_null=True)
    current_period_end = serializers.DateField(allow_null=True)


class EntitlementSerializer(serializers.Serializer):
    """The signed-in user's resolved entitlements — the read-time enforcement layer.

    Lets the UI lock affordances (hide a nav entry, show an upgrade CTA, render an
    ``n / topic_cap`` meter) instead of discovering limits through 403s. ``plans`` lists
    every subscription active on the account (Spore / Lab / Canopy), for account
    visibility.
    """

    tier = serializers.CharField()
    features = serializers.ListField(child=serializers.CharField())
    topic_cap = serializers.IntegerField()
    cluster_cap = serializers.IntegerField()
    cluster_topic_cap = serializers.IntegerField()
    topics_used = serializers.IntegerField()
    seat_count = serializers.IntegerField()
    pi_cap = serializers.IntegerField(allow_null=True)
    addons = serializers.ListField(child=serializers.CharField())
    plans = PlanSerializer(many=True)


class OrgBillingSerializer(serializers.Serializer):
    """A lab or department plan's seat-priced state (cents; nothing is charged here)."""

    scope_type = serializers.CharField()
    scope_slug = serializers.CharField(allow_null=True)
    scope_name = serializers.CharField()
    tier = serializers.CharField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    seat_count = serializers.IntegerField()
    seat_price_cents = serializers.IntegerField()
    recurring_monthly_cents = serializers.IntegerField()
    add_member_proration_cents = serializers.IntegerField()
    current_period_start = serializers.DateField(allow_null=True)
    current_period_end = serializers.DateField(allow_null=True)
    activated_at = serializers.DateTimeField(allow_null=True)
    can_manage = serializers.BooleanField()

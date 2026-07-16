"""Serializers for the billing read surface."""

from rest_framework import serializers


class EntitlementSerializer(serializers.Serializer):
    """The signed-in user's resolved entitlements — the read-time enforcement layer.

    Lets the UI lock affordances (hide a nav entry, show an upgrade CTA, render an
    ``n / topic_cap`` meter) instead of discovering limits through 403s.
    """

    tier = serializers.CharField()
    features = serializers.ListField(child=serializers.CharField())
    topic_cap = serializers.IntegerField()
    topics_used = serializers.IntegerField()
    seat_count = serializers.IntegerField()
    pi_cap = serializers.IntegerField(allow_null=True)
    addons = serializers.ListField(child=serializers.CharField())

"""Read serializers for the portal. Never expose tokens, scopes, or raw ids we
don't need on the client — this is display state for the profile card."""

from __future__ import annotations

from rest_framework import serializers

from .models import DiscordIdentity


class DiscordStatusSerializer(serializers.Serializer):
    connected = serializers.SerializerMethodField()
    state = serializers.CharField(allow_null=True)
    link_method = serializers.CharField(allow_null=True)
    username = serializers.CharField(source="username_cache", allow_null=True)
    global_name = serializers.CharField(source="global_name_cache", allow_null=True)
    dm_ok = serializers.BooleanField(allow_null=True)
    dm_checked_at = serializers.DateTimeField(allow_null=True)
    linked_at = serializers.DateTimeField(allow_null=True)

    def get_connected(self, obj) -> bool:
        return bool(obj and obj.state == DiscordIdentity.State.ACTIVE)

    @staticmethod
    def empty() -> dict:
        return {
            "connected": False,
            "state": None,
            "link_method": None,
            "username": None,
            "global_name": None,
            "dm_ok": None,
            "dm_checked_at": None,
            "linked_at": None,
        }

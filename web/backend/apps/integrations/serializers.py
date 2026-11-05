"""Read serializers for the portal. Never expose tokens, scopes, or raw ids we
don't need on the client — this is display state for the profile card."""

from __future__ import annotations

from rest_framework import serializers

from .models import DiscordGuildLink, DiscordIdentity


class DiscordStatusSerializer(serializers.Serializer):
    connected = serializers.SerializerMethodField()
    state = serializers.CharField(allow_null=True)
    link_method = serializers.CharField(allow_null=True)
    username = serializers.CharField(source="username_cache", allow_null=True)
    global_name = serializers.CharField(source="global_name_cache", allow_null=True)
    dm_ok = serializers.BooleanField(allow_null=True)
    dm_checked_at = serializers.DateTimeField(allow_null=True)
    linked_at = serializers.DateTimeField(allow_null=True)
    # Delivery preference for the daily report DM (opt-out; default delivered).
    daily_report_opt_out = serializers.BooleanField()

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
            "daily_report_opt_out": False,
        }


class DiscordGuildStatusSerializer(serializers.Serializer):
    """Whether a Lab's Discord server is synced, for the Manage & Invite page.

    ``synced`` is the single boolean the card keys on (bot installed AND a lab
    manager activated it with ``/activate-lab``); ``state`` carries the nuance so
    the UI can distinguish "installed, run /activate-lab" (pending_setup) and
    "Mylo was removed" (kicked) from "not connected" (no link at all).

    Reads :class:`~.services.resolve.LabServer` — the lab's primary binding.
    """

    synced = serializers.SerializerMethodField()
    state = serializers.CharField(allow_null=True)
    guild_id = serializers.CharField(allow_null=True)
    guild_name = serializers.CharField(source="guild_name_cache", allow_null=True)
    verified = serializers.BooleanField(source="verified_via_code_grant")
    confirmed_at = serializers.DateTimeField(allow_null=True)

    def get_synced(self, obj) -> bool:
        return bool(obj and obj.state == DiscordGuildLink.State.ACTIVE)

    @staticmethod
    def empty() -> dict:
        return {
            "synced": False,
            "state": None,
            "guild_id": None,
            "guild_name": None,
            "verified": False,
            "confirmed_at": None,
        }

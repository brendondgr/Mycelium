from django.contrib import admin

from .models import (
    DiscordActivationCode,
    DiscordGuildLink,
    DiscordIdentity,
    DiscordLabActivationCode,
)


@admin.register(DiscordIdentity)
class DiscordIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "discord_user_id", "state", "link_method", "dm_ok",
                    "linked_at")
    list_filter = ("state", "link_method", "dm_ok")
    search_fields = ("user__username", "discord_user_id", "username_cache")
    # Tokens are encrypted at rest and must never be edited/inspected in admin.
    exclude = ("access_token", "refresh_token")
    readonly_fields = ("created_at", "updated_at", "linked_at")


@admin.register(DiscordGuildLink)
class DiscordGuildLinkAdmin(admin.ModelAdmin):
    list_display = ("lab", "guild_id", "state", "verified_via_code_grant",
                    "installed_by", "confirmed_at")
    list_filter = ("state", "verified_via_code_grant")
    search_fields = ("lab__name", "lab__slug", "guild_id", "guild_name_cache")


@admin.register(DiscordActivationCode)
class DiscordActivationCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "consumed_at")
    list_filter = ("consumed_at",)
    search_fields = ("user__username",)
    # Only the hash is stored; still, don't surface it as an editable field.
    readonly_fields = ("code_hash", "created_at")


@admin.register(DiscordLabActivationCode)
class DiscordLabActivationCodeAdmin(admin.ModelAdmin):
    list_display = ("lab", "issued_by", "created_at", "expires_at", "consumed_at")
    list_filter = ("consumed_at",)
    search_fields = ("lab__name", "lab__slug", "issued_by__username")
    # Only the hash is stored; still, don't surface it as an editable field.
    readonly_fields = ("code_hash", "created_at", "consumed_guild_id")

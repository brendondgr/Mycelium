from django.contrib import admin

from .models import (
    DiscordActivationCode,
    DiscordChannelRoute,
    DiscordDepartmentActivationCode,
    DiscordGuildLink,
    DiscordIdentity,
    DiscordLabActivationCode,
    DiscordTargetBinding,
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
    list_display = ("guild_id", "guild_name_cache", "state", "verified_via_code_grant",
                    "installed_by", "confirmed_at")
    list_filter = ("state", "verified_via_code_grant")
    search_fields = ("guild_id", "guild_name_cache")


class DiscordChannelRouteInline(admin.TabularInline):
    model = DiscordChannelRoute
    extra = 0
    fields = ("purpose", "channel_id", "channel_type", "poster_policy", "ok",
              "verified_at", "created_by_mylo")


@admin.register(DiscordTargetBinding)
class DiscordTargetBindingAdmin(admin.ModelAdmin):
    list_display = ("guild", "lab", "department", "state", "activated_at", "addon_ok")
    list_filter = ("state",)
    search_fields = ("guild__guild_id", "guild__guild_name_cache", "lab__name",
                     "lab__slug", "department__name")
    inlines = [DiscordChannelRouteInline]


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


@admin.register(DiscordDepartmentActivationCode)
class DiscordDepartmentActivationCodeAdmin(admin.ModelAdmin):
    list_display = (
        "department", "issued_by", "created_at", "expires_at", "consumed_at"
    )
    list_filter = ("consumed_at",)
    search_fields = ("department__name", "issued_by__username")
    readonly_fields = ("code_hash", "created_at", "consumed_guild_id")

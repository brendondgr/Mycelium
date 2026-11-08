from django.contrib import admin

from tools.delivery.models import (
    IgnoredItem,
    LabReminderPolicy,
    Notification,
    ReminderFire,
    ReminderSubscription,
)


@admin.register(ReminderSubscription)
class ReminderSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("title", "target_type", "deadline_kind", "due_date", "state")
    list_filter = ("state", "area", "deadline_kind")
    search_fields = ("title", "target_user__username", "target_lab__slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ReminderFire)
class ReminderFireAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "fired_on", "channel", "state", "days_remaining")
    list_filter = ("channel", "state", "fired_on")
    search_fields = ("idempotency_key",)
    readonly_fields = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "created_at", "read_at", "dismissed_at")
    list_filter = ("kind",)
    search_fields = ("title", "user__username", "dedupe_key")
    readonly_fields = ("created_at",)


@admin.register(LabReminderPolicy)
class LabReminderPolicyAdmin(admin.ModelAdmin):
    list_display = ("lab", "created_at", "updated_at")
    search_fields = ("lab__slug", "lab__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(IgnoredItem)
class IgnoredItemAdmin(admin.ModelAdmin):
    list_display = ("user", "area", "content", "created_at")
    list_filter = ("area", "created_at")
    search_fields = ("user__username", "content__source", "content__external_id")
    readonly_fields = ("created_at",)

from django.contrib import admin

from .models import (
    ContentDeadline,
    ContentItem,
    LabReminderPolicy,
    Notification,
    RelevanceScore,
    ReminderFire,
    ReminderSubscription,
)


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ("__str__", "type", "source", "external_id", "created_at")
    list_filter = ("type", "source")
    search_fields = ("source", "external_id", "source_url")
    readonly_fields = ("created_at",)


@admin.register(ContentDeadline)
class ContentDeadlineAdmin(admin.ModelAdmin):
    list_display = ("content", "kind", "due_date", "confidence", "changed_at")
    list_filter = ("kind", "confidence")
    search_fields = ("content__source", "content__external_id")
    readonly_fields = ("created_at", "updated_at", "changed_at", "previous_due_date")


@admin.register(RelevanceScore)
class RelevanceScoreAdmin(admin.ModelAdmin):
    list_display = ("content", "target_type", "score", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content__source",)
    readonly_fields = ("created_at",)


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

from django.contrib import admin

from .models import ContentDeadline, ContentItem, RelevanceScore


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

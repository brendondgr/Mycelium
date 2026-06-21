from django.contrib import admin

from .models import ContentItem, RelevanceScore


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ("__str__", "type", "source", "created_at")
    list_filter = ("type", "source")
    search_fields = ("source",)
    readonly_fields = ("created_at",)


@admin.register(RelevanceScore)
class RelevanceScoreAdmin(admin.ModelAdmin):
    list_display = ("content", "target_type", "score", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content__source",)
    readonly_fields = ("created_at",)

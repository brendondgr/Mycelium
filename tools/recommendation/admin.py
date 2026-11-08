from django.contrib import admin

from tools.recommendation.models import RelevanceScore


@admin.register(RelevanceScore)
class RelevanceScoreAdmin(admin.ModelAdmin):
    list_display = ("content", "target_type", "score", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content__source",)
    readonly_fields = ("created_at",)

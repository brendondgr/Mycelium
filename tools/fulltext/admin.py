"""Read-only admin views of what the tool retrieved and why."""

from django.contrib import admin

from .models import FulltextDocument, FulltextRequest, SourceVerdict


class ReadOnly(admin.ModelAdmin):
    """Rows are written by the tool, never by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FulltextDocument)
class FulltextDocumentAdmin(ReadOnly):
    list_display = ("title", "doi", "pmid", "source", "licensed", "chars", "fetched_at")
    list_filter = ("source", "licensed")
    search_fields = ("title", "doi", "pmid", "pmcid", "arxiv_id")


@admin.register(FulltextRequest)
class FulltextRequestAdmin(ReadOnly):
    list_display = ("identifier", "status", "requester", "retryable", "created_at")
    list_filter = ("status", "retryable")


@admin.register(SourceVerdict)
class SourceVerdictAdmin(ReadOnly):
    list_display = ("key", "source", "outcome", "created_at")
    list_filter = ("source",)
    search_fields = ("key",)

"""Staff views of the knowledge core.

Read-mostly. The one write staff are meant to make is a merge (or its reversal),
which goes through :mod:`apps.knowledge.merging` so it is logged and reversible;
edges are otherwise maintained by the projection and by the owning features.
"""

from __future__ import annotations

from django.contrib import admin, messages

from . import merging
from .models import Concept, ConceptAlias, ConceptMerge, Edge


class ConceptAliasInline(admin.TabularInline):
    model = ConceptAlias
    extra = 0
    fields = ("text", "facet", "scope", "scope_user", "scope_lab", "scope_department")
    readonly_fields = fields
    can_delete = False


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display = ("label", "facet", "scope", "status", "edge_count", "updated_at")
    list_filter = ("facet", "scope", "status")
    search_fields = ("label", "neutral_label", "aliases__text")
    readonly_fields = ("embedding", "merged_into", "created_at", "updated_at")
    inlines = [ConceptAliasInline]
    actions = ["merge_into_first"]

    @admin.display(description="Edges")
    def edge_count(self, obj: Concept) -> int:
        return obj.edges.count()

    @admin.action(description="Merge the selected concepts into the first one")
    def merge_into_first(self, request, queryset):
        concepts = list(queryset.filter(status=Concept.Status.ACTIVE).order_by("pk"))
        if len(concepts) < 2:
            self.message_user(
                request, "Select at least two active concepts.", messages.WARNING
            )
            return
        target, *sources = concepts
        try:
            for source in sources:
                merging.merge(source, target, actor=request.user)
        except merging.MergeRefused as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return
        self.message_user(
            request, f"Merged {len(sources)} concept(s) into “{target.label}”."
        )


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ("subject_label", "relation", "concept", "tier", "status", "surface")
    list_filter = ("tier", "status", "relation")
    search_fields = ("surface", "concept__label")
    raw_id_fields = ("user", "project", "lab", "author_work", "content_item", "concept")

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(ConceptMerge)
class ConceptMergeAdmin(admin.ModelAdmin):
    list_display = ("kind", "source", "target", "actor", "created_at", "reversed_by")
    list_filter = ("kind",)
    readonly_fields = [field.name for field in ConceptMerge._meta.fields]
    actions = ["reverse"]

    def has_add_permission(self, request) -> bool:
        return False

    @admin.action(description="Reverse the selected merges")
    def reverse(self, request, queryset):
        reversed_count = 0
        for record in queryset.order_by("-pk"):
            try:
                merging.unmerge(record, actor=request.user)
                reversed_count += 1
            except merging.MergeRefused as exc:
                self.message_user(request, f"{record}: {exc}", messages.ERROR)
        if reversed_count:
            self.message_user(request, f"Reversed {reversed_count} merge(s).")

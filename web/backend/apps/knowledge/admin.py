"""Staff views of the knowledge core.

Read-only. Edges are maintained by the projection and by the owning features,
never by hand.
"""

from __future__ import annotations

from django.contrib import admin

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

    @admin.display(description="Edges")
    def edge_count(self, obj: Concept) -> int:
        return obj.edges.count()


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

    def has_add_permission(self, request) -> bool:
        return False

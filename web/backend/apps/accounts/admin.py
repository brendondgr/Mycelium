from django.contrib import admin

from .models import AuditEvent, Lab, LabMembership


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(LabMembership)
class LabMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "lab", "role", "created_at")
    list_filter = ("role", "lab")
    search_fields = ("user__username", "lab__name", "lab__slug")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("action", "target_type", "target_id", "actor", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("action", "target_type", "target_id", "actor__username")
    readonly_fields = ("created_at",)

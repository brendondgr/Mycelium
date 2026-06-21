from django.contrib import admin

from .models import AuditEvent, Department, DeptMembership, Lab, LabMembership


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "institution", "created_at")
    search_fields = ("name", "institution", "owner__username")


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "department", "created_at")
    list_filter = ("department",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(LabMembership)
class LabMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "lab", "role", "is_lead", "created_at")
    list_filter = ("role", "is_lead", "lab")
    search_fields = ("user__username", "lab__name", "lab__slug")


@admin.register(DeptMembership)
class DeptMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "role", "created_at")
    list_filter = ("role", "department")
    search_fields = ("user__username", "department__name")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("action", "target_type", "target_id", "actor", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("action", "target_type", "target_id", "actor__username")
    readonly_fields = ("created_at",)

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from .interests import validate_interests
from .models import (
    AuditEvent,
    Department,
    DeptMembership,
    DeptProfile,
    Lab,
    LabMembership,
    LabProfile,
    Profile,
    WatchPreference,
)


def _flatten_drf_error(detail) -> str:
    """Render a DRF validation ``detail`` into a single admin-friendly string."""
    parts: list[str] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            parts.append(f"{key}: {_flatten_drf_error(value)}")
    elif isinstance(detail, list):
        parts.extend(_flatten_drf_error(item) for item in detail)
    else:
        parts.append(str(detail))
    return "; ".join(parts)


class ProfileAdminForm(forms.ModelForm):
    """Run ``interests`` through the shared contract gate on admin save."""

    class Meta:
        model = Profile
        fields = "__all__"

    def clean_interests(self):
        data = self.cleaned_data.get("interests")
        try:
            return validate_interests(data)
        except DRFValidationError as exc:
            raise DjangoValidationError(_flatten_drf_error(exc.detail)) from exc


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    form = ProfileAdminForm
    list_display = ("user", "academic_title", "institution", "updated_at")
    list_filter = ("academic_title",)
    search_fields = ("user__username", "institution")
    readonly_fields = ("created_at", "updated_at")


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


@admin.register(LabProfile)
class LabProfileAdmin(admin.ModelAdmin):
    list_display = ("lab", "updated_at")
    search_fields = ("lab__name", "lab__slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DeptProfile)
class DeptProfileAdmin(admin.ModelAdmin):
    list_display = ("department", "updated_at")
    search_fields = ("department__name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(WatchPreference)
class WatchPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "cadence", "updated_at")
    list_filter = ("cadence",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("action", "target_type", "target_id", "actor", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("action", "target_type", "target_id", "actor__username")
    readonly_fields = ("created_at",)

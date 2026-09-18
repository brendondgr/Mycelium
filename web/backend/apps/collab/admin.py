from django.contrib import admin

from .models import RequirementSlots, SlotFeedback


@admin.register(RequirementSlots)
class RequirementSlotsAdmin(admin.ModelAdmin):
    list_display = ("content", "status", "prompt_version", "updated_at")
    list_filter = ("status", "prompt_version")
    readonly_fields = [f.name for f in RequirementSlots._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(SlotFeedback)
class SlotFeedbackAdmin(admin.ModelAdmin):
    list_display = ("kind", "content", "slot_text", "user", "created_at")
    list_filter = ("kind",)
    readonly_fields = [f.name for f in SlotFeedback._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

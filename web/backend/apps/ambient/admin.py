"""Admin for the ledger — deliberately read-mostly.

The consent tables are editable because support sometimes has to turn a source
off on somebody's behalf. Observations and their verdicts are not: an
observation is evidence about a person, and evidence a staff member can quietly
rewrite is not evidence. Removing it is done through
:mod:`apps.ambient.reconcile`, which leaves a retraction behind.
"""

from django.contrib import admin

from .models import (
    ListeningConsent,
    Observation,
    ObservationFeedback,
    RawMessageRef,
    Retraction,
    Source,
)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("kind", "external_id", "label", "lab", "consent_state")
    list_filter = ("kind", "consent_state")
    search_fields = ("external_id", "label")


@admin.register(ListeningConsent)
class ListeningConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "enabled", "questions_muted", "updated_at")
    list_filter = ("platform", "enabled", "questions_muted")
    search_fields = ("user__username", "user__email")


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(RawMessageRef)
class RawMessageRefAdmin(ReadOnlyAdmin):
    # No body column exists to display, here or anywhere else.
    list_display = ("source", "external_id", "speaker", "place_label", "sent_at")
    list_filter = ("place_kind", "speaker_kind")


@admin.register(Observation)
class ObservationAdmin(ReadOnlyAdmin):
    list_display = (
        "speaker",
        "understanding_kind",
        "force",
        "subject",
        "visibility",
        "status",
        "observed_at",
    )
    list_filter = ("understanding_kind", "force", "visibility", "status", "origin")
    search_fields = ("speaker__username",)


@admin.register(ObservationFeedback)
class ObservationFeedbackAdmin(ReadOnlyAdmin):
    list_display = ("observation", "user", "verdict", "channel", "created_at")
    list_filter = ("verdict", "channel")


@admin.register(Retraction)
class RetractionAdmin(ReadOnlyAdmin):
    list_display = ("reason", "user", "source", "created_at", "recomputed_at")
    list_filter = ("reason",)

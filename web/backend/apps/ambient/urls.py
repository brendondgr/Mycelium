from django.urls import path

from . import views

urlpatterns = [
    # What Mylo records of me, per server and per project (both slash forms).
    path("recording/", views.RecordingView.as_view(), name="ambient-recording"),
    path("recording", views.RecordingView.as_view()),
    # The head's switch for an org's Discord servers.
    path(
        "servers/<str:kind>/<str:ref>/",
        views.OrgServerListeningView.as_view(),
        name="ambient-org-servers",
    ),
    path("servers/<str:kind>/<str:ref>", views.OrgServerListeningView.as_view()),
    path(
        "projects/<uuid:pk>/conversation/",
        views.ProjectConversationView.as_view(),
        name="ambient-project-conversation",
    ),
    path(
        "projects/<uuid:pk>/channel-hints/",
        views.ProjectChannelHintView.as_view(),
        name="ambient-project-channel-hints",
    ),
    path(
        "attributions/<int:ref_id>/correct/",
        views.AttributionCorrectView.as_view(),
        name="ambient-attribution-correct",
    ),
    path(
        "suggestions/",
        views.SuggestionListView.as_view(),
        name="ambient-suggestions",
    ),
    path(
        "suggestions/<int:pk>/answer/",
        views.SuggestionAnswerView.as_view(),
        name="ambient-suggestion-answer",
    ),
    path("changes/", views.ChangeListView.as_view(), name="ambient-changes"),
    path(
        "changes/<int:pk>/undo/",
        views.ChangeUndoView.as_view(),
        name="ambient-change-undo",
    ),
    path(
        "understanding/",
        views.UnderstandingView.as_view(),
        name="ambient-understanding",
    ),
    path(
        "understanding/<int:concept_id>/<str:relation>/",
        views.UnderstandingItemView.as_view(),
        name="ambient-understanding-item",
    ),
    path(
        "understanding/<int:concept_id>/<str:relation>/reopen/",
        views.UnderstandingReopenView.as_view(),
        name="ambient-understanding-reopen",
    ),
    path("settings/", views.AmbientSettingsView.as_view(), name="ambient-settings"),
    path(
        "observations/delete/",
        views.ObservationsDeleteView.as_view(),
        name="ambient-observations-delete",
    ),
    path(
        "projects/<uuid:pk>/developments/",
        views.ProjectDevelopmentsView.as_view(),
        name="ambient-project-developments",
    ),
    path(
        "labs/<slug:slug>/changes/",
        views.LabChangesView.as_view(),
        name="ambient-lab-changes",
    ),
    path(
        "transcripts/",
        views.TranscriptUploadView.as_view(),
        name="ambient-transcripts",
    ),
]

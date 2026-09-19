from django.urls import path

from . import views

urlpatterns = [
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
]

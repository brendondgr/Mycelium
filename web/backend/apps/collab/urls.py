from django.urls import path

from .views import (
    CollaborationPreviewView,
    CollaborationSettingView,
    IntroductionView,
    MatchFeedbackView,
    SavedPeopleView,
    SearchView,
    SlotFeedbackView,
    TeamView,
)

urlpatterns = [
    path("search/", SearchView.as_view(), name="collab-search"),
    path("team/", TeamView.as_view(), name="collab-team"),
    path("saved/", SavedPeopleView.as_view(), name="collab-saved"),
    path(
        "searches/<int:search_id>/introduction/<str:username>/",
        IntroductionView.as_view(),
        name="collab-introduction",
    ),
    path(
        "searches/<int:search_id>/feedback/",
        MatchFeedbackView.as_view(),
        name="collab-match-feedback",
    ),
    path("settings/", CollaborationSettingView.as_view(), name="collab-settings"),
    path("preview/", CollaborationPreviewView.as_view(), name="collab-preview"),
    path(
        "calls/<uuid:content_id>/slot-feedback/",
        SlotFeedbackView.as_view(),
        name="collab-slot-feedback",
    ),
]

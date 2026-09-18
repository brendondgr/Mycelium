from django.urls import path

from .views import CollaborationPreviewView, CollaborationSettingView, SlotFeedbackView

urlpatterns = [
    path("settings/", CollaborationSettingView.as_view(), name="collab-settings"),
    path("preview/", CollaborationPreviewView.as_view(), name="collab-preview"),
    path(
        "calls/<uuid:content_id>/slot-feedback/",
        SlotFeedbackView.as_view(),
        name="collab-slot-feedback",
    ),
]

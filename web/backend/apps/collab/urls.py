from django.urls import path

from .views import SlotFeedbackView

urlpatterns = [
    path(
        "calls/<uuid:content_id>/slot-feedback/",
        SlotFeedbackView.as_view(),
        name="collab-slot-feedback",
    ),
]

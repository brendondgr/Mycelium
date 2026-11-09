"""Routes under ``api/tools/files/``."""

from django.urls import path

from . import views

urlpatterns = [
    path("files/", views.FilesView.as_view(), name="files-list"),
    path("files", views.FilesView.as_view()),
    path("files/<uuid:file_id>/", views.FileView.as_view(), name="files-detail"),
    path("files/<uuid:file_id>/text/", views.FileTextView.as_view(), name="files-text"),
    path(
        "files/<uuid:file_id>/download/",
        views.FileDownloadView.as_view(),
        name="files-download",
    ),
]

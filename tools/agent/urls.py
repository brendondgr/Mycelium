"""Routes under ``api/tools/agent/``. POST routes accept both trailing-slash
forms (a dev proxy strips the slash)."""

from django.urls import path

from . import views


def both(route, view, name):
    return [path(route, view, name=name), path(route.rstrip("/"), view)]


urlpatterns = [
    path("status/", views.StatusView.as_view(), name="agent-status"),
    path("catalog/", views.CatalogView.as_view(), name="agent-catalog"),
    *both("threads/", views.ThreadsView.as_view(), "agent-threads"),
    path("threads/<uuid:thread_id>/", views.ThreadView.as_view(), name="agent-thread"),
    *both(
        "threads/<uuid:thread_id>/messages/",
        views.MessagesView.as_view(),
        "agent-messages",
    ),
    *both(
        "threads/<uuid:thread_id>/answer/", views.AnswerView.as_view(), "agent-answer"
    ),
    *both(
        "threads/<uuid:thread_id>/cancel/", views.CancelView.as_view(), "agent-cancel"
    ),
    *both("threads/<uuid:thread_id>/fork/", views.ForkView.as_view(), "agent-fork"),
    path(
        "threads/<uuid:thread_id>/events/",
        views.EventsView.as_view(),
        name="agent-events",
    ),
    path(
        "threads/<uuid:thread_id>/stream/",
        views.StreamView.as_view(),
        name="agent-stream",
    ),
    path(
        "threads/<uuid:thread_id>/export/",
        views.ExportView.as_view(),
        name="agent-export",
    ),
    path("refs/search/", views.RefSearchView.as_view(), name="agent-ref-search"),
    path("preferences/", views.PreferencesView.as_view(), name="agent-preferences"),
    path(
        "policy/<str:kind>/<str:ref>/", views.PolicyView.as_view(), name="agent-policy"
    ),
]

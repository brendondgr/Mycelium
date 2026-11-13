from django.urls import path

from . import setup_status, views

# Both slash and no-slash variants: the browser reaches these through the Next
# `/api` proxy, which strips the trailing slash, and Django's APPEND_SLASH cannot
# redirect a PATCH — so a slash-only route would 500 the write. Mirrors the
# accounts/content url style.
urlpatterns = [
    path("users/", views.AdminUserListView.as_view(), name="admin-users"),
    path("users", views.AdminUserListView.as_view(), name="admin-users-no-slash"),
    path(
        "users/<int:pk>/",
        views.AdminUserDetailView.as_view(),
        name="admin-user-detail",
    ),
    path(
        "users/<int:pk>",
        views.AdminUserDetailView.as_view(),
        name="admin-user-detail-no-slash",
    ),
    path("labs/", views.AdminLabListView.as_view(), name="admin-labs"),
    path("labs", views.AdminLabListView.as_view(), name="admin-labs-no-slash"),
    path(
        "labs/<slug:slug>/",
        views.AdminLabDetailView.as_view(),
        name="admin-lab-detail",
    ),
    path(
        "labs/<slug:slug>",
        views.AdminLabDetailView.as_view(),
        name="admin-lab-detail-no-slash",
    ),
    path("llm/servers/", views.AdminLLMServersView.as_view(),
         name="admin-llm-servers"),
    path("llm/servers", views.AdminLLMServersView.as_view(),
         name="admin-llm-servers-no-slash"),
    path("setup-status/", setup_status.SetupStatusView.as_view(),
         name="admin-setup-status"),
    path("setup-status", setup_status.SetupStatusView.as_view(),
         name="admin-setup-status-no-slash"),
]

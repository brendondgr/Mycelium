from django.urls import path

from . import views

urlpatterns = [
    path("projects/", views.ProjectListView.as_view(), name="project-list"),
    path("projects", views.ProjectListView.as_view(), name="project-list-no-slash"),
    # Every project of one lab (any lab member may browse them to join).
    path(
        "projects/lab/<slug:slug>/",
        views.LabProjectsView.as_view(),
        name="lab-projects",
    ),
    path(
        "projects/lab/<slug:slug>",
        views.LabProjectsView.as_view(),
        name="lab-projects-no-slash",
    ),
    # Self-join / leave a project; managers add another member. Both slash and
    # no-slash variants — the Next `/api` proxy strips the trailing slash and
    # Django's APPEND_SLASH cannot redirect a POST (it would 500).
    path(
        "projects/<uuid:pk>/join/",
        views.ProjectJoinView.as_view(),
        name="project-join",
    ),
    path(
        "projects/<uuid:pk>/join",
        views.ProjectJoinView.as_view(),
        name="project-join-no-slash",
    ),
    path(
        "projects/<uuid:pk>/leave/",
        views.ProjectLeaveView.as_view(),
        name="project-leave",
    ),
    path(
        "projects/<uuid:pk>/leave",
        views.ProjectLeaveView.as_view(),
        name="project-leave-no-slash",
    ),
    path(
        "projects/<uuid:pk>/members/",
        views.ProjectMembersView.as_view(),
        name="project-members",
    ),
    path(
        "projects/<uuid:pk>/members",
        views.ProjectMembersView.as_view(),
        name="project-members-no-slash",
    ),
]

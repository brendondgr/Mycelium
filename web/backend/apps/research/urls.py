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
    # Self-join / leave a project; managers add another member.
    path(
        "projects/<uuid:pk>/join/",
        views.ProjectJoinView.as_view(),
        name="project-join",
    ),
    path(
        "projects/<uuid:pk>/leave/",
        views.ProjectLeaveView.as_view(),
        name="project-leave",
    ),
    path(
        "projects/<uuid:pk>/members/",
        views.ProjectMembersView.as_view(),
        name="project-members",
    ),
]

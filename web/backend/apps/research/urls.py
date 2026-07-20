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
    # Read one project, or PATCH its name / research focus (managers).
    path(
        "projects/<uuid:pk>/",
        views.ProjectDetailView.as_view(),
        name="project-detail",
    ),
    path(
        "projects/<uuid:pk>",
        views.ProjectDetailView.as_view(),
        name="project-detail-no-slash",
    ),
    # Archive (POST) / unarchive (DELETE) a project. Never deletes the row.
    path(
        "projects/<uuid:pk>/archive/",
        views.ProjectArchiveView.as_view(),
        name="project-archive",
    ),
    path(
        "projects/<uuid:pk>/archive",
        views.ProjectArchiveView.as_view(),
        name="project-archive-no-slash",
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
    # Collaboration surface: share into the feed, read the feed, paste-a-link
    # ingest, mark-seen, and engagement events. Slash + no-slash for the proxy.
    path(
        "projects/<uuid:pk>/shares/",
        views.ProjectShareView.as_view(),
        name="project-share",
    ),
    path(
        "projects/<uuid:pk>/shares",
        views.ProjectShareView.as_view(),
        name="project-share-no-slash",
    ),
    path(
        "projects/<uuid:pk>/feed/",
        views.ProjectFeedView.as_view(),
        name="project-feed",
    ),
    path(
        "projects/<uuid:pk>/feed",
        views.ProjectFeedView.as_view(),
        name="project-feed-no-slash",
    ),
    path(
        "projects/<uuid:pk>/ingest-link/",
        views.ProjectIngestLinkView.as_view(),
        name="project-ingest-link",
    ),
    path(
        "projects/<uuid:pk>/ingest-link",
        views.ProjectIngestLinkView.as_view(),
        name="project-ingest-link-no-slash",
    ),
    path(
        "projects/<uuid:pk>/items/<uuid:content_id>/seen/",
        views.ProjectItemSeenView.as_view(),
        name="project-item-seen",
    ),
    path(
        "projects/<uuid:pk>/items/<uuid:content_id>/seen",
        views.ProjectItemSeenView.as_view(),
        name="project-item-seen-no-slash",
    ),
    path(
        "projects/<uuid:pk>/events/",
        views.ProjectEventView.as_view(),
        name="project-event",
    ),
    path(
        "projects/<uuid:pk>/events",
        views.ProjectEventView.as_view(),
        name="project-event-no-slash",
    ),
    # Shared collections / reading lists (Feature C).
    path(
        "projects/<uuid:pk>/collections/",
        views.ProjectCollectionsView.as_view(),
        name="project-collections",
    ),
    path(
        "projects/<uuid:pk>/collections",
        views.ProjectCollectionsView.as_view(),
        name="project-collections-no-slash",
    ),
    path(
        "projects/<uuid:pk>/collections/<uuid:cid>/",
        views.ProjectCollectionDetailView.as_view(),
        name="project-collection-detail",
    ),
    path(
        "projects/<uuid:pk>/collections/<uuid:cid>",
        views.ProjectCollectionDetailView.as_view(),
        name="project-collection-detail-no-slash",
    ),
    path(
        "projects/<uuid:pk>/collections/<uuid:cid>/items/",
        views.ProjectCollectionItemsView.as_view(),
        name="project-collection-items",
    ),
    path(
        "projects/<uuid:pk>/collections/<uuid:cid>/items",
        views.ProjectCollectionItemsView.as_view(),
        name="project-collection-items-no-slash",
    ),
    path(
        "projects/<uuid:pk>/collections/<uuid:cid>/items/<uuid:content_id>/",
        views.ProjectCollectionItemDetailView.as_view(),
        name="project-collection-item-detail",
    ),
    path(
        "projects/<uuid:pk>/collections/<uuid:cid>/items/<uuid:content_id>",
        views.ProjectCollectionItemDetailView.as_view(),
        name="project-collection-item-detail-no-slash",
    ),
]

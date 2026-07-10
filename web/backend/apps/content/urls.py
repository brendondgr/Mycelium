from django.urls import path

from . import views

urlpatterns = [
    # Both forms so a dev proxy that strips the trailing slash still resolves
    # (matches the workspace read endpoints).
    path("daily-report/", views.DailyReportView.as_view(), name="daily-report"),
    path("daily-report", views.DailyReportView.as_view(), name="daily-report-no-slash"),
    # Post-onboarding live match: one area per POST, over the existing corpus.
    path(
        "onboarding/match/",
        views.OnboardingMatchView.as_view(),
        name="onboarding-match",
    ),
    path("onboarding/match", views.OnboardingMatchView.as_view()),
    # Opportunities (personal workspace): grants + conferences feeds, the save
    # system, deadlines, and the notification-bell alerts.
    path(
        "opportunities/grants/",
        views.GrantsView.as_view(),
        name="opportunities-grants",
    ),
    path("opportunities/grants", views.GrantsView.as_view()),
    path(
        "opportunities/conferences/",
        views.ConferencesView.as_view(),
        name="opportunities-conferences",
    ),
    path("opportunities/conferences", views.ConferencesView.as_view()),
    path(
        "opportunities/fellowships/",
        views.FellowshipsView.as_view(),
        name="opportunities-fellowships",
    ),
    path("opportunities/fellowships", views.FellowshipsView.as_view()),
    path(
        "opportunities/save/",
        views.SaveOpportunityView.as_view(),
        name="opportunity-save",
    ),
    path("opportunities/save", views.SaveOpportunityView.as_view()),
    path(
        "opportunities/save/<uuid:content_id>/",
        views.SaveOpportunityView.as_view(),
        name="opportunity-unsave",
    ),
    path(
        "opportunities/save/<uuid:content_id>",
        views.SaveOpportunityView.as_view(),
    ),
    # Institutional recommendation feeds: a lab's aggregate matches and one
    # project's focus matches (papers + grants + conferences, fellowships excluded).
    path(
        "labs/<slug:slug>/recommendations/",
        views.LabRecommendationsView.as_view(),
        name="lab-recommendations",
    ),
    path(
        "labs/<slug:slug>/recommendations",
        views.LabRecommendationsView.as_view(),
    ),
    path(
        "projects/<uuid:pk>/recommendations/",
        views.ProjectRecommendationsView.as_view(),
        name="project-recommendations",
    ),
    path(
        "projects/<uuid:pk>/recommendations",
        views.ProjectRecommendationsView.as_view(),
    ),
    path("deadlines/", views.DeadlinesView.as_view(), name="deadlines"),
    path("deadlines", views.DeadlinesView.as_view()),
    path("notifications/", views.NotificationsView.as_view(), name="notifications"),
    path("notifications", views.NotificationsView.as_view()),
]

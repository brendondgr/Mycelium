from django.urls import path

from . import reminders_views, views

urlpatterns = [
    # Both forms so a dev proxy that strips the trailing slash still resolves
    # (matches the workspace read endpoints).
    path("daily-report/", views.DailyReportView.as_view(), name="daily-report"),
    path("daily-report", views.DailyReportView.as_view(), name="daily-report-no-slash"),
    # The cross-category "Mylo Report" briefing (the Daily page's three zones).
    path("daily-briefing/", views.DailyBriefingView.as_view(), name="daily-briefing"),
    path(
        "daily-briefing",
        views.DailyBriefingView.as_view(),
        name="daily-briefing-no-slash",
    ),
    # Unified query-first search over the content corpus.
    path("search/", views.SearchView.as_view(), name="search"),
    path("search", views.SearchView.as_view(), name="search-no-slash"),
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
    # A lab's written daily briefing (the lab overview's Mylo Report zone).
    path(
        "labs/<slug:slug>/daily-briefing/",
        views.LabDailyBriefingView.as_view(),
        name="lab-daily-briefing",
    ),
    path(
        "labs/<slug:slug>/daily-briefing",
        views.LabDailyBriefingView.as_view(),
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
    # The signed-in user's own "what Mylo found" recency matrix (personal Overview).
    path(
        "recommendations/window-counts/",
        views.PersonalWindowCountsView.as_view(),
        name="personal-window-counts",
    ),
    path(
        "recommendations/window-counts",
        views.PersonalWindowCountsView.as_view(),
    ),
    # The Saves (bookmarks) page: every save with feed-parity card payloads.
    path("saves/", views.SavedItemsView.as_view(), name="saves"),
    path("saves", views.SavedItemsView.as_view()),
    # A lab's shared saves (lab Saves area); members read, managers mutate.
    path(
        "labs/<slug:slug>/saves/",
        views.LabSavedItemsView.as_view(),
        name="lab-saves",
    ),
    path("labs/<slug:slug>/saves", views.LabSavedItemsView.as_view()),
    path("notifications/", views.NotificationsView.as_view(), name="notifications"),
    path("notifications", views.NotificationsView.as_view()),
    path(
        "notifications/<uuid:pk>/action/",
        views.NotificationActionView.as_view(),
        name="notification-action",
    ),
    path(
        "notifications/<uuid:pk>/action",
        views.NotificationActionView.as_view(),
    ),
    # Deadline reminders: create / list / cancel personal + lab reminders (R9).
    path(
        "reminders/",
        reminders_views.ReminderListCreateView.as_view(),
        name="reminders",
    ),
    path("reminders", reminders_views.ReminderListCreateView.as_view()),
    # Postable Discord channels for the lab reminder channel picker (manager-only).
    path(
        "reminders/lab-channels/",
        reminders_views.LabReminderChannelsView.as_view(),
        name="reminder-lab-channels",
    ),
    path(
        "reminders/lab-channels",
        reminders_views.LabReminderChannelsView.as_view(),
    ),
    path(
        "reminders/<uuid:pk>/",
        reminders_views.ReminderDetailView.as_view(),
        name="reminder-detail",
    ),
    path("reminders/<uuid:pk>", reminders_views.ReminderDetailView.as_view()),
    # Cross-member suggestions (Feature F): the in-app fan-out feed + dismiss.
    path(
        "suggestions/",
        views.MemberSuggestionsView.as_view(),
        name="member-suggestions",
    ),
    path("suggestions", views.MemberSuggestionsView.as_view()),
    path(
        "suggestions/<uuid:pk>/dismiss/",
        views.MemberSuggestionDismissView.as_view(),
        name="member-suggestion-dismiss",
    ),
    path(
        "suggestions/<uuid:pk>/dismiss",
        views.MemberSuggestionDismissView.as_view(),
    ),
]

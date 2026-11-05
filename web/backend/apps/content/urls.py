from datetime import date, datetime

from django.urls import path, register_converter

from . import announcement_views, reminders_views, views


class IsoDateConverter:
    """``YYYY-MM-DD`` path segments for the dated briefing routes.

    Matching the shape in the URL rather than parsing it in the view means a
    malformed date simply fails to resolve (a 404) instead of reaching the ORM as
    an invalid ``DateField`` lookup.
    """

    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> date:
        return datetime.strptime(value, "%Y-%m-%d").date()

    def to_url(self, value) -> str:
        return value.isoformat() if isinstance(value, date) else str(value)


register_converter(IsoDateConverter, "isodate")

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
    # Briefing history (the Reports page): the dated index, then one day's full
    # envelope. The index carries no bodies so it stays cheap over the window.
    path("briefings/", views.BriefingHistoryView.as_view(), name="briefings"),
    path("briefings", views.BriefingHistoryView.as_view()),
    path(
        "briefings/<isodate:on>/",
        views.BriefingDetailView.as_view(),
        name="briefing-detail",
    ),
    path("briefings/<isodate:on>", views.BriefingDetailView.as_view()),
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
    # Static hover copy for conference rank badges + trust tiers (plan Phase 9).
    # Not a feed: one small, cacheable table, fetched once rather than repeated
    # on every conference row.
    path(
        "opportunities/ranking-reference/",
        views.RankingReferenceView.as_view(),
        name="ranking-reference",
    ),
    path(
        "opportunities/ranking-reference",
        views.RankingReferenceView.as_view(),
    ),
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
    # Manual ignore: hide one item from this reader's own feeds (and undo).
    path(
        "opportunities/ignore/",
        views.IgnoreItemView.as_view(),
        name="opportunity-ignore",
    ),
    path("opportunities/ignore", views.IgnoreItemView.as_view()),
    path(
        "opportunities/ignore/<uuid:content_id>/",
        views.IgnoreItemView.as_view(),
        name="opportunity-unignore",
    ),
    path(
        "opportunities/ignore/<uuid:content_id>",
        views.IgnoreItemView.as_view(),
    ),
    path(
        "opportunities/ignored/",
        views.IgnoredItemsView.as_view(),
        name="opportunities-ignored",
    ),
    path("opportunities/ignored", views.IgnoredItemsView.as_view()),
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
    # A lab's retained briefing history, then one dated lab briefing.
    path(
        "labs/<slug:slug>/briefings/",
        views.LabBriefingHistoryView.as_view(),
        name="lab-briefings",
    ),
    path("labs/<slug:slug>/briefings", views.LabBriefingHistoryView.as_view()),
    path(
        "labs/<slug:slug>/briefings/<isodate:on>/",
        views.LabBriefingDetailView.as_view(),
        name="lab-briefing-detail",
    ),
    path(
        "labs/<slug:slug>/briefings/<isodate:on>",
        views.LabBriefingDetailView.as_view(),
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
    # What Mylo thinks the reader's project state should say, and their answer.
    path(
        "reflections/",
        views.ReflectionProposalsView.as_view(),
        name="reflection-proposals",
    ),
    path("reflections", views.ReflectionProposalsView.as_view()),
    path(
        "reflections/<uuid:pk>/action/",
        views.ReflectionProposalActionView.as_view(),
        name="reflection-proposal-action",
    ),
    path(
        "reflections/<uuid:pk>/action",
        views.ReflectionProposalActionView.as_view(),
    ),
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
    # "May I set a reminder here?" — the paid-plan + Discord-sync gate the UI reads
    # to lock the bell, computed by the same module the create path enforces with.
    path(
        "reminders/access/",
        reminders_views.ReminderAccessView.as_view(),
        name="reminder-access",
    ),
    path("reminders/access", reminders_views.ReminderAccessView.as_view()),
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
    # Who a lab alert may tag: roles, members, @everyone (manager-only).
    path(
        "reminders/lab-mention-targets/",
        reminders_views.LabMentionTargetsView.as_view(),
        name="reminder-lab-mention-targets",
    ),
    path(
        "reminders/lab-mention-targets",
        reminders_views.LabMentionTargetsView.as_view(),
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
    # Opportunity announcements (plan 20261105-mylo-opportunity-announcements).
    *[
        path(route, view.as_view(), **({"name": name} if slash else {}))
        for route_base, view, name in (
            ("announcements", announcement_views.AnnouncementsView, "announcements"),
            (
                "announcements/settings",
                announcement_views.AnnouncementSettingsView,
                "announcement-settings",
            ),
            (
                "announcements/test",
                announcement_views.AnnouncementTestView,
                "announcement-test",
            ),
            (
                "announcements/create-channels",
                announcement_views.AnnouncementCreateChannelsView,
                "announcement-create-channels",
            ),
            (
                "announcements/link-click",
                announcement_views.LinkClickView,
                "announcement-link-click",
            ),
            (
                "announcements/department-opportunities",
                announcement_views.DepartmentOpportunitiesView,
                "announcement-department-opportunities",
            ),
        )
        for slash, route in ((True, f"{route_base}/"), (False, route_base))
    ],
]

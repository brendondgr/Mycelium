"""Discord integration routes, mounted under /api/integrations/.

Both slash and no-slash variants for every POST-able route: the browser reaches
these through the Next `/api` proxy, which strips the trailing slash, and Django's
APPEND_SLASH cannot redirect an unsafe method. The OAuth callbacks are hit directly
by Discord (browser redirect) at the exact registered redirect URI — no-slash, to
match DISCORD_OAUTH_REDIRECT_URI / DISCORD_GUILD_REDIRECT_URI defaults.
"""

from django.urls import path

from . import slack_views, views


def _both(route, view, name):
    v = view.as_view()
    return [path(f"{route}/", v, name=name), path(route, v, name=f"{name}-no-slash")]


urlpatterns = [
    *_both("discord/start", views.DiscordStartView, "discord-start"),
    *_both("discord/status", views.DiscordStatusView, "discord-status"),
    *_both("discord/probe", views.DiscordProbeView, "discord-probe"),
    *_both("discord/disconnect", views.DiscordDisconnectView, "discord-disconnect"),
    *_both(
        "discord/daily-report",
        views.DiscordDailyReportView,
        "discord-daily-report",
    ),
    *_both("discord/code", views.DiscordActivationCodeView, "discord-code"),
    *_both(
        "discord/lab-code", views.DiscordLabActivationCodeView, "discord-lab-code"
    ),
    *_both(
        "discord/guild/status", views.DiscordGuildStatusView, "discord-guild-status"
    ),
    *_both("discord/health", views.DiscordHealthView, "discord-health"),
    *_both("discord/guild/start", views.DiscordGuildStartView, "discord-guild-start"),
    # OAuth callbacks — Discord redirects the browser here (GET). No-slash form is
    # the canonical registered redirect URI.
    path(
        "discord/callback",
        views.DiscordCallbackView.as_view(),
        name="discord-callback",
    ),
    path("discord/callback/", views.DiscordCallbackView.as_view()),
    path(
        "discord/guild-callback",
        views.DiscordGuildCallbackView.as_view(),
        name="discord-guild-callback",
    ),
    path("discord/guild-callback/", views.DiscordGuildCallbackView.as_view()),
    # Slack (ambient Plan 11). The events and interactions URLs are what the
    # Slack app's configuration points at; the callback is its redirect URL.
    *_both("slack/events", slack_views.SlackEventsView, "slack-events"),
    *_both(
        "slack/interactions", slack_views.SlackInteractionsView, "slack-interactions"
    ),
    *_both("slack/install", slack_views.SlackInstallView, "slack-install"),
    path(
        "slack/oauth/callback",
        slack_views.SlackOAuthCallbackView.as_view(),
        name="slack-callback",
    ),
    path("slack/oauth/callback/", slack_views.SlackOAuthCallbackView.as_view()),
    *_both("slack/link-code", slack_views.SlackLinkCodeView, "slack-link-code"),
    *_both("slack/lab-code", slack_views.SlackLabCodeView, "slack-lab-code"),
    *_both("slack/status", slack_views.SlackStatusView, "slack-status"),
    *_both("slack/unlink", slack_views.SlackUnlinkView, "slack-unlink"),
    *_both("slack/listening", slack_views.SlackListeningView, "slack-listening"),
]

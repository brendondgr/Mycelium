"""The delivery tool: what people see and do with what was ranked for them.

Standard library and spec imports only (see tools/README.md).
"""

from tools._framework.spec import Mount, Setting, Stage, Tool


def _s(key, kind, default, help_, env):
    """A setting whose environment variable and Django name are the same."""
    return Setting(key, kind, default, help_, env=env, django=env)


class DeliveryTool(Tool):
    name = "delivery"
    summary = (
        "Puts what was ranked in front of people: the feeds' API, saves and "
        "collections, project shares, the daily and weekly reports, reminders, "
        "notifications, project alerts, Discord and Slack delivery, and "
        "opportunity announcements."
    )
    depends_on = ("retrieval", "recommendation")
    #: The platform (Mylo's Discord commands, project pages, the ambient
    #: ledger) still calls into this code; see platform_imports.txt.
    core = True
    exports = (
        "read",
        "service",
        "events",
        # Imported directly from outside this tool today (the boundary test
        # checks every such import is listed here). New code uses the doors.
        "announce",
        "announcement_actions",
        "announcement_links",
        "announcement_setup",
        "collaboration",
        "delivery_failures",
        "discord_announcements",
        "discord_commands",
        "fanout",
        "guards",
        "matchers",
        "models",
        "reminders_discord",
        "run_analytics",
        "serializers",
        "timeline_settings",
    )
    settings = (
        _s("briefing_retention_days", "int", 90,
           "Days a daily briefing is kept before the nightly prune.",
           "BRIEFING_RETENTION_DAYS"),
        _s("opportunity_feed_max", "int", 250,
           "Most opportunities an opportunity feed returns.", "OPPORTUNITY_FEED_MAX"),
        _s("fanout_cosine_floor", "float", 0.35,
           "Similarity a shared item needs to be suggested to another project "
           "member.", "FANOUT_COSINE_FLOOR"),
        _s("fanout_async", "bool", False,
           "Run the share fan-out on Celery instead of in the request.",
           "FANOUT_ASYNC"),
        _s("high_signal_floor", "int", 90,
           "Match percent an item needs for an out-of-band high-signal message.",
           "HIGH_SIGNAL_FLOOR"),
        _s("high_signal_weekly_cap", "int", 2,
           "High-signal messages per person per week.", "HIGH_SIGNAL_WEEKLY_CAP"),
        _s("high_signal_deadline_min_days", "int", 7,
           "High-signal opportunities must close at least this many days out.",
           "HIGH_SIGNAL_DEADLINE_MIN_DAYS"),
        _s("high_signal_deadline_max_days", "int", 120,
           "...and at most this many.", "HIGH_SIGNAL_DEADLINE_MAX_DAYS"),
        _s("project_alert_overlap_threshold", "float", 0.62,
           "Project alerts: similarity for an overlapping paper.",
           "PROJECT_ALERT_OVERLAP_THRESHOLD"),
        _s("project_alert_blocker_threshold", "float", 0.58,
           "Project alerts: similarity for a paper that addresses a blocker.",
           "PROJECT_ALERT_BLOCKER_THRESHOLD"),
        _s("project_alert_slot_threshold", "float", 0.55,
           "Project alerts: similarity for a call that fits a team gap.",
           "PROJECT_ALERT_SLOT_THRESHOLD"),
        _s("project_alert_daily_cap", "int", 3,
           "Project alerts per project per day.", "PROJECT_ALERT_DAILY_CAP"),
        _s("run_analytics_retention_days", "int", 90,
           "Days nightly-run analytics are kept.", "RUN_ANALYTICS_RETENTION_DAYS"),
    )
    #: The feeds, saves, reports, reminders and announcements API, at the
    #: prefix and position its include always had.
    mounts = (Mount("api/", after="apps.research.urls"),)
    stages = (
        Stage("run_reminder_tick", "remind", "Firing due deadline reminders…"),
        Stage("prune_briefings", "prune",
              "Pruning daily briefings past the retention window…",
              after=("prune_opportunities",)),
        Stage("evaluate_project_alerts", "alert",
              "Deciding what today changes for each project…"),
        Stage("announce_opportunities", "announce",
              "Announcing newly fitting grants, fellowships and conferences…"),
        Stage("announce_opportunity_updates", "announce",
              "Updating announced opportunities and the closing-soon lists…"),
        Stage("generate_daily_briefing", "brief",
              "Writing each user's and lab's daily briefing…"),
        Stage("send_daily_discord_reports", "deliver",
              "DMing each linked user their daily PDF report…"),
        Stage("send_lab_digests", "deliver",
              "Posting each lab's digest to its Discord updates channel…"),
        Stage("generate_weekly_briefing", "weekly",
              "Writing the Monday weekly for each target…"),
        Stage("send_weekly_reports", "weekly",
              "Queueing the Monday weekly to Discord…"),
    )

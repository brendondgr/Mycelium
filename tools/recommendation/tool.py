"""The recommendation tool: rank and filter the corpus for every person, lab,
department and project.

Standard library and spec imports only (see tools/README.md).
"""

from tools._framework.spec import Beat, Setting, Stage, Tool


def _s(key, kind, default, help_, env):
    """A setting whose environment variable and Django name are the same."""
    return Setting(key, kind, default, help_, env=env, django=env)


class RecommendationTool(Tool):
    name = "recommendation"
    summary = (
        "Ranks the whole corpus for every person, lab, department and project "
        "against their profiles and interest clusters, takes each target's "
        "per-theme slate, and writes the model verdicts."
    )
    depends_on = ("retrieval",)
    #: The platform's delivery code and profile pages read slates and scores
    #: on every request; it cannot run without this tool until delivery moves.
    core = True
    exports = (
        "read",
        "service",
        "events",
        # Imported directly from outside this tool today (the boundary test
        # checks every such import is listed here). New code uses the doors.
        "cluster_fit",
        "clustering",
        "comprehension",
        "explorations",
        "fellowship_bands",
        "fellowships",
        "fusion",
        "interests_query",
        "member_fit",
        "models",
        "onboarding_match",
        "opportunities",
        "opportunity_llm",
        "pipeline",
        "ranking",
        "refitting",
        "scan_status",
        "slates",
        "targets",
        "tasks",
        "team_profile",
        "theme_run",
        "top_feed",
        "typesafe_rerank",
        "understanding",
        "vectors",
        "verdicts",
    )
    settings = (
        # Papers.
        _s("area_focus_weight", "float", 0.25,
           "Weight of a paper's focus-area similarity in its ranking.",
           "AREA_FOCUS_WEIGHT"),
        _s("paper_match_threshold", "float", 0.5,
           "Best transformer cosine a paper needs to be surfaced.",
           "PAPER_MATCH_THRESHOLD"),
        _s("paper_match_max_surface", "int", 250,
           "Backstop cap on surfaced papers per target.", "PAPER_MATCH_MAX_SURFACE"),
        _s("paper_min_match_percent", "int", 60,
           "Model score below which a paper stays off the feed.",
           "PAPER_MIN_MATCH_PERCENT"),
        _s("report_top_n", "int", 25, "Papers per theme in a target's slate.",
           "REPORT_TOP_N"),
        _s("paper_cluster_top_n", "int", 0,
           "Per-cluster paper cap (0: the slate depth decides).",
           "PAPER_CLUSTER_TOP_N"),
        _s("cluster_admit_frac", "float", 0.5,
           "Per-cluster admission: fraction of the cluster's best score.",
           "CLUSTER_ADMIT_FRAC"),
        _s("cluster_admit_hard_floor", "float", 0.35,
           "Per-cluster admission: absolute floor.", "CLUSTER_ADMIT_HARD_FLOOR"),
        _s("cluster_fit_batch", "int", 12, "Items per model write-up call.",
           "CLUSTER_FIT_BATCH"),
        _s("paper_onboarding_min_high_quality", "int", 30,
           "High-quality papers a new user's first feed aims for.",
           "PAPER_ONBOARDING_MIN_HIGH_QUALITY"),
        # Opportunities.
        _s("grant_match_threshold", "float", 0.4,
           "Embedding match a grant needs to be scored.", "GRANT_MATCH_THRESHOLD"),
        _s("conference_match_threshold", "float", 0.4,
           "Embedding match a conference needs to be scored.",
           "CONFERENCE_MATCH_THRESHOLD"),
        _s("fellowship_fit_threshold", "float", 0.0,
           "Research-fit floor for an eligible fellowship.",
           "FELLOWSHIP_FIT_THRESHOLD"),
        _s("fellowship_match_threshold", "float", 0.4,
           "Embedding match a fellowship needs to be scored.",
           "FELLOWSHIP_MATCH_THRESHOLD"),
        _s("fellowship_withhold_unverified", "bool", False,
           "Hide fellowships whose eligibility could not be verified.",
           "FELLOWSHIP_WITHHOLD_UNVERIFIED"),
        _s("opportunity_match_max_surface", "int", 250,
           "Backstop cap on surfaced opportunities per target.",
           "OPPORTUNITY_MATCH_MAX_SURFACE"),
        _s("opportunity_min_match_percent", "int", 60,
           "Model score below which an opportunity stays off the feed.",
           "OPPORTUNITY_MIN_MATCH_PERCENT"),
        # Who an item is for, and team profiles.
        _s("member_fit_cosine_floor", "float", 0.35,
           "Similarity a lab member needs to be named as who an item is for.",
           "MEMBER_FIT_COSINE_FLOOR"),
        _s("member_fit_max_members", "int", 3, "Members named per item.",
           "MEMBER_FIT_MAX_MEMBERS"),
        _s("project_profile_focus_weight", "float", 1.0,
           "Team profile: weight of the project's stated focus.",
           "PROJECT_PROFILE_FOCUS_WEIGHT"),
        _s("project_profile_member_weight", "float", 0.6,
           "Team profile: weight of the members' profiles.",
           "PROJECT_PROFILE_MEMBER_WEIGHT"),
        _s("project_profile_engagement_weight", "float", 0.4,
           "Team profile: weight of what the team engaged with.",
           "PROJECT_PROFILE_ENGAGEMENT_WEIGHT"),
        _s("project_profile_halflife_days", "float", 90.0,
           "Team profile: half-life of an engagement event, in days.",
           "PROJECT_PROFILE_HALFLIFE_DAYS"),
        Setting("team_profile_hour", "int", 3,
                "Hour (0-23) the nightly team-profile recompute runs on Beat.",
                env="CELERY_TEAM_PROFILE_HOUR"),
    )
    stages = (
        Stage("run_daily_suggestions", "rank",
              "Searching and ranking research papers for all targets…"),
        Stage("run_daily_opportunities", "rank",
              "Ranking every grant/conference/fellowship for all targets…",
              args=("--no-prune",)),
    )
    beat = (
        # Recompute every project's team-relevance signal nightly, so engagement
        # that accrued during the day shapes the next day's recommendations.
        Beat("recompute-project-profiles", "apps.content.recompute_project_profiles",
             kwargs={"hour": "setting:team_profile_hour", "minute": 0}),
    )
    subscribes = {
        "retrieval.items_merging": "tools.recommendation.handlers:repoint_scores",
    }

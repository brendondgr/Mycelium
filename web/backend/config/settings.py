import re
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

env = environ.FileAwareEnv(DEBUG=(bool, False))

environ.Env.read_env(ROOT_DIR.parent / ".env")
# Also fold in the Mylo gateway's env so the *one* bot identity is shared: the
# bot TOKEN (`DISCORD_API_KEY`) and the activation/error channel ids live only in
# `.env-mylo`. Without this, Django (and every in-process Django bootstrap — the
# Mylo gateway serving `/setup`, the daily run) sees an empty `DISCORD_BOT_TOKEN`,
# so every Discord REST call is skipped as "unreachable" and `/setup` wrongly
# blames a channel permission overwrite. `read_env` is setdefault-style, so a real
# process env var or a value already loaded from `.env` still wins.
environ.Env.read_env(ROOT_DIR.parent / ".env-mylo")



def env_str(name: str, default: str = "") -> str:
    """Read an env var, treating blank/whitespace as unset.

    compose passes optional URLs through as `${VAR:-}`, which arrives as an
    empty string rather than an absent variable; plain `env(...)` would take
    that empty value over the default and hand out URLs like `/login`.
    """
    return (env(name, default="") or "").strip() or default


# The external hostname this stack is served at (Cloudflare tunnel, reverse
# proxy, real domain) — the single knob for public routing. Every absolute URL
# Django hands to a browser derives from PUBLIC_BASE_URL, so nothing sends a
# visitor on the public host back to localhost. Assumed HTTPS, since that is
# what a tunnel or public proxy terminates.
PUBLIC_HOSTNAME = env_str("PUBLIC_HOSTNAME")
PUBLIC_BASE_URL = (
    f"https://{PUBLIC_HOSTNAME}" if PUBLIC_HOSTNAME else "http://localhost:11050"
)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-dev-only")
DEBUG = env("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)
# Setting PUBLIC_HOSTNAME alone is enough to be reachable there: an explicit
# DJANGO_ALLOWED_HOSTS left over from local-only work would otherwise 400 every
# proxied request with DisallowedHost.
if PUBLIC_HOSTNAME and PUBLIC_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(PUBLIC_HOSTNAME)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Postgres full-text search + trigram support for apps.content.search
    # (SearchVectorField, SearchRank, TrigramWordSimilarity). No-op feature-wise
    # on SQLite; the search path is Postgres-only and guarded accordingly.
    "django.contrib.postgres",
    "corsheaders",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.research",
    "apps.content",
    "apps.billing",
    "apps.scraper",
    "apps.integrations",
    "apps.adminpanel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.debug_middleware.CsrfDebugMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = env.list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    default=["http://localhost:11050", "http://localhost:11250"],
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:11050", "http://localhost:11250"],
)

# Same rule as ALLOWED_HOSTS: the public origin is always trusted when
# PUBLIC_HOSTNAME is set, so a login POST from the public host is not rejected
# as a CSRF failure just because the configured lists still say localhost.
if PUBLIC_HOSTNAME:
    for _origin_list in (CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS):
        if PUBLIC_BASE_URL not in _origin_list:
            _origin_list.append(PUBLIC_BASE_URL)

# Namespace the auth cookies. Browsers key cookies by domain but NOT by port, so
# several Django apps on `localhost:<port>` share one cookie jar and Django's
# default `sessionid`/`csrftoken` names collide — a neighbouring app overwrites
# Mycelium's session cookie and every authenticated request then 403s. Distinct
# names isolate Mycelium's session + CSRF cookies from any other local app.
SESSION_COOKIE_NAME = env("DJANGO_SESSION_COOKIE_NAME", default="mycelium_sessionid")
CSRF_COOKIE_NAME = env("DJANGO_CSRF_COOKIE_NAME", default="mycelium_csrftoken")

# Every request reaches Django through the nginx gateway (and usually a tunnel or
# public proxy in front of that), so the socket Django sees is always plain HTTP.
# Without this, `request.is_secure()` and `request.build_absolute_uri()` would call
# a public HTTPS site "http://" — which matters because the Discord OAuth callback
# is now built from the incoming request and must match the registered URI exactly.
# nginx always overwrites X-Forwarded-Proto, so a client cannot forge it.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    # Per-endpoint throttles opt in by scope; registration caps anonymous
    # account creation so the open AllowAny endpoint can't be hammered.
    "DEFAULT_THROTTLE_RATES": {
        "register": env("DJANGO_REGISTER_THROTTLE_RATE", default="20/hour"),
    },
}

# Sign-up gate: registration is invite-only, so a new account must carry a valid
# verification code. One shared code is live at a time (rotate it by setting the
# env var) and it is compared in constant time.
#
# Brute-force policy: 3 consecutive wrong codes from the same client → a 1-hour
# *shadow* ban. During the ban every attempt gets the same generic "code is not
# valid" answer as a plain miss, so a prober cannot tell a wrong code from a
# blocked one — and a correct code is refused too. The counters live in Redis
# (apps.accounts.signup_gate) so a ban survives a web restart and is shared
# across processes.
SIGNUP_ACCESS_CODE = env_str("SIGNUP_ACCESS_CODE", "251253")
SIGNUP_CODE_MAX_FAILURES = env.int("SIGNUP_CODE_MAX_FAILURES", default=3)
SIGNUP_CODE_FAILURE_WINDOW_SECONDS = env.int(
    "SIGNUP_CODE_FAILURE_WINDOW_SECONDS", default=3600
)
SIGNUP_CODE_LOCKOUT_SECONDS = env.int("SIGNUP_CODE_LOCKOUT_SECONDS", default=3600)

# Email: console backend in dev (messages print to the runserver console). A real
# transactional provider is wired in via this env var for non-dev environments.
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

CELERY_BROKER_URL = env(
    "CELERY_BROKER_URL",
    default=env("REDIS_URL", default="redis://localhost:11550/0"),
)
CELERY_RESULT_BACKEND = env(
    "CELERY_RESULT_BACKEND",
    default="redis://localhost:11550/1",
)

# Scheduled background work. Celery Beat (the `beat` compose service) reads this
# and enqueues the task on the worker. The hour is UTC (USE_TZ / TIME_ZONE above).
#
# NOTE: the daily research + opportunity run is NOT scheduled here. It now runs on
# the host via `manual_all.py` (the `mylo-daily.timer` systemd unit), because that
# flow includes the Illinois Fellowship Finder scrape, which needs host-only
# Playwright the backend container does not have (the open-source grant/conference
# collector itself is pure HTTP and runs in-container — see
# docs/plans/open-opportunity-collector.md D6). The `run_daily_suggestions` /
# `run_daily_opportunities` tasks and management commands still exist and are
# invoked by `manual_all.py`; only their in-container schedule moved. Keep
# team-profile recompute on Beat — it has no host dependency.
CELERY_BEAT_SCHEDULE = {
    # Feature D: recompute every project's team-relevance signal nightly, so
    # engagement that accrued during the day shapes the next day's recommendations.
    "recompute-project-profiles": {
        "task": "apps.content.recompute_project_profiles",
        "schedule": crontab(
            hour=env.int("CELERY_TEAM_PROFILE_HOUR", default=3), minute=0
        ),
    },
    # Discord reconciliation (apps.integrations): the HTTP-only tradeoff for the
    # absent gateway GUILD_DELETE/deauthorize events — mark kicked guilds, refresh
    # or revoke lapsing OAuth tokens. No host dependency (pure Discord REST), so it
    # stays on Beat. Also runnable on the host via `manage.py reconcile_discord`.
    "reconcile-discord": {
        "task": "apps.integrations.reconcile_discord",
        "schedule": crontab(
            hour=env.int("DISCORD_RECONCILE_HOUR", default=4), minute=0
        ),
    },
    # The outbound Discord queue. Every minute, because the point of the queue is
    # that a message delayed by an outage arrives shortly after it clears — a slower
    # cadence would just move the latency somewhere the user notices. The task holds
    # no retry state of its own (each row carries its own next_attempt_at), so a
    # missed run costs a minute, not a message.
    "drain-discord-outbox": {
        "task": "apps.integrations.drain_outbox",
        "schedule": crontab(minute="*"),
    },
    # Weekly clean-up of delivered outbox rows and the report PDFs they carried.
    # Sunday, well away from the daily run and the other sweeps.
    "purge-discord-outbox": {
        "task": "apps.integrations.purge_outbox",
        "schedule": crontab(day_of_week=0, hour=5, minute=30),
    },
}

# How many per-(user, area) grant/conference LLM scoring calls run concurrently
# in the daily opportunity batch. The model call is the slow step, so scoring
# units one at a time dominates the runtime; the endpoint handles many at once.
OPPORTUNITY_LLM_CONCURRENCY = env.int("OPPORTUNITY_LLM_CONCURRENCY", default=12)

# Where the daily suggestion run writes its verbose, timestamped log (one file
# per run). Under the repo's data/ dir by default so it is readable on the host.
#
# Every data path below reads through `env_str`, not `env`: `.env.example` is an
# env_file for the backend and worker, so a key listed there with no value arrives
# as an empty string, and plain `env(...)` takes that over the default. An empty
# path then becomes `Path("")` — which is `Path(".")`, the process working
# directory — so the artifact silently lands in the repo root, or the write fails
# outright with "Is a directory". These are the paths the host runner reads back
# across the bind mount, so a blank one breaks the seam rather than just moving a
# file.
DAILY_SUGGESTIONS_LOG_DIR = env_str(
    "DAILY_SUGGESTIONS_LOG_DIR",
    str(ROOT_DIR.parent / "data" / "logs" / "daily-suggestions"),
)

# The nightly internal analytics artifacts. Both live under the repo's data/ dir
# because the *host* runner reads them: `manual_all.py` builds its Discord summary
# from the JSON and attaches the PDF, and it has neither Django nor a database.
# Keep these paths in step with `mylo/analytics.py`, the reader on the other side.
RUN_ANALYTICS_JSON_PATH = env_str(
    "RUN_ANALYTICS_JSON_PATH",
    str(ROOT_DIR.parent / "data" / "logs" / "mylo-run-analytics.json"),
)
RUN_ANALYTICS_PDF_DIR = env_str(
    "RUN_ANALYTICS_PDF_DIR",
    str(ROOT_DIR.parent / "data" / "analytics"),
)
# One report a day, kept forever, is a slow disk leak. The command sweeps its own
# directory rather than adding another prune stage to the nightly chain.
RUN_ANALYTICS_RETENTION_DAYS = env.int("RUN_ANALYTICS_RETENTION_DAYS", default=90)

NEO4J_URI = env("NEO4J_URI", default="bolt://localhost:11750")
NEO4J_USERNAME = env("NEO4J_USERNAME", default="neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", default="")

S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="")
S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID", default="")
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY", default="")
S3_BUCKET_NAME = env("S3_BUCKET_NAME", default="")

# LLM (OpenAI-compatible endpoint, e.g. a vLLM server). The base URL points at
# any OpenAI-compatible `/v1` API; the API key is required by the OpenAI SDK but
# is ignored by vLLM (use "EMPTY"). Reasoning controls assume the server already
# has its reasoning parser and tooling configured (see apps/core/llm.py).
LLM_BASE_URL = env("LLM_BASE_URL", default="http://localhost:8001/v1")
LLM_API_KEY = env("LLM_API_KEY", default="EMPTY")
LLM_MODEL = env("LLM_MODEL", default="")
LLM_TIMEOUT = env.float("LLM_TIMEOUT", default=60.0)
# How long to wait to *reach* the server, as opposed to waiting for it to answer.
# Generation is slow, so LLM_TIMEOUT is generous; a connect that takes seconds
# means the endpoint is unreachable, and every LLM seam has a deterministic
# fallback that should be reached quickly instead of after the full timeout.
LLM_CONNECT_TIMEOUT = env.float("LLM_CONNECT_TIMEOUT", default=5.0)
# SDK-level retries. Default 0: retrying an unreachable endpoint multiplies the
# wait before the fallback (the SDK's own default of 2 turns one dead call into
# three timeouts).
LLM_MAX_RETRIES = env.int("LLM_MAX_RETRIES", default=0)
LLM_TEMPERATURE = env.float("LLM_TEMPERATURE", default=0.2)
LLM_MAX_TOKENS = env.int("LLM_MAX_TOKENS", default=1024)
# Default reasoning level: one of "none", "low", "medium", "high".
LLM_REASONING = env("LLM_REASONING", default="medium")
# How reasoning levels are sent to the server: "effort" maps to vLLM's
# `reasoning_effort`; "thinking" toggles `chat_template_kwargs.enable_thinking`.
LLM_REASONING_STYLE = env("LLM_REASONING_STYLE", default="effort")
# Thinking-token budget for the harder reasoning tasks (cluster composition):
# sent as `thinking_token_budget` in the request's extra_body so the server
# reserves room to reason before answering. Keep >= 512 (see clusters.py).
LLM_THINKING_BUDGET = env.int("LLM_THINKING_BUDGET", default=512)

# Daily-suggestion ranking (apps.content.ranking). Weight applied to a paper's
# research-focus overlap when re-ranking retrieved papers: blended score =
# similarity + AREA_FOCUS_WEIGHT * focus_overlap. 0 disables the focus boost.
AREA_FOCUS_WEIGHT = env.float("AREA_FOCUS_WEIGHT", default=0.25)

# Daily research-paper feed sizing (apps.content.pipeline). The Research Papers
# feed is no longer a fixed top-N: a paper is surfaced only when its transformer
# (embedding) cosine match to the researcher's interests clears PAPER_MATCH_THRESHOLD
# — a variable-length list whose size the reader is told ("N papers met the
# threshold"). It starts deliberately high so the feed is precise; lower it toward
# 0 to widen the feed. Only the top DEFAULT_SUGGESTIONS of the survivors still go to
# the language model for a bespoke percent match. PAPER_MATCH_MAX_SURFACE is a
# backstop cap so a pathological run can never persist an unbounded list. Both are
# expressed as the raw cosine similarity fraction in [0, 1] (shown as a % in the UI),
# matching the FANOUT_COSINE_FLOOR convention. Papers only — grant/conference/
# fellowship matching is unaffected.
PAPER_MATCH_THRESHOLD = env.float("PAPER_MATCH_THRESHOLD", default=0.5)
PAPER_MATCH_MAX_SURFACE = env.int("PAPER_MATCH_MAX_SURFACE", default=250)

# Nightly runs carry forward a paper's prior LLM verdict instead of re-scoring it
# (apps.content.pipeline / .suggest), so a researcher's match% doesn't flap night
# to night and the freed LLM slots go to papers never scored, new ones first. A
# paper the model scores below PAPER_MIN_MATCH_PERCENT is persisted (so the
# carry-forward store remembers it and never re-sends it) but hidden from the feed
# (``suggested=False``) rather than surfaced with a low score.
PAPER_MIN_MATCH_PERCENT = env.int("PAPER_MIN_MATCH_PERCENT", default=60)

# How many items make up a target's slate per category — the "Top 25" the daily
# report is built from (apps.content.top_feed). The report shows the slate and calls
# new whatever entered it since the last run, so this number is both how much a
# reader is shown and how far down the ranking a promotion still counts as news.
# There is deliberately no second relevance floor on top: the feed's own embedding
# threshold (PAPER_MATCH_THRESHOLD, GRANT_MATCH_THRESHOLD, …) already decides what
# is good enough to be in the feed at all, and a second opinion about the top of
# that list only ever made the report quietly shorter than it claimed to be.
REPORT_TOP_N = env.int("REPORT_TOP_N", default=25)

# Papers an institutional target (lab / lab project) draws from EACH of its
# interest clusters (apps.content.pipeline.recommend_for_target). A lab's areas are
# broad theme names rather than a person's specific keywords, so one theme's
# vocabulary consistently sits closer to the day's literature; ranked globally it
# took the whole model budget and the lab's other themes read as empty. Each theme
# now contributes its own best N, all of which are scored by the model and shown —
# a slate member is not withheld by PAPER_MIN_MATCH_PERCENT, since this run is what
# chose it. Left at 0 (the default) the depth comes from
# ``apps.content.slates.slate_depth`` instead, which is where the per-category
# geometry now lives; set it only to override that for papers specifically.
PAPER_CLUSTER_TOP_N = env.int("PAPER_CLUSTER_TOP_N", default=0)

# Per-cluster admission (apps.content.admission). A candidate is admitted when it
# clears PAPER_MATCH_THRESHOLD *or* reaches CLUSTER_ADMIT_FRAC of its own theme's
# best score — the second is what stops a theme whose vocabulary sits further from
# the corpus being excluded wholesale. CLUSTER_ADMIT_HARD_FLOOR sits under both, so
# a theme with nothing genuinely relevant admits nothing rather than its ten
# least-irrelevant candidates. It is not optional; do not set it to 0.
CLUSTER_ADMIT_FRAC = env.float("CLUSTER_ADMIT_FRAC", default=0.5)
CLUSTER_ADMIT_HARD_FLOOR = env.float("CLUSTER_ADMIT_HARD_FLOOR", default=0.35)

# Model write-ups per target per run (apps.content.cluster_fit). A run-safety cap,
# not a spend cap: the nightly batch is shared, so an unbounded spike for one
# reader who just redesigned their profile would degrade everyone else's report.
# Entrants are written first and whatever does not fit carries to the next run.
CLUSTER_WRITEUP_BUDGET = env.int("CLUSTER_WRITEUP_BUDGET", default=40)
CLUSTER_FIT_BATCH = env.int("CLUSTER_FIT_BATCH", default=12)

# Papers sign-up hybrid (apps.content.onboarding_match). A brand-new user is first
# matched against the latest gather batch already in the store (no live scan). If
# that yields at least PAPER_ONBOARDING_MIN_HIGH_QUALITY suggestions carrying a
# "read" verdict, those are shown; otherwise a
# background scan of the user's watch topics is kicked off and the Research Papers
# page shows a "scanning" state (a Redis flag, best-effort) until it lands.
# PAPER_SCAN_INFLIGHT_TTL bounds that flag so a dead scan can never wedge it on.
PAPER_ONBOARDING_MIN_HIGH_QUALITY = env.int(
    "PAPER_ONBOARDING_MIN_HIGH_QUALITY", default=30
)
PAPER_SCAN_INFLIGHT_TTL = env.int("PAPER_SCAN_INFLIGHT_TTL", default=1800)

# Opportunity feed sizing (apps.content.opportunities / .fellowships). Like the
# paper feed, grants/conferences/fellowships are no longer fixed top-N lists: an
# item is surfaced only when its match to the researcher clears the area's
# threshold, so the feed shows *all* sufficiently-related opportunities (however
# many that is), capped by OPPORTUNITY_MATCH_MAX_SURFACE as a backstop. Only the
# top items of each still go to the language model. GRANT/CONFERENCE thresholds are
# the transformer (embedding) cosine fraction in [0, 1] (start lower than papers —
# the goal is to widen a previously-capped feed). FELLOWSHIP_FIT_THRESHOLD is the
# rule engine's fit score in [0, 1] applied *after* the hard eligibility gate, so
# the default 0.0 surfaces every fellowship the user is actually eligible for.
# FELLOWSHIP_MATCH_THRESHOLD is the embedding-cosine relevance floor an eligible
# fellowship must clear to surface at all (mirrors GRANT/CONFERENCE_MATCH_THRESHOLD;
# 0 disables the relevance gate, keeping the old eligibility-only behaviour) — it
# only applies for researchers with a declared interest signal; users with none
# keep the pure rule-engine ranking.
GRANT_MATCH_THRESHOLD = env.float("GRANT_MATCH_THRESHOLD", default=0.4)
CONFERENCE_MATCH_THRESHOLD = env.float("CONFERENCE_MATCH_THRESHOLD", default=0.4)
FELLOWSHIP_FIT_THRESHOLD = env.float("FELLOWSHIP_FIT_THRESHOLD", default=0.0)
FELLOWSHIP_MATCH_THRESHOLD = env.float("FELLOWSHIP_MATCH_THRESHOLD", default=0.4)
OPPORTUNITY_MATCH_MAX_SURFACE = env.int("OPPORTUNITY_MATCH_MAX_SURFACE", default=250)

# A fellowship whose scraped facet buckets are all empty (a failed detail render,
# a missed selector) carries no eligibility information, so every facet test
# trivially passes it and it would otherwise match everybody. It is tiered
# "unverified" and labelled as unchecked instead. Withholding it entirely is the
# stricter option, off by default: a parse failure should not silently cost a
# researcher a real award.
FELLOWSHIP_WITHHOLD_UNVERIFIED = env.bool(
    "FELLOWSHIP_WITHHOLD_UNVERIFIED", default=False
)

# One-time, per-record extraction of the *prose* eligibility a facet cannot carry
# ("must have received the PhD within 24 months"). A deterministic pattern pass
# runs always; the language-model pass fills what the patterns miss and is what
# this switch turns off. Extraction happens at ingest and is carried forward on
# re-ingest, so the nightly run never pays for it twice.
FELLOWSHIP_CONSTRAINT_EXTRACTION = env.bool(
    "FELLOWSHIP_CONSTRAINT_EXTRACTION", default=True
)

# Opportunity feeds accumulate: the daily run scores only that day's *new* items and
# appends them, so a grant/conference/fellowship feed is the union of every run's
# matches (papers, by contrast, are fresh-only). OPPORTUNITY_FEED_MAX caps how many
# accumulated matches a feed returns, a payload backstop since an accumulating feed
# grows between prunes. Items still leave the feed when pruned at their deadline.
OPPORTUNITY_FEED_MAX = env.int("OPPORTUNITY_FEED_MAX", default=250)

# How long a *dateless* conference may go unseen by the collector before the
# nightly prune deletes it. A conference with no deadline and no event date is
# nothing a reader can act on, so it is hidden from feeds immediately
# (apps.content.liveness), but deleting it needs evidence the source has
# actually dropped it — otherwise a genuinely rolling call the source still
# lists every night would be deleted and re-created on the next run, losing its
# first_seen. `last_seen` is that evidence. Grants are unaffected: a dateless
# grant is a rolling call by design and never expires.
OPPORTUNITY_STALE_DAYS = env.int("OPPORTUNITY_STALE_DAYS", default=60)

# Same carry-forward + floor behaviour as papers (above), for grants / conferences /
# fellowships: an item the model scored below this stays in the carry-forward store
# (never re-sent to the model) but off the feed until it improves or ages out.
OPPORTUNITY_MIN_MATCH_PERCENT = env.int("OPPORTUNITY_MIN_MATCH_PERCENT", default=60)

# High-signal notification gate (apps.content.high_signal, reminders R7). A brutal
# floor: abstention is a feature — if nothing clears the bar, send nothing. An alert
# that fires most days is a digest, and digests are out of scope. HIGH_SIGNAL_FLOOR is
# a PLACEHOLDER pending shadow-mode calibration on the real RelevanceScore corpus
# (`manage.py high_signal_shadow`); do NOT trust the default 90 until it is measured
# (D-14). Delivery ships OFF (D-10: high-signal stays in-app-only for now; and it must
# not deliver on a guessed threshold) — flip HIGH_SIGNAL_DELIVERY_ENABLED only after
# calibration.
HIGH_SIGNAL_FLOOR = env.int("HIGH_SIGNAL_FLOOR", default=90)
HIGH_SIGNAL_WEEKLY_CAP = env.int("HIGH_SIGNAL_WEEKLY_CAP", default=2)
HIGH_SIGNAL_DEADLINE_MIN_DAYS = env.int("HIGH_SIGNAL_DEADLINE_MIN_DAYS", default=7)
HIGH_SIGNAL_DEADLINE_MAX_DAYS = env.int("HIGH_SIGNAL_DEADLINE_MAX_DAYS", default=120)
HIGH_SIGNAL_DELIVERY_ENABLED = env.bool("HIGH_SIGNAL_DELIVERY_ENABLED", default=False)

# How many days of written daily briefings the Reports page keeps (the
# `prune_briefings` stage of the daily run deletes anything older). Flat for every
# plan: only holders of the scheduled-reports feature are ever given a briefing, so
# there is nothing to retain on the free tier. Markdown only — the DM'd PDF is an
# outbox attachment and ages out with the outbox's own sweep.
BRIEFING_RETENTION_DAYS = env.int("BRIEFING_RETENTION_DAYS", default=90)

# Project collaboration (apps.content.collaboration). Per-action weight written on
# each RelevanceEvent — the weak relevance labels a future team-signal recompute
# reads. Positive for engagement, negative for rejection. Tunable so the eventual
# recompute can be calibrated without a migration; unknown actions fall back to 0.
RELEVANCE_EVENT_WEIGHTS = {
    "view": env.float("RELEVANCE_WEIGHT_VIEW", default=0.1),
    "open_external": env.float("RELEVANCE_WEIGHT_OPEN_EXTERNAL", default=0.3),
    "save": env.float("RELEVANCE_WEIGHT_SAVE", default=0.5),
    "share": env.float("RELEVANCE_WEIGHT_SHARE", default=0.7),
    "thumbs_up": env.float("RELEVANCE_WEIGHT_THUMBS_UP", default=1.0),
    "dismiss": env.float("RELEVANCE_WEIGHT_DISMISS", default=-0.3),
    "thumbs_down": env.float("RELEVANCE_WEIGHT_THUMBS_DOWN", default=-0.7),
}

# Project team-relevance signal (apps.content.team_profile — Feature D). The
# recomputed team vector blends the project's declared focus, its members' interest
# vectors, and their recent weighted engagement (each normalized before fusion);
# it is written to Project.embedding for the recommendation pipeline to read.
# Engagement decays with a half-life so stale clicks fade. Weights are relative.
PROJECT_PROFILE_FOCUS_WEIGHT = env.float("PROJECT_PROFILE_FOCUS_WEIGHT", default=1.0)
PROJECT_PROFILE_MEMBER_WEIGHT = env.float("PROJECT_PROFILE_MEMBER_WEIGHT", default=0.6)
PROJECT_PROFILE_ENGAGEMENT_WEIGHT = env.float(
    "PROJECT_PROFILE_ENGAGEMENT_WEIGHT", default=0.4
)
PROJECT_PROFILE_HALFLIFE_DAYS = env.float("PROJECT_PROFILE_HALFLIFE_DAYS", default=90.0)

# Cross-member relevance fan-out (apps.content.fanout — Feature F). A shared paper
# is suggested to a member when the normalized cosine between the item and the
# member's profile clears this floor; below-floor rows persist as audited
# abstentions, never sent. ``FANOUT_ASYNC`` routes the trigger through Celery
# instead of running inline in the share request (needs a running worker).
FANOUT_COSINE_FLOOR = env.float("FANOUT_COSINE_FLOOR", default=0.35)
FANOUT_ASYNC = env.bool("FANOUT_ASYNC", default=False)

# Per-item member recommendations (apps.content.member_fit) — the "who in this lab
# is this most applicable to?" layer on every lab/project feed. A member is a
# candidate when the cosine between the item and their own interest vector clears
# MEMBER_FIT_COSINE_FLOOR (the FANOUT_COSINE_FLOOR convention); at most
# MEMBER_FIT_MAX_MEMBERS are named per item, so a card stays readable in a large
# lab. Mylo writes the rationale for the strongest MEMBER_FIT_LLM_LIMIT items of
# each area (the digest's llm_limit convention); everything below carries a
# deterministic reason built from the overlap, and an unreachable model degrades
# the whole layer to that same deterministic ranking.
MEMBER_FIT_COSINE_FLOOR = env.float("MEMBER_FIT_COSINE_FLOOR", default=0.35)
MEMBER_FIT_MAX_MEMBERS = env.int("MEMBER_FIT_MAX_MEMBERS", default=3)
MEMBER_FIT_LLM_LIMIT = env.int("MEMBER_FIT_LLM_LIMIT", default=10)
# Recompute a project's team profile immediately when its membership changes.
TEAM_PROFILE_AUTORECOMPUTE = env.bool("TEAM_PROFILE_AUTORECOMPUTE", default=True)

# Unified search (apps.content.search) — the digest retrieval pipeline run
# query-first over the whole content corpus. Unlike the digest, search never
# abstains: it always returns the top-k and only flags low confidence as a UI
# cue. SEARCH_CANDIDATE_POOL bounds how deep the relevance ranking goes (the
# union of the lexical/semantic/fuzzy channels); pages slice within that pool so
# deep-page latency stays flat. SEARCH_LOW_CONFIDENCE_COSINE is the display
# threshold for the "low confidence" cue (top cosine below it), never a gate.
SEARCH_CANDIDATE_POOL = env.int("SEARCH_CANDIDATE_POOL", default=500)
SEARCH_PAGE_SIZE = env.int("SEARCH_PAGE_SIZE", default=20)
SEARCH_MAX_PAGE_SIZE = env.int("SEARCH_MAX_PAGE_SIZE", default=50)
SEARCH_LOW_CONFIDENCE_COSINE = env.float("SEARCH_LOW_CONFIDENCE_COSINE", default=0.35)
# SEARCH_SEMANTIC_FLOOR is the *inclusion* gate for the semantic (embedding)
# channel: a candidate whose cosine similarity to the query is below it is not
# admitted, so the far-field nearest-neighbours pgvector always returns no longer
# pad the pool with vaguely-related items. This is NOT abstention — the lexical
# and fuzzy channels still return every match, so a real term/typo hit always
# surfaces. Kept just below SEARCH_LOW_CONFIDENCE_COSINE so the [floor, cue) band
# still surfaces borderline items with the "low confidence" badge; raise it (e.g.
# 0.4) to trim more aggressively, set 0.0 to disable the gate.
SEARCH_SEMANTIC_FLOOR = env.float("SEARCH_SEMANTIC_FLOOR", default=0.30)
# Fuzzy (pg_trgm) channel: enabled, with its own bounded pool (typo recovery is a
# tail signal, so it need not scan as deep as the lexical/semantic pools).
SEARCH_FUZZY_ENABLED = env.bool("SEARCH_FUZZY_ENABLED", default=True)
SEARCH_FUZZY_POOL = env.int("SEARCH_FUZZY_POOL", default=200)

# The query-embedding cache (apps.content.query_embedding). A repeated search
# should skip the model call, so the normalized query → its vector is cached in
# Redis. It lives in a *dedicated* Redis db (never the Celery broker/result dbs),
# derived from REDIS_URL by swapping the db number so it is correct on both the
# host and inside the compose network. Best-effort: a Redis outage degrades to
# "embed every time", never an error.
_REDIS_URL = env("REDIS_URL", default="redis://localhost:11550/0")
SEARCH_CACHE_URL = env(
    "SEARCH_CACHE_URL", default=re.sub(r"/\d+$", "/2", _REDIS_URL)
)
SEARCH_CACHE_TTL = env.int("SEARCH_CACHE_TTL", default=3600)

# A small Redis-backed cache for the "paper scan in flight" flag, which the web
# process sets (at sign-up) and the Celery worker clears (when the scan lands), so
# it must be shared across processes — the default LocMemCache is per-process. All
# reads/writes are best-effort (apps.content.scan_status), so a Redis outage
# degrades to "no scanning state", never an error.
SCAN_CACHE_URL = env("SCAN_CACHE_URL", default=re.sub(r"/\d+$", "/3", _REDIS_URL))

# Ephemeral Discord-link state (apps.integrations): OAuth `state` nonces and the
# `/activate` failure counters / lockouts. It MUST be shared across processes and
# survive a bot restart — a lockout kept in process memory would reset on redeploy
# — so it lives in Redis, in its own db (never the Celery broker/result dbs), keyed
# to short TTLs. A Redis outage fails these lookups closed (see services.state).
DISCORD_CACHE_URL = env("DISCORD_CACHE_URL", default=re.sub(r"/\d+$", "/4", _REDIS_URL))

# Sign-up verification-code failure counters / shadow bans (apps.accounts
# .signup_gate). Same reasoning as the Discord cache: a ban kept in process memory
# would reset on redeploy and would not be seen by a sibling web process, so it
# lives in Redis in its own db. Reads fail *closed* (see signup_gate).
SIGNUP_CACHE_URL = env("SIGNUP_CACHE_URL", default=re.sub(r"/\d+$", "/5", _REDIS_URL))

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
    "search": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": SEARCH_CACHE_URL,
        "KEY_PREFIX": "mycelium_search",
        "TIMEOUT": SEARCH_CACHE_TTL,
    },
    "scan": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": SCAN_CACHE_URL,
        "KEY_PREFIX": "mycelium_scan",
        "TIMEOUT": PAPER_SCAN_INFLIGHT_TTL,
    },
    "discord": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": DISCORD_CACHE_URL,
        "KEY_PREFIX": "mycelium_discord",
        # No blanket TTL: every write sets its own (nonce 10 min, lockout 1 hr).
        "TIMEOUT": None,
    },
    "signup": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": SIGNUP_CACHE_URL,
        "KEY_PREFIX": "mycelium_signup",
        # No blanket TTL: the failure counter and the ban each set their own.
        "TIMEOUT": None,
    },
}

# Author-import sources (apps.accounts.intake). Keys are optional: OpenAlex works
# without one (a polite `mailto` is encouraged), and Semantic Scholar's key only
# raises rate limits. Google Scholar needs no key but the optional `scholarly`
# package (install the `scrapers` extra).
OPENALEX_API_KEY = env("OPEN_ALEX_API_KEY", default="")
OPENALEX_MAILTO = env("OPENALEX_MAILTO", default="")
SEMANTIC_SCHOLAR_API_KEY = env("SEMANTIC_SCHOLAR_API_KEY", default="")

# Literature scan (apps.scraper). PubMed's key is optional (it only raises the
# NCBI rate limit). The contact email is OpenAlex/NCBI etiquette; it falls back
# to OPENALEX_MAILTO. The embedding model matches the ResearchScraper reranker
# and runs via the optional `embeddings` extra (`uv sync --extra embeddings`).
PUBMED_API_KEY = env("PUBMED_API_KEY", default="")
SCRAPER_CONTACT_EMAIL = env("SCRAPER_CONTACT_EMAIL", default=OPENALEX_MAILTO)
SCRAPER_EMBEDDING_MODEL = env(
    "SCRAPER_EMBEDDING_MODEL", default="BAAI/bge-small-en-v1.5"
)

# Embedding device (apps.scraper.embedding). "auto" runs on a CUDA GPU whenever
# ONNX Runtime actually exposes CUDAExecutionProvider — which requires the GPU
# flavour of the extra (`uv sync --extra embeddings-gpu`) — and on the CPU
# otherwise. "cuda" demands the GPU (and warns, then falls back, if it is
# missing); "cpu" pins the CPU even on a GPU host, e.g. when the card is fully
# claimed by the local LLM. EMBEDDING_DEVICE_ID picks a card on a multi-GPU box.
# The batch sizes are handed to fastembed: a GPU is throughput-bound and wants a
# large batch, a CPU is latency-bound and wants a modest one.
EMBEDDING_DEVICE = env("EMBEDDING_DEVICE", default="auto")
EMBEDDING_DEVICE_ID = env("EMBEDDING_DEVICE_ID", default="")
EMBEDDING_BATCH_SIZE_CPU = env.int("EMBEDDING_BATCH_SIZE_CPU", default=64)
EMBEDDING_BATCH_SIZE_GPU = env.int("EMBEDDING_BATCH_SIZE_GPU", default=256)

# Cross-encoder rerank (apps.content.reranking). Reorders the head of the fused
# candidate list by reading query and document together, over the pool the
# pipeline already built — nothing about retrieval changes.
#
# Ships OFF. The evidence for it is a *preference*: three blinded reads by the
# product's own user (docs/research/experiments/EXP-2026-08-015 … -017) put this
# reranker over the deployed dense pool first in papers, grants and conferences,
# and at 5 wins / 3 ties / 0 losses once the pool was held constant. On
# LongEval-Sci the same model is significantly *harmful* on short queries and
# claim C-013 stands refuted, so this is not a measured improvement and Q-033 is
# still open. Turn it on deliberately, per environment.
#
# RERANK_MODEL is the one reranker any human has judged here; fastembed offers
# five others and none of them have been looked at (Q-021/Q-023).
# RERANK_DEVICE follows EMBEDDING_DEVICE when unset, so a GPU host is configured
# once for both models: "auto" uses CUDA whenever ONNX Runtime really exposes it,
# and a CUDA session that fails to build degrades to the CPU with a warning.
# RERANK_CONTENT_TYPES omits fellowships deliberately — on that corpus the
# query's domain word is boilerplate and this reranker was measured promoting
# medically-themed programmes with no topical connection (Q-031).
# RERANK_DEPTH is the depth every experiment used; RERANK_MAX_PAIRS bounds a
# multi-interest profile so a nightly run cannot become an afternoon.
RERANK_ENABLED = env.bool("RERANK_ENABLED", default=False)
RERANK_MODEL = env("RERANK_MODEL", default="Xenova/ms-marco-MiniLM-L-6-v2")
RERANK_DEVICE = env("RERANK_DEVICE", default="")
RERANK_DEVICE_ID = env("RERANK_DEVICE_ID", default="")
RERANK_DEPTH = env.int("RERANK_DEPTH", default=50)
RERANK_MAX_PAIRS = env.int("RERANK_MAX_PAIRS", default=400)
RERANK_BATCH_SIZE_CPU = env.int("RERANK_BATCH_SIZE_CPU", default=32)
RERANK_BATCH_SIZE_GPU = env.int("RERANK_BATCH_SIZE_GPU", default=128)
RERANK_CONTENT_TYPES = env.list(
    "RERANK_CONTENT_TYPES", default=["paper", "grant", "conference"]
)

# ---------------------------------------------------------------------------
# Discord integration (apps.integrations) — identity + lab linking.
#
# Mylo owns no data: every Discord-originated DB touch goes through Mycelium's
# ORM (apps.integrations.services.resolve is the single boundary). These are the
# *application* credentials for the one Discord app. The bot TOKEN is reused from
# the existing Mylo gateway env (`.env-mylo` → DISCORD_API_KEY) so there is one
# bot identity, not two; the OAuth client id/secret are new. Secrets stay in the
# environment — never persisted to the DB, never logged.
# ---------------------------------------------------------------------------
DISCORD_APP_ID = env("DISCORD_APP_ID", default="")
DISCORD_CLIENT_ID = env("DISCORD_CLIENT_ID", default="")
DISCORD_CLIENT_SECRET = env("DISCORD_CLIENT_SECRET", default="")
# The bot token. Read from the same var the Mylo gateway uses (mylo/config.py)
# so the OAuth REST calls (DM probe, guild reconcile) act as the same bot; falls
# back to DISCORD_BOT_TOKEN for parity with the plan's naming.
DISCORD_BOT_TOKEN = env(
    "DISCORD_API_KEY", default=env("DISCORD_BOT_TOKEN", default="")
)
# Fernet key for OAuth tokens at rest — distinct from the bot token. When unset
# (dev/tests) apps.integrations.fields derives a stable key from SECRET_KEY, so
# the encrypted field always works; production sets a real, rotated key here.
DISCORD_TOKEN_ENC_KEY = env("DISCORD_TOKEN_ENC_KEY", default="")

# Absolute origin for links Mylo writes into Discord messages (digests, nudges).
# Those are composed outside any HTTP request, so they cannot be derived from one
# and genuinely need a configured origin: PUBLIC_BASE_URL, or an explicit pin.
#
# One extra guard, because this origin leaves the building: a blank
# PUBLIC_HOSTNAME leaves PUBLIC_BASE_URL on its localhost default, and a lab's
# Discord channel then receives "http://localhost:11050/app/daily" — a link that
# works only on the operator's own machine, with nothing in the stack objecting.
# So when the resolved origin is a loopback host we substitute the deployment's
# public origin instead. An explicit DISCORD_APP_BASE_URL still wins outright,
# and nothing else in the app is affected — this only governs links written *into*
# Discord, never what a browser is redirected to.
PUBLIC_FALLBACK_HOSTNAME = env_str(
    "PUBLIC_FALLBACK_HOSTNAME", "mycelium.brendondgr.com"
)
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"})


def is_loopback_origin(url: str) -> bool:
    """Whether ``url``'s host is a loopback address (so it must not be published)."""
    host = re.sub(r"^[a-z]+://", "", str(url or "").strip(), flags=re.IGNORECASE)
    host = host.split("/", 1)[0]
    if host.startswith("["):  # bracketed IPv6 literal, e.g. [::1]:11050
        host = host.split("]", 1)[0] + "]"
    else:
        host = host.split(":", 1)[0]
    return host.casefold() in _LOOPBACK_HOSTS


def outbound_base_url(configured: str) -> str:
    """The origin safe to write into an outbound message, never a loopback one."""
    configured = str(configured or "").rstrip("/")
    if configured and not is_loopback_origin(configured):
        return configured
    if PUBLIC_FALLBACK_HOSTNAME:
        return f"https://{PUBLIC_FALLBACK_HOSTNAME}"
    return configured


DISCORD_APP_BASE_URL = outbound_base_url(
    env_str("DISCORD_APP_BASE_URL", PUBLIC_BASE_URL)
)

# The two OAuth callbacks are NOT configured here by default. OAuth2 forbids a
# relative redirect_uri, but the next best thing is to derive it per request from
# the origin the browser is actually on (apps.integrations.services.oauth), so the
# stack works at whatever hostname it is served at without re-pointing config —
# and a leftover localhost value can never send a public visitor to localhost.
# Set these only to PIN a fixed origin. Whatever they resolve to must be
# registered verbatim in the Discord app's OAuth2 redirect list, or Discord
# returns "Invalid OAuth2 redirect_uri"; with the derived form that means
# registering every public origin the portal is reachable at.
DISCORD_OAUTH_REDIRECT_URI = env_str("DISCORD_OAUTH_REDIRECT_URI")
DISCORD_GUILD_REDIRECT_URI = env_str("DISCORD_GUILD_REDIRECT_URI")
# Where the user lands back in the portal after a link attempt (success or error
# is carried as a query param). The frontend profile page reads it. Kept absolute
# because the Mylo gateway quotes it in DMs; the callback views redirect to its
# path alone, so the browser stays on the origin it arrived from.
DISCORD_PORTAL_RETURN_URL = env_str(
    "DISCORD_PORTAL_RETURN_URL", f"{DISCORD_APP_BASE_URL}/app/profile"
)
# Guild permissions integer requested on the bot install (Path C). The floor for
# *this* scope: View Channels (1<<10) + Send Messages (1<<11) + Embed Links
# (1<<14) = 19456. No Administrator / Manage Roles / Manage Channels.
DISCORD_INSTALL_PERMISSIONS = env("DISCORD_INSTALL_PERMISSIONS", default="19456")
# The ops sink channel (apps.integrations.services.errors). Reuses the same
# ERROR_CHANNEL the Mylo daily run posts to (mylo/config.py). Treat as public.
DISCORD_ERROR_CHANNEL_ID = env("ERROR_CHANNEL", default="")

# The hub guild id + the #activation channel id, for the Path B fallback.
# /activate is usable in any server Mylo is installed in, so no one has to join the
# hub to link an account; this pair only funnels the command into one channel
# *inside the hub guild*, and is inert unless both are set.
DISCORD_HUB_GUILD_ID = env("DISCORD_HUB_GUILD_ID", default="")
DISCORD_ACTIVATION_CHANNEL_ID = env(
    "ACTIVATION_CHANNEL", default=env("DISCORD_ACTIVATION_CHANNEL_ID", default="")
)

# Path B code policy. 8 chars over a 30-symbol ambiguity-free alphabet ≈ 39 bits,
# a 15-minute TTL, and one live code per user. The lockout: 5 failures in 15 min
# → a 1-hour block, keyed on the redeeming discord_user_id (not IP), in Redis so
# it survives a bot restart.
DISCORD_ACTIVATION_TTL_SECONDS = env.int(
    "DISCORD_ACTIVATION_TTL_SECONDS", default=900
)
DISCORD_ACTIVATION_MAX_FAILURES = env.int("DISCORD_ACTIVATION_MAX_FAILURES", default=5)
DISCORD_ACTIVATION_FAILURE_WINDOW_SECONDS = env.int(
    "DISCORD_ACTIVATION_FAILURE_WINDOW_SECONDS", default=900
)
DISCORD_ACTIVATION_LOCKOUT_SECONDS = env.int(
    "DISCORD_ACTIVATION_LOCKOUT_SECONDS", default=3600
)

# The outbound Discord queue (apps.integrations.services.outbox). Every product
# message is queued and drained by a worker, so a brief Discord outage delays a
# reminder instead of losing it.
#
# The retry interval is a flat wait, not exponential backoff: five attempts five
# minutes apart, a ~20-minute window. Discord's own Retry-After on a 429 may only
# *lengthen* a wait, never shorten it. Note the interval is longer than Discord's
# enforce_nonce dedup window ("a few minutes"), so the nonce reliably protects a
# fast in-drain retry but not necessarily the next scheduled one.
DISCORD_OUTBOX_RETRY_SECONDS = env.int("DISCORD_OUTBOX_RETRY_SECONDS", default=300)
DISCORD_OUTBOX_MAX_ATTEMPTS = env.int("DISCORD_OUTBOX_MAX_ATTEMPTS", default=5)
DISCORD_OUTBOX_BATCH_LIMIT = env.int("DISCORD_OUTBOX_BATCH_LIMIT", default=50)
# Delivered rows (and their attachment files) are swept after this many days.
# Failed and dead rows are kept — they are the record of what went wrong.
DISCORD_OUTBOX_RETENTION_DAYS = env.int("DISCORD_OUTBOX_RETENTION_DAYS", default=30)
# Where a queued attachment (the daily PDF report) waits for its send. Bytes must
# outlive the batch that rendered them, so this is a durable path, not a temp dir.
DISCORD_OUTBOX_ATTACHMENT_DIR = env_str(
    "DISCORD_OUTBOX_ATTACHMENT_DIR",
    str(ROOT_DIR.parent / "data" / "outbox"),
)

# Per-user, per-bucket slash-command limits as (calls, seconds), enforced by the
# authorization gate. Search is tighter than the rest because one call can trigger a
# query embedding plus several Postgres scans; the others are cheap reads. The check
# fails closed, so a cache outage denies rather than leaving the surface unmetered.
DISCORD_COMMAND_RATE_LIMITS = {
    "search": (env.int("DISCORD_RATE_SEARCH", default=5), 60),
    "command": (env.int("DISCORD_RATE_COMMAND", default=20), 60),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django.security.csrf": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "mycelium.csrf_debug": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

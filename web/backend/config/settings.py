import re
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

env = environ.FileAwareEnv(DEBUG=(bool, False))

environ.Env.read_env(ROOT_DIR.parent / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-dev-only")
DEBUG = env("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)

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

# Namespace the auth cookies. Browsers key cookies by domain but NOT by port, so
# several Django apps on `localhost:<port>` share one cookie jar and Django's
# default `sessionid`/`csrftoken` names collide — a neighbouring app overwrites
# Mycelium's session cookie and every authenticated request then 403s. Distinct
# names isolate Mycelium's session + CSRF cookies from any other local app.
SESSION_COOKIE_NAME = env("DJANGO_SESSION_COOKIE_NAME", default="mycelium_sessionid")
CSRF_COOKIE_NAME = env("DJANGO_CSRF_COOKIE_NAME", default="mycelium_csrftoken")

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
# and enqueues the task on the worker. The hour is UTC (USE_TZ / TIME_ZONE above);
# CELERY_DAILY_SUGGESTIONS_HOUR lets a deployment shift it without a code change.
CELERY_BEAT_SCHEDULE = {
    "daily-research-suggestions": {
        "task": "apps.content.run_daily_suggestions",
        "schedule": crontab(
            hour=env.int("CELERY_DAILY_SUGGESTIONS_HOUR", default=6), minute=0
        ),
    },
    # Grants/conferences run an hour before papers (1am) so the opportunity
    # corpus is refreshed and pruned before the day's matching. Same pattern as
    # above; CELERY_DAILY_OPPORTUNITIES_HOUR shifts it without a code change.
    "daily-opportunities": {
        "task": "apps.content.run_daily_opportunities",
        "schedule": crontab(
            hour=env.int("CELERY_DAILY_OPPORTUNITIES_HOUR", default=1), minute=0
        ),
    },
    # Feature D: recompute every project's team-relevance signal nightly, so
    # engagement that accrued during the day shapes the next day's recommendations.
    "recompute-project-profiles": {
        "task": "apps.content.recompute_project_profiles",
        "schedule": crontab(
            hour=env.int("CELERY_TEAM_PROFILE_HOUR", default=3), minute=0
        ),
    },
}

# How many per-(user, area) grant/conference LLM scoring calls run concurrently
# in the daily opportunity batch. The model call is the slow step, so scoring
# units one at a time dominates the runtime; the endpoint handles many at once.
OPPORTUNITY_LLM_CONCURRENCY = env.int("OPPORTUNITY_LLM_CONCURRENCY", default=12)

# Where the daily suggestion run writes its verbose, timestamped log (one file
# per run). Under the repo's data/ dir by default so it is readable on the host.
DAILY_SUGGESTIONS_LOG_DIR = env(
    "DAILY_SUGGESTIONS_LOG_DIR",
    default=str(ROOT_DIR.parent / "data" / "logs" / "daily-suggestions"),
)

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
LLM_TEMPERATURE = env.float("LLM_TEMPERATURE", default=0.2)
LLM_MAX_TOKENS = env.int("LLM_MAX_TOKENS", default=1024)
# Default reasoning level: one of "none", "low", "medium", "high".
LLM_REASONING = env("LLM_REASONING", default="medium")
# How reasoning levels are sent to the server: "effort" maps to vLLM's
# `reasoning_effort`; "thinking" toggles `chat_template_kwargs.enable_thinking`.
LLM_REASONING_STYLE = env("LLM_REASONING_STYLE", default="effort")

# Daily-suggestion ranking (apps.content.ranking). Weight applied to a paper's
# research-focus overlap when re-ranking retrieved papers: blended score =
# similarity + AREA_FOCUS_WEIGHT * focus_overlap. 0 disables the focus boost.
AREA_FOCUS_WEIGHT = env.float("AREA_FOCUS_WEIGHT", default=0.25)

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

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

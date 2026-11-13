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


# The instance configuration (config/instance.py): defaults → deployment profile →
# mycelium.toml → environment. Every operator-facing policy — billing, limits,
# sign-up, email, optional features, nightly cost controls — resolves there, and
# the names below re-export it under the settings the code already reads. The
# environment still wins, under the same variable names as before. Read after
# `.env` is loaded so its values count as environment.
from .instance import ConfigError as _ConfigError  # noqa: E402
from .instance import resolve as _resolve_instance  # noqa: E402

try:
    INSTANCE = _resolve_instance(ROOT_DIR.parent)
except _ConfigError as _exc:  # fail at boot, with the key that is wrong
    raise SystemExit(f"Invalid Mycelium configuration: {_exc}") from None
_cfg = INSTANCE.values
INSTANCE_PROFILE = INSTANCE.profile
BILLING_MODE = _cfg["billing.mode"]
#: The billing module only decides anything while this is true.
BILLING_ENABLED = BILLING_MODE == "subscriptions"
INSTANCE_LIMITS = {
    key.removeprefix("limits."): value
    for key, value in _cfg.items()
    if key.startswith("limits.") and not key.startswith("limits.tiers.")
}
INSTANCE_TIER_LIMITS = {}
for _key, _value in _cfg.items():
    if _key.startswith("limits.tiers."):
        _tier, _name = _key.removeprefix("limits.tiers.").split(".")
        INSTANCE_TIER_LIMITS.setdefault(_tier, {})[_name] = _value
SIGNUP_MODE = _cfg["signup.mode"]
SIGNUP_ALLOWED_DOMAINS = _cfg["signup.allowed_domains"]
SIGNUP_VERIFY_EMAIL = _cfg["signup.verify_email"]
EMAIL_PROVIDER = _cfg["email.provider"]
NIGHTLY_MODEL_CALLS = _cfg["nightly.model_calls"]
# The public demo (`[demo]`, apps/demo).
DEMO_ENABLED = _cfg["demo.enabled"]
DEMO_QUESTIONS_PER_VISITOR = _cfg["demo.questions_per_visitor"]
DEMO_QUESTIONS_PER_IP_PER_DAY = _cfg["demo.questions_per_ip_per_day"]
DEMO_QUESTIONS_PER_DAY = _cfg["demo.questions_per_day"]
DEMO_QUESTION_MAX_CHARS = _cfg["demo.question_max_chars"]

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
    # Postgres full-text search + trigram support for tools.retrieval.search
    # (SearchVectorField, SearchRank, TrigramWordSimilarity). No-op feature-wise
    # on SQLite; the search path is Postgres-only and guarded accordingly.
    "django.contrib.postgres",
    "corsheaders",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.research",
    "apps.billing",
    "apps.integrations",
    "apps.adminpanel",
    "apps.ambient",
    "apps.knowledge",
    "apps.collab",
    "apps.demo",
]

# Modular tools (tools/ at the repository root). The import script decides,
# before Django starts, which tools may run: only LOADED ones are installed,
# routed, scheduled and configured; a tool that is disabled, broken, or missing
# a dependency contributes nothing, and neither does anything depending on it.
# See tools/README.md.
import sys as _sys  # noqa: E402

if str(ROOT_DIR.parent) not in _sys.path:
    _sys.path.append(str(ROOT_DIR.parent))
from tools._framework import host as _tools_host  # noqa: E402
from tools._framework.loader import ToolsLoadError as _ToolsLoadError  # noqa: E402

try:
    TOOLS_REPORT = _tools_host.boot(INSTANCE)
except _ToolsLoadError as _exc:
    raise SystemExit(str(_exc)) from None
INSTALLED_APPS += [_tools_host.FRAMEWORK_APP, *_tools_host.installed_apps(TOOLS_REPORT)]
TOOLS_URL_MOUNTS = _tools_host.url_mounts(TOOLS_REPORT)

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
    # The public demo's door: /api/demo/<x> is /api/<x> as the demo viewer,
    # read-only. Inert unless demo.enabled (apps/demo/middleware.py).
    "apps.demo.middleware.DemoMiddleware",
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
    # A second engine for the plain-text half of an email, differing in exactly
    # one option: autoescape is off. HTML escaping is correct for a web page and
    # actively wrong in a text/plain body, where it renders literally — a From
    # address arrives as "Mycelium &lt;mycelium@…&gt;" in the reader's client.
    #
    # An engine rather than an {% autoescape %} tag in each template, because the
    # tag is per-file and silently forgotten the day someone adds the fifth
    # template. apps.core.mail.render selects this by name.
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "NAME": "email_text",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {"autoescape": False},
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
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
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
        # Anonymous, and each one sends mail to an address the caller names, so
        # the cap is what stops the endpoint being pointed at someone's inbox.
        "password_reset": env("DJANGO_PASSWORD_RESET_THROTTLE_RATE", default="10/hour"),
        "email_check": env("DJANGO_EMAIL_CHECK_THROTTLE_RATE", default="60/hour"),
        # Signed-in, so the cap is per account: it bounds resend spam and the
        # rate at which one user can grind at codes.
        "email_verify": env("DJANGO_EMAIL_VERIFY_THROTTLE_RATE", default="30/hour"),
        # Every /api/demo/ request, per network address: the demo is an
        # unauthenticated read path, so it gets the same kind of cap.
        "demo": env("DJANGO_DEMO_THROTTLE_RATE", default="1200/hour"),
    },
}

# How long an emailed password-reset link stays usable. Django's default is three
# days, which is a long time for a link that grants a password change to sit in a
# mailbox; an hour is enough for someone acting on the mail they just asked for.
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=3600)

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
SIGNUP_ACCESS_CODE = env_str("SIGNUP_ACCESS_CODE")
SIGNUP_CODE_MAX_FAILURES = env.int("SIGNUP_CODE_MAX_FAILURES", default=3)
SIGNUP_CODE_FAILURE_WINDOW_SECONDS = env.int(
    "SIGNUP_CODE_FAILURE_WINDOW_SECONDS", default=3600
)
SIGNUP_CODE_LOCKOUT_SECONDS = env.int("SIGNUP_CODE_LOCKOUT_SECONDS", default=3600)

# Whether sign-up refuses an address that places the account at no institution
# (``apps.accounts.institution``). Off by default: a personal address proves no
# affiliation, which is already enough to keep anyone from being *listed* at a
# university they cannot receive mail at, and refusing the sign-up outright is a
# stronger rule than that. Turn it on to require an institutional address.
# An invited address is exempt either way — being asked for by name is its own
# affiliation proof, and it is how someone at an institute missing from the
# directory gets in at all.
SIGNUP_REQUIRE_INSTITUTION_EMAIL = _cfg["signup.require_institution_email"]

# Sign-up with a valid access code grants this personal tier instead of Free, so
# everyone who gets past the invite gate lands on the intelligence line rather
# than the on-demand baseline. Must be a tier sold to a personal scope
# (apps.billing.tiers.PERSONAL_TIERS) — provisioning validates it and will refuse
# a team tier here. Set to "free" to restore the old behaviour.
SIGNUP_GRANT_TIER = _cfg["billing.signup_tier"]

# Feature gating master switch. Off (the default) makes
# apps.billing.entitlements resolve every capability as granted, for every user
# and every lab, whatever their tier or add-ons. Plans, prices, invoices and the
# numeric caps below are untouched — this only stops a tier from *withholding* a
# feature. Turn it on to sell tiered capability again.
BILLING_ENFORCE_ENTITLEMENTS = BILLING_ENABLED and _cfg["billing.enforce_features"]

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
    # "recompute-project-profiles" (nightly team-profile recompute) is declared
    # by the recommendation tool (tools/recommendation/tool.py, Tool.beat).
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
    # The outbound Slack queue (ambient Plan 11), on the same cadence and for the
    # same reason. A no-op while nothing is queued.
    "drain-slack-outbox": {
        "task": "apps.integrations.drain_slack_outbox",
        "schedule": crontab(minute="*"),
    },
    "drain-teams-outbox": {
        "task": "apps.integrations.drain_teams_outbox",
        "schedule": crontab(minute="*"),
    },
    # Weekly clean-up of delivered outbox rows and the report PDFs they carried.
    # Sunday, well away from the daily run and the other sweeps.
    "purge-discord-outbox": {
        "task": "apps.integrations.purge_outbox",
        "schedule": crontab(day_of_week=0, hour=5, minute=30),
    },
    # The ambient ledger's retention sweep: delete message references past
    # their window. Message bodies are not its business — those expire in Redis
    # by TTL within hours — and observations are never touched, because they are
    # the person's own record and leave only when the person removes them.
    # Nightly, after the daily run has read whatever it was going to read.
    # Which project each person actually spent their conversation on, over 7
    # and 28 days. Derived from attributed references and never hand-edited;
    # before the retention sweep, so it reads the same history the sweep keeps.
    "recompute-ambient-attention": {
        "task": "apps.ambient.recompute_attention",
        "schedule": crontab(
            hour=env.int("AMBIENT_ATTENTION_HOUR", default=4), minute=45
        ),
    },
    # Read conversations that have gone quiet, within the buffer's TTL (Plan
    # 04, option C). Does nothing while AMBIENT_ENABLED is off.
    "read-ambient-conversations": {
        "task": "apps.ambient.read_conversations",
        "schedule": crontab(minute=env.int("AMBIENT_READ_MINUTE", default=20)),
    },
    "sweep-ambient-retention": {
        "task": "apps.ambient.sweep_retention",
        "schedule": crontab(hour=env.int("AMBIENT_SWEEP_HOUR", default=5), minute=15),
    },
    # The knowledge core's reconciliation: re-mirror every declared profile,
    # lab and project into the graph (a save hook can be missed, and a wording
    # the embedder could not reach is retried here), then prune private
    # concepts nothing points at. Before the 07:00 daily run so the run reads a
    # reconciled graph.
    # Collaboration: remind people whose open-to-collaboration setting ends
    # soon, and drop appearance records past eight weeks.
    "collab-daily": {
        "task": "apps.collab.daily",
        "schedule": crontab(hour=env.int("COLLAB_DAILY_HOUR", default=4), minute=30),
    },
    "sweep-knowledge": {
        "task": "apps.knowledge.sweep",
        "schedule": crontab(hour=env.int("KNOWLEDGE_SWEEP_HOUR", default=4), minute=15),
    },
}

# How many per-(user, area) grant/conference LLM scoring calls run concurrently
# in the daily opportunity batch. The model call is the slow step, so scoring
# units one at a time dominates the runtime; the endpoint handles many at once.
OPPORTUNITY_LLM_CONCURRENCY = _cfg["nightly.llm_concurrency"]
# How many précis and per-theme write-up calls may be in flight for one target
# (tools.recommendation.comprehension / cluster_fit / theme_run). Themes run side by
# side
# and share this budget. vLLM batches concurrent requests.
WRITEUP_LLM_CONCURRENCY = _cfg["nightly.writeup_concurrency"]

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
# RUN_ANALYTICS_RETENTION_DAYS -> tools/delivery/tool.py

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
# Output cap per model reply; 0 = none (instance key llm.max_tokens, D-6 of
# the Mylo agent plan). Callers that need a cap pass max_tokens themselves.
LLM_MAX_TOKENS = _cfg["llm.max_tokens"]
# Default reasoning level: one of "none", "low", "medium", "high".
LLM_REASONING = env("LLM_REASONING", default="medium")
# How reasoning levels are sent to the server: "effort" maps to vLLM's
# `reasoning_effort`; "thinking" toggles `chat_template_kwargs.enable_thinking`.
LLM_REASONING_STYLE = env("LLM_REASONING_STYLE", default="effort")
# Thinking-token budget for the harder reasoning tasks (cluster composition):
# sent as `thinking_token_budget` in the request's extra_body so the server
# reserves room to reason before answering. Keep >= 512 (see clusters.py).
LLM_THINKING_BUDGET = env.int("LLM_THINKING_BUDGET", default=512)
# Model servers ([llm] default / allow_cloud / fallback, [llm.providers.<name>],
# [llm.routes] in mycelium.toml). "local" is synthesised from the LLM_* values
# above unless declared. The table holds key *variable names* only;
# apps.core.llm_servers reads a key from the environment when it builds a client.
LLM_SERVERS = INSTANCE.llm.servers
LLM_ROUTES = INSTANCE.llm.routes
LLM_DEFAULT_SERVER = _cfg["llm.default"]
LLM_ALLOW_CLOUD = _cfg["llm.allow_cloud"]
LLM_FALLBACK = _cfg["llm.fallback"]

# TypeSafe System One (apps/core/systemone.py). A decision model, not a text
# generator: typed questions in, calibrated probabilities out. Prototype seam
# only — no production path calls it. The model is pinned to a version rather
# than the `jev-latest` alias so an experiment names the thing that answered.
TYPESAFE_API_KEY = env("TYPESAFE_API_KEY", default="")
TYPESAFE_MODEL = env("TYPESAFE_MODEL", default="jev-1.13.0")
TYPESAFE_BASE_URL = env("TYPESAFE_BASE_URL", default="https://api.typesafe.ai")
TYPESAFE_TIMEOUT = env.float("TYPESAFE_TIMEOUT", default=10.0)
# Retries belong to the caller, as with LLM_MAX_RETRIES.
TYPESAFE_MAX_RETRIES = env.int("TYPESAFE_MAX_RETRIES", default=0)

# Daily-suggestion ranking (tools.recommendation.ranking). Weight applied to a paper's
# research-focus overlap when re-ranking retrieved papers: blended score =
# similarity + AREA_FOCUS_WEIGHT * focus_overlap. 0 disables the focus boost.
# AREA_FOCUS_WEIGHT -> tools/recommendation/tool.py

# Daily research-paper feed sizing (tools.recommendation.pipeline). The Research Papers
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
# PAPER_MATCH_THRESHOLD -> tools/recommendation/tool.py
# PAPER_MATCH_MAX_SURFACE -> tools/recommendation/tool.py

# Nightly runs carry forward a paper's prior LLM verdict instead of re-scoring it
# (tools.recommendation.pipeline / .suggest), so a researcher's match% doesn't flap
# night
# to night and the freed LLM slots go to papers never scored, new ones first. A
# paper the model scores below PAPER_MIN_MATCH_PERCENT is persisted (so the
# carry-forward store remembers it and never re-sends it) but hidden from the feed
# (``suggested=False``) rather than surfaced with a low score.
# PAPER_MIN_MATCH_PERCENT -> tools/recommendation/tool.py

# How many items make up a target's slate per category — the "Top 25" the daily
# report is built from (tools.recommendation.top_feed). The report shows the slate and
# calls
# new whatever entered it since the last run, so this number is both how much a
# reader is shown and how far down the ranking a promotion still counts as news.
# There is deliberately no second relevance floor on top: the feed's own embedding
# threshold (PAPER_MATCH_THRESHOLD, GRANT_MATCH_THRESHOLD, …) already decides what
# is good enough to be in the feed at all, and a second opinion about the top of
# that list only ever made the report quietly shorter than it claimed to be.
# REPORT_TOP_N -> tools/recommendation/tool.py

# Papers an institutional target (lab / lab project) draws from EACH of its
# interest clusters (tools.recommendation.pipeline.recommend_for_target). A lab's areas
# are
# broad theme names rather than a person's specific keywords, so one theme's
# vocabulary consistently sits closer to the day's literature; ranked globally it
# took the whole model budget and the lab's other themes read as empty. Each theme
# now contributes its own best N, all of which are scored by the model and shown —
# a slate member is not withheld by PAPER_MIN_MATCH_PERCENT, since this run is what
# chose it. Left at 0 (the default) the depth comes from
# ``tools.recommendation.slates.slate_depth`` instead, which is where the per-category
# geometry now lives; set it only to override that for papers specifically.
# PAPER_CLUSTER_TOP_N -> tools/recommendation/tool.py

# Per-cluster admission (tools.recommendation.admission). A candidate is admitted when
# it
# clears PAPER_MATCH_THRESHOLD *or* reaches CLUSTER_ADMIT_FRAC of its own theme's
# best score — the second is what stops a theme whose vocabulary sits further from
# the corpus being excluded wholesale. CLUSTER_ADMIT_HARD_FLOOR sits under both, so
# a theme with nothing genuinely relevant admits nothing rather than its ten
# least-irrelevant candidates. It is not optional; do not set it to 0.
# CLUSTER_ADMIT_FRAC -> tools/recommendation/tool.py
# CLUSTER_ADMIT_HARD_FLOOR -> tools/recommendation/tool.py

# Model write-ups per target per run (tools.recommendation.cluster_fit). A run-safety
# cap,
# not a spend cap: the nightly batch is shared, so an unbounded spike for one
# reader who just redesigned their profile would degrade everyone else's report.
# Funded by slate position (entrants first at equal position); whatever does not
# fit is written deterministically and carries to the next run.
CLUSTER_WRITEUP_BUDGET = _cfg["nightly.cluster_writeup_budget"]
# CLUSTER_FIT_BATCH -> tools/recommendation/tool.py

# Papers sign-up hybrid (tools.recommendation.onboarding_match). A brand-new user is
# first
# matched against the latest gather batch already in the store (no live scan). If
# that yields at least PAPER_ONBOARDING_MIN_HIGH_QUALITY suggestions carrying a
# "read" verdict, those are shown; otherwise a
# background scan of the user's watch topics is kicked off and the Research Papers
# page shows a "scanning" state (a Redis flag, best-effort) until it lands.
# PAPER_SCAN_INFLIGHT_TTL bounds that flag so a dead scan can never wedge it on.
# PAPER_ONBOARDING_MIN_HIGH_QUALITY -> tools/recommendation/tool.py
PAPER_SCAN_INFLIGHT_TTL = env.int("PAPER_SCAN_INFLIGHT_TTL", default=1800)

# Opportunity feed sizing (tools.recommendation.opportunities / .fellowships). Like the
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
# GRANT_MATCH_THRESHOLD -> tools/recommendation/tool.py
# CONFERENCE_MATCH_THRESHOLD -> tools/recommendation/tool.py
# FELLOWSHIP_FIT_THRESHOLD -> tools/recommendation/tool.py
# FELLOWSHIP_MATCH_THRESHOLD -> tools/recommendation/tool.py
# OPPORTUNITY_MATCH_MAX_SURFACE -> tools/recommendation/tool.py

# A fellowship whose scraped facet buckets are all empty (a failed detail render,
# a missed selector) carries no eligibility information, so every facet test
# trivially passes it and it would otherwise match everybody. It is tiered
# "unverified" and labelled as unchecked instead. Withholding it entirely is the
# stricter option, off by default: a parse failure should not silently cost a
# researcher a real award.
# FELLOWSHIP_WITHHOLD_UNVERIFIED -> tools/recommendation/tool.py

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
# OPPORTUNITY_FEED_MAX -> tools/delivery/tool.py
# Opportunity announcements (plan 20261105-mylo-opportunity-announcements): one
# Discord thread per newly fitting grant, fellowship or conference. Off until
# every phase has shipped; the dry run works either way.
OPPORTUNITY_ANNOUNCEMENTS_ENABLED = _cfg["features.announcements"]

# How long a dateless conference may go unseen before the nightly prune deletes
# it (OPPORTUNITY_STALE_DAYS) is the retrieval tool's setting:
# tools/retrieval/tool.py.

# Same carry-forward + floor behaviour as papers (above), for grants / conferences /
# fellowships: an item the model scored below this stays in the carry-forward store
# (never re-sent to the model) but off the feed until it improves or ages out.
# OPPORTUNITY_MIN_MATCH_PERCENT -> tools/recommendation/tool.py

# High-signal notification gate (tools.delivery.high_signal, reminders R7). A brutal
# floor: abstention is a feature — if nothing clears the bar, send nothing. An alert
# that fires most days is a digest, and digests are out of scope. HIGH_SIGNAL_FLOOR is
# a PLACEHOLDER pending shadow-mode calibration on the real RelevanceScore corpus
# (`manage.py high_signal_shadow`); do NOT trust the default 90 until it is measured
# (D-14). Delivery ships OFF (D-10: high-signal stays in-app-only for now; and it must
# not deliver on a guessed threshold) — flip HIGH_SIGNAL_DELIVERY_ENABLED only after
# calibration.
# HIGH_SIGNAL_FLOOR -> tools/delivery/tool.py
# HIGH_SIGNAL_WEEKLY_CAP -> tools/delivery/tool.py
# HIGH_SIGNAL_DEADLINE_MIN_DAYS -> tools/delivery/tool.py
# HIGH_SIGNAL_DEADLINE_MAX_DAYS -> tools/delivery/tool.py
HIGH_SIGNAL_DELIVERY_ENABLED = _cfg["features.high_signal"]

# How many days of written daily briefings the Reports page keeps (the
# `prune_briefings` stage of the daily run deletes anything older). Flat for every
# plan: only holders of the scheduled-reports feature are ever given a briefing, so
# there is nothing to retain on the free tier. Markdown only — the DM'd PDF is an
# outbox attachment and ages out with the outbox's own sweep.
# BRIEFING_RETENTION_DAYS -> tools/delivery/tool.py

# Project collaboration (tools.delivery.collaboration). Per-action weight written on
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

# Project team-relevance signal (tools.recommendation.team_profile — Feature D). The
# recomputed team vector blends the project's declared focus, its members' interest
# vectors, and their recent weighted engagement (each normalized before fusion);
# it is written to Project.embedding for the recommendation pipeline to read.
# Engagement decays with a half-life so stale clicks fade. Weights are relative.
# PROJECT_PROFILE_FOCUS_WEIGHT -> tools/recommendation/tool.py
# PROJECT_PROFILE_MEMBER_WEIGHT -> tools/recommendation/tool.py
# PROJECT_PROFILE_ENGAGEMENT_WEIGHT -> tools/recommendation/tool.py
# PROJECT_PROFILE_HALFLIFE_DAYS -> tools/recommendation/tool.py

# Cross-member relevance fan-out (tools.delivery.fanout — Feature F). A shared paper
# is suggested to a member when the normalized cosine between the item and the
# member's profile clears this floor; below-floor rows persist as audited
# abstentions, never sent. ``FANOUT_ASYNC`` routes the trigger through Celery
# instead of running inline in the share request (needs a running worker).
# FANOUT_COSINE_FLOOR -> tools/delivery/tool.py
# FANOUT_ASYNC -> tools/delivery/tool.py

# Per-item member recommendations (tools.recommendation.member_fit) — the "who in this
# lab
# is this most applicable to?" layer on every lab/project feed. A member is a
# candidate when the cosine between the item and their own interest vector clears
# MEMBER_FIT_COSINE_FLOOR (the FANOUT_COSINE_FLOOR convention); at most
# MEMBER_FIT_MAX_MEMBERS are named per item, so a card stays readable in a large
# lab. Mylo writes the rationale for the strongest MEMBER_FIT_LLM_LIMIT items of
# each area (the digest's llm_limit convention); everything below carries a
# deterministic reason built from the overlap, and an unreachable model degrades
# the whole layer to that same deterministic ranking.
# MEMBER_FIT_COSINE_FLOOR -> tools/recommendation/tool.py
# MEMBER_FIT_MAX_MEMBERS -> tools/recommendation/tool.py
MEMBER_FIT_LLM_LIMIT = _cfg["nightly.member_fit_llm_limit"]
# Recompute a project's team profile immediately when its membership changes.
TEAM_PROFILE_AUTORECOMPUTE = env.bool("TEAM_PROFILE_AUTORECOMPUTE", default=True)

# Unified search (tools.retrieval.search): its SEARCH_* settings are the
# retrieval tool's — tools/retrieval/tool.py, [tools.retrieval] in mycelium.toml.

# The query-embedding cache (tools.retrieval.query_embedding). A repeated search
# should skip the model call, so the normalized query → its vector is cached in
# Redis. It lives in a *dedicated* Redis db (never the Celery broker/result dbs),
# derived from REDIS_URL by swapping the db number so it is correct on both the
# host and inside the compose network. Best-effort: a Redis outage degrades to
# "embed every time", never an error.
_REDIS_URL = env("REDIS_URL", default="redis://localhost:11550/0")
SEARCH_CACHE_URL = env("SEARCH_CACHE_URL", default=re.sub(r"/\d+$", "/2", _REDIS_URL))
SEARCH_CACHE_TTL = env.int("SEARCH_CACHE_TTL", default=3600)

# A small Redis-backed cache for the "paper scan in flight" flag, which the web
# process sets (at sign-up) and the Celery worker clears (when the scan lands), so
# it must be shared across processes — the default LocMemCache is per-process. All
# reads/writes are best-effort (tools.recommendation.scan_status), so a Redis outage
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

# The ambient raw-message buffer (apps.ambient.buffer). This is the one place a
# person's actual words exist, and they exist only long enough to assemble one
# window for extraction — so it gets its own Redis db (never the Celery
# broker/result dbs, never a shared cache), every key carries a TTL, and nothing
# here is ever written to Postgres, a disk, or a backup. A Redis outage costs a
# night's extraction; it must never cost a message a longer life somewhere else.
AMBIENT_CACHE_URL = env("AMBIENT_CACHE_URL", default=re.sub(r"/\d+$", "/6", _REDIS_URL))

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
    "ambient": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": AMBIENT_CACHE_URL,
        "KEY_PREFIX": "mycelium_ambient",
        # Every write sets its own TTL from AMBIENT_RAW_TTL_HOURS; this is the
        # backstop for a write that somehow does not.
        "TIMEOUT": 60 * 60 * 6,
    },
}

# Author-import sources (apps.accounts.intake). Keys are optional: OpenAlex works
# without one (a polite `mailto` is encouraged), and Semantic Scholar's key only
# raises rate limits. Google Scholar needs no key but the optional `scholarly`
# package (install the `scrapers` extra).
OPENALEX_API_KEY = env("OPEN_ALEX_API_KEY", default="")
OPENALEX_MAILTO = env("OPENALEX_MAILTO", default="")
SEMANTIC_SCHOLAR_API_KEY = env("SEMANTIC_SCHOLAR_API_KEY", default="")

# Literature scan contact (tools/retrieval). The contact email is OpenAlex/NCBI
# etiquette; it falls back to OPENALEX_MAILTO.
SCRAPER_CONTACT_EMAIL = env("SCRAPER_CONTACT_EMAIL", default=OPENALEX_MAILTO)
# PUBMED_API_KEY and the corpus embedding model (SCRAPER_EMBEDDING_MODEL) are
# the retrieval tool's settings now: tools/retrieval/tool.py.

# Embedding device and batch sizes (EMBEDDING_DEVICE, EMBEDDING_DEVICE_ID,
# EMBEDDING_BATCH_SIZE_CPU/GPU) are the retrieval tool's settings:
# tools/retrieval/tool.py, section [tools.retrieval] in mycelium.toml.

# Cross-encoder rerank (tools.recommendation.reranking). Reorders the head of the fused
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
RERANK_ENABLED = _cfg["features.rerank"]
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

# Which decision model re-orders the head of each theme's slate
# (tools.recommendation.typesafe_rerank over apps.core.decisions), set by
# [decision] in mycelium.toml. "jev" asks TypeSafe's hosted model, "port" a model
# the operator serves (llama.cpp, vLLM or a decide server at DECISION_PORT_URL),
# "off" leaves the stack above exactly as deployed, and "auto" (the default)
# takes jev with a key, else port with a URL, else off. The old RERANK_METHOD
# env name still works (typesafe = jev, local = off). It reorders the top
# TYPESAFE_RERANK_WINDOW of every theme by the returned probability. Gated to
# paid plans through billing.entitlements (Feature.TYPESAFE_RERANK); with
# BILLING_ENFORCE_ENTITLEMENTS off that gate grants everyone.
# Evidence: EXP-2026-09-003, EXP-2026-09-004 (Jev); EXP-2026-11-007 (d3-lite on
# a port: works, but below the discrimination bar).
DECISION_BACKEND = _cfg["decision.backend"]
DECISION_PORT_URL = _cfg["decision.port_url"]
DECISION_PORT_PROTOCOL = _cfg["decision.port_protocol"]
DECISION_PORT_MODEL = _cfg["decision.port_model"]
DECISION_PORT_TIMEOUT = _cfg["decision.port_timeout"]
DECISION_PORT_API_KEY = env("DECISION_PORT_API_KEY", default="")
TYPESAFE_RERANK_WINDOW = env.int("TYPESAFE_RERANK_WINDOW", default=20)
TYPESAFE_RERANK_CONTENT_TYPES = env.list(
    "TYPESAFE_RERANK_CONTENT_TYPES",
    default=["paper", "grant", "conference", "fellowship"],
)
TYPESAFE_RERANK_CONCURRENCY = _cfg["nightly.rerank_concurrency"]

# ---------------------------------------------------------------------------
# Project alerts (tools.delivery.matchers, tools.delivery.alerts).
#
# Ships OFF. The three thresholds below decide when a paper is close enough to a
# project's claimed contribution, a venue's slot, or a stated blocker to be worth
# interrupting somebody about, and nobody has measured them yet — a similarity
# threshold set by taste fires constantly or never, and both teach a reader to
# stop opening the report. Plan 3.8: a calibration run (alert precision measured
# as saved-or-opened within seven days against dismissed) sets these, and only
# then does the flag turn on.
#
# The two triggers that are NOT threshold-based — a timeline verdict and a moved
# deadline — are arithmetic over stored dates and are correct today, so they run
# regardless of this flag. That is the whole reason the flag is per-mechanism
# rather than per-feature.
# ---------------------------------------------------------------------------
PROJECT_ALERTS_ENABLED = _cfg["features.project_alerts"]
# PROJECT_ALERT_OVERLAP_THRESHOLD -> tools/delivery/tool.py
# PROJECT_ALERT_BLOCKER_THRESHOLD -> tools/delivery/tool.py
# PROJECT_ALERT_SLOT_THRESHOLD -> tools/delivery/tool.py
#: At most this many alerts per target per day. The cap is the product decision,
#: not a performance one: four things that all need attention today is a reader
#: who attends to none of them. Overflow is held for the Monday weekly.
# PROJECT_ALERT_DAILY_CAP -> tools/delivery/tool.py

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
DISCORD_BOT_TOKEN = env("DISCORD_API_KEY", default=env("DISCORD_BOT_TOKEN", default=""))
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

# The two OAuth callbacks. OAuth2 forbids a relative redirect_uri, and Discord
# matches whatever we send BYTE-FOR-BYTE against the app's registered redirect
# list — anything else is rejected with "Invalid OAuth2 redirect_uri" on Discord's
# own page, with nothing reaching our logs. So the one thing this must never do is
# vary: a deployment that emits three different origins has to register three, and
# will silently fail the day it emits a fourth.
#
# The origin is therefore resolved in this order:
#   1. An explicit DISCORD_OAUTH_REDIRECT_URI / DISCORD_GUILD_REDIRECT_URI pin.
#   2. DISCORD_CALLBACK_ORIGIN — PUBLIC_BASE_URL whenever PUBLIC_HOSTNAME is set,
#      i.e. any deployment that knows its own public name. This is the case that
#      matters: it pins the callback to the one origin a browser can actually come
#      back on, and stops the internal proxy hop (Host: backend:8000, because the
#      Next rewrite target replaces the Host header) or a loopback dev origin from
#      ever being sent to Discord.
#   3. The live request's own origin — only on an unconfigured local checkout,
#      where there is no public name to pin to.
#
# `manage.py discord_check` prints exactly what this resolves to, which is what
# belongs in the Developer Portal's redirect list.
DISCORD_OAUTH_REDIRECT_URI = env_str("DISCORD_OAUTH_REDIRECT_URI")
DISCORD_GUILD_REDIRECT_URI = env_str("DISCORD_GUILD_REDIRECT_URI")
DISCORD_CALLBACK_ORIGIN = env_str(
    "DISCORD_CALLBACK_ORIGIN", PUBLIC_BASE_URL if PUBLIC_HOSTNAME else ""
).rstrip("/")
# Where the user lands back in the portal after a link attempt (success or error
# is carried as a query param). Settings → You → Delivery reads it. Kept absolute
# because the Mylo gateway quotes it in DMs; the callback views redirect to its
# path alone, so the browser stays on the origin it arrived from.
DISCORD_PORTAL_RETURN_URL = env_str(
    "DISCORD_PORTAL_RETURN_URL", f"{DISCORD_APP_BASE_URL}/app/settings/you/delivery"
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
# A public invite to the Mycelium hub server, quoted verbatim in the portal's
# "link with a code" panel so someone who is not already in a server with Mylo has
# somewhere to run /activate. Blank is a supported state: the panel then drops the
# "join the server" step rather than offering a dead link.
DISCORD_INVITE_URL = env_str("DISCORD_INVITE_URL")

DISCORD_ACTIVATION_TTL_SECONDS = env.int("DISCORD_ACTIVATION_TTL_SECONDS", default=900)
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

# ---------------------------------------------------------------------------
# Transactional email (apps.core.mail) — Resend.
#
# The transport for anything the product has to put in a person's inbox rather
# than a Discord DM: a password reset, an invitation to a lab or department, a
# verification code. Those all reach people who are *not yet* linked to Discord,
# which is exactly why email cannot be replaced by the outbox.
#
# Wired as a Django EMAIL_BACKEND rather than a bare helper on purpose: Django's
# own password-reset machinery sends through `django.core.mail`, so routing that
# name at Resend means the built-in flow works when it is built, with no second
# transport to configure. apps.core.mail.send_email sits on top for templated
# product mail.
#
# The API key is send-only (it cannot read delivery logs) and stays in the
# environment — never persisted, never logged.
# ---------------------------------------------------------------------------
RESEND_API_KEY = env("RESEND_API_KEY", default="")
RESEND_API_URL = env_str("RESEND_API_URL", "https://api.resend.com/emails")
RESEND_TIMEOUT_SECONDS = env.int("RESEND_TIMEOUT_SECONDS", default=15)

# The verified sending identity. The domain must be verified in Resend and carry
# SPF + DKIM, or mail is accepted by the API and then dropped or spam-filed by
# the receiving side — the failure is silent from here.
DEFAULT_FROM_EMAIL = _cfg["email.from"]
SERVER_EMAIL = env_str("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
# Optional Reply-To for product mail. Blank means replies go to DEFAULT_FROM_EMAIL,
# which is an unmonitored no-reply address.
EMAIL_REPLY_TO = _cfg["email.reply_to"]
EMAIL_SUBJECT_PREFIX = env_str("EMAIL_SUBJECT_PREFIX")

# The master switch, default OFF. Real mail is irreversible: a mistimed loop in
# development emails real people at their real addresses, and there is no recall.
# So sending is opt-in per deployment rather than on by default, and the console
# backend below makes an un-configured environment loud instead of silent.
EMAIL_ENABLED = EMAIL_PROVIDER != "none"

# Backend resolution, in order of specificity:
#   1. An explicit EMAIL_BACKEND always wins (tests pin locmem this way).
#   2. email.provider = "resend" with a key → Resend.
#   3. email.provider = "smtp"              → Django's SMTP backend.
#   4. Anything else                        → console, so a developer sees the body.
EMAIL_HOST = _cfg["email.smtp_host"]
EMAIL_PORT = _cfg["email.smtp_port"]
EMAIL_HOST_USER = _cfg["email.smtp_user"]
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = _cfg["email.smtp_tls"]
if EMAIL_PROVIDER == "resend" and RESEND_API_KEY:
    _email_backend = "apps.core.mail.backend.ResendEmailBackend"
elif EMAIL_PROVIDER == "smtp" and EMAIL_HOST:
    _email_backend = "django.core.mail.backends.smtp.EmailBackend"
else:
    _email_backend = "django.core.mail.backends.console.EmailBackend"
EMAIL_BACKEND = env_str("EMAIL_BACKEND", _email_backend)

# Absolute origin for links written into email (reset links, invitation links).
# Same reasoning as DISCORD_APP_BASE_URL: these are composed outside any HTTP
# request, so they cannot be derived from one, and a loopback origin would send a
# real recipient to their own machine.
EMAIL_APP_BASE_URL = outbound_base_url(env_str("EMAIL_APP_BASE_URL", PUBLIC_BASE_URL))

# ---------------------------------------------------------------------------
# The ambient evidence ledger (apps.ambient)
#
# What Mylo understands about a person from the lab's own conversation. It ships
# OFF and collects nothing until AMBIENT_ENABLED is set, because turning it on
# means reading what people say to each other — a decision a deployment makes
# deliberately, never one it inherits from a default.
# ---------------------------------------------------------------------------
AMBIENT_ENABLED = _cfg["features.ambient"]

# How long raw message text may sit in the buffer before it expires, in hours.
# The buffer is deleted explicitly once a window has been read; this TTL is the
# safety net for the night that never runs. AMBIENT_RAW_TTL_HOURS_MAX is a hard
# ceiling the per-source override cannot raise, so "Mylo does not keep your
# messages" stays true of every source, however it is configured.
AMBIENT_RAW_TTL_HOURS = env.int("AMBIENT_RAW_TTL_HOURS", default=6)
AMBIENT_RAW_TTL_HOURS_MAX = env.int("AMBIENT_RAW_TTL_HOURS_MAX", default=24)

# How long a repeated message counts as the same piece of evidence rather than a
# second one. Forwarded and re-pasted material is common in a lab channel and a
# profile should not read three copies of one link as three signals.
AMBIENT_REPEAT_WINDOW_DAYS = env.int("AMBIENT_REPEAT_WINDOW_DAYS", default=30)

# How long a message *reference* is kept, in days. A reference holds ids and
# timestamps and no text, but a permanent record of every message id and the
# minute it was sent is still a record of who talked when, and this feature has
# no use for one. The sweep (apps.ambient.retention) never lowers this below the
# repeat window plus a day: a reference vanishing while its hash could still
# match would silently turn a repeat back into new evidence.
AMBIENT_REF_RETENTION_DAYS = env.int("AMBIENT_REF_RETENTION_DAYS", default=45)

# What is worth carrying at all (apps.ambient.filters). Discord delivers far
# more than is useful, and feeding a server's reaction spam to an extractor
# costs money to learn nothing. A message shorter than the minimum with no link
# and no attachment is chatter; one longer than the maximum is a pasted
# document, and only its head reaches the buffer. A message addressed to Mylo
# deliberately — a DM, a mention, a note — skips the minimum, because somebody
# answering "yes" to Mylo's own question meant that.
AMBIENT_MIN_MESSAGE_CHARS = env.int("AMBIENT_MIN_MESSAGE_CHARS", default=24)
AMBIENT_MAX_MESSAGE_CHARS = env.int("AMBIENT_MAX_MESSAGE_CHARS", default=4000)

# Which project a message is about (apps.ambient.attribution). The top
# candidate must reach the floor AND lead the runner-up by the margin, or the
# answer is "unresolved" — a real answer, because a message filed under the
# wrong project corrupts two things at once. These ship conservative and are
# to be set from labelled corrections (OD-03b), not by taste. Continuity is how
# long a confident attribution carries in the same place; the thread override
# is how strong another project's own content must be to break a thread's
# inheritance from its opening.
AMBIENT_ATTRIBUTION_FLOOR = env.float("AMBIENT_ATTRIBUTION_FLOOR", default=0.6)
AMBIENT_ATTRIBUTION_MARGIN = env.float("AMBIENT_ATTRIBUTION_MARGIN", default=0.25)
AMBIENT_CONTINUITY_MINUTES = env.int("AMBIENT_CONTINUITY_MINUTES", default=30)
AMBIENT_THREAD_OVERRIDE = env.float("AMBIENT_THREAD_OVERRIDE", default=0.9)

# The reasoning agent (ambient-profile Plan 04). Reading happens through the
# day, within the buffer's TTL (decision 2026-09-19, option C): a conversation
# is read once its place has been quiet for AMBIENT_WINDOW_QUIET_MINUTES, once
# it reaches its cap, or once its oldest body is an hour from expiring. The
# model is called at most AMBIENT_EXTRACT_DAILY_CAP_PER_LAB times a day per lab
# (per DM source for a person's own conversation with Mylo), with at most
# AMBIENT_EXTRACT_CONCURRENCY calls in flight.
AMBIENT_WINDOW_HOURS = env.int("AMBIENT_WINDOW_HOURS", default=4)
AMBIENT_WINDOW_MAX_MESSAGES = env.int("AMBIENT_WINDOW_MAX_MESSAGES", default=40)
AMBIENT_WINDOW_QUIET_MINUTES = env.int("AMBIENT_WINDOW_QUIET_MINUTES", default=60)
AMBIENT_EXTRACT_DAILY_CAP_PER_LAB = _cfg["nightly.ambient_extract_per_lab"]
AMBIENT_EXTRACT_CONCURRENCY = _cfg["nightly.ambient_extract_concurrency"]
# Deciding, nightly. Ships OFF and separate from AMBIENT_ENABLED: with it off,
# observations accumulate and nothing is decided about anybody. Deliberation is
# pure over the ledger (no model call); the explanations it asks for are
# model-written, at most AMBIENT_EXPLAIN_NIGHTLY_CAP a night.
AMBIENT_DELIBERATE_ENABLED = _cfg["features.ambient_deliberate"]
AMBIENT_LOOKBACK_DAYS = env.int("AMBIENT_LOOKBACK_DAYS", default=28)
AMBIENT_HALF_LIFE_DAYS = env.float("AMBIENT_HALF_LIFE_DAYS", default=21.0)
# The consistency test (Plans 04 and 06): distinct days, how far apart the first
# and last are, distinct conversations, and at least one preference, decision
# or fact rather than only questions and possibilities — with no rejection
# since. Two mentions on one day never pass; the same two a fortnight apart do.
AMBIENT_CONSISTENT_DAYS = env.int("AMBIENT_CONSISTENT_DAYS", default=2)
AMBIENT_CONSISTENT_SPAN_DAYS = env.int("AMBIENT_CONSISTENT_SPAN_DAYS", default=5)
AMBIENT_CONSISTENT_CONVERSATIONS = env.int(
    "AMBIENT_CONSISTENT_CONVERSATIONS", default=2
)
# A topic is "already covered" when the person holds the same concept, or one at
# least this similar, on their declared profile or among what they confirmed.
AMBIENT_COVERED_SIMILARITY = env.float("AMBIENT_COVERED_SIMILARITY", default=0.85)
# A no rests this long, and afterwards only fresh consistency re-opens it.
AMBIENT_DECLINE_REST_DAYS = env.int("AMBIENT_DECLINE_REST_DAYS", default=30)
# A declared cluster nobody has talked about for this long is a swap candidate.
AMBIENT_STALE_DAYS = env.int("AMBIENT_STALE_DAYS", default=90)
AMBIENT_EXPLAIN_NIGHTLY_CAP = _cfg["nightly.ambient_explain"]
# The evolving profile (Plan 05). A confirmed exploration joins a person's
# paper search as its own theme, weighted at AMBIENT_DRIFT_WEIGHT of a declared
# theme in the global ranking so it can never crowd one (apps.content
# .explorations). Ships OFF: a ranking change is turned on with an evaluation
# run behind it. An exploration is reviewed ("keep this?") after
# AMBIENT_EXPLORATION_REVIEW_DAYS. The project a person spent most of their
# week on leads their report, with AMBIENT_ATTENTION_EXTRA_ITEMS more items,
# once its 7-day share reaches AMBIENT_ATTENTION_LEAD_SHARE.
AMBIENT_DRIFT_ENABLED = _cfg["features.ambient_drift"]
AMBIENT_DRIFT_WEIGHT = env.float("AMBIENT_DRIFT_WEIGHT", default=0.15)
AMBIENT_EXPLORATION_REVIEW_DAYS = env.int("AMBIENT_EXPLORATION_REVIEW_DAYS", default=30)
AMBIENT_ATTENTION_LEAD_SHARE = env.float("AMBIENT_ATTENTION_LEAD_SHARE", default=0.4)
AMBIENT_ATTENTION_EXTRA_ITEMS = env.int("AMBIENT_ATTENTION_EXTRA_ITEMS", default=2)
# The confirmation dialogue (Plan 06): at most this many new questions a day
# per person — reviews of explorations included — strongest evidence first,
# never on a weekend, never in a quiet period, never once shut off.
AMBIENT_QUESTIONS_PER_DAY = env.int("AMBIENT_QUESTIONS_PER_DAY", default=2)

# ---------------------------------------------------------------------------
# The knowledge core (apps.knowledge)
#
# Concepts and the evidenced edges people, projects, labs and works have to
# them — shared by collaboration matching and the ambient profile. See
# docs/plans/collaboration-network/01-knowledge-core.md.
# ---------------------------------------------------------------------------
# How close two wordings must be to count as one concept, as cosine similarity
# of their embeddings. Deliberately conservative: a wrong merge makes unrelated
# ideas look like the same one ("uses statistics" matching everything), while a
# missed merge only splits a count until someone merges it by hand.
KNOWLEDGE_MERGE_COSINE = env.float("KNOWLEDGE_MERGE_COSINE", default=0.92)
# A concept is a term, not a paragraph. A declared value longer than this is
# prose (a problem statement, a pasted abstract) and is not turned into a
# concept at all; requirement slots (CN-03) extract terms from prose instead.
KNOWLEDGE_MAX_SURFACE_CHARS = env.int("KNOWLEDGE_MAX_SURFACE_CHARS", default=120)
# Re-project a profile, lab or project into the graph when it is saved. The
# nightly sweep reconciles anything a missed hook left behind, so turning this
# off costs a day of staleness, not correctness.
KNOWLEDGE_PROJECT_ON_SAVE = env.bool("KNOWLEDGE_PROJECT_ON_SAVE", default=True)
# A person's own papers (plan CN-02): read once each, into facets and
# demonstrated edges. An import is read as soon as it lands; the nightly pass
# reads whatever is still unread within these caps (one model call per work)
# and looks up the OpenAlex field of works from other sources by DOI.
KNOWLEDGE_FACET_ON_IMPORT = env.bool("KNOWLEDGE_FACET_ON_IMPORT", default=True)
KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP = _cfg["nightly.knowledge_work_facets"]
KNOWLEDGE_FIELD_LOOKUPS_NIGHTLY_CAP = _cfg["nightly.knowledge_field_lookups"]

# ---------------------------------------------------------------------------
# Collaboration matching (apps.collab)
#
# What a funding call needs (requirement slots) and whether the reader and
# their own lab already cover it. See docs/plans/collaboration-network/.
# ---------------------------------------------------------------------------
# How close a slot must be to a concept someone holds to count as covered,
# as cosine similarity. Looser than the concept-merge threshold on purpose: a
# slot is a call's phrasing of a need, not a second name for the same idea.
COLLAB_COVERAGE_COSINE = env.float("COLLAB_COVERAGE_COSINE", default=0.80)
# Calls whose slots are read per night (one model call each, ever); new calls
# are read on arrival within the same budget.
COLLAB_SLOTS_NIGHTLY_CAP = _cfg["nightly.collab_slots"]
# Being findable (plan CN-04). Off by default; turning it on lasts this many
# months, with a reminder this many days before it ends. A person is shown to
# at most COLLAB_APPEARANCE_CAP distinct seekers a week, so the most sought-
# after people are not flooded. Verified scope reads the same affiliation
# directory the app's institution picker uses.
COLLAB_OPEN_MONTHS = env.int("COLLAB_OPEN_MONTHS", default=6)
COLLAB_RENEWAL_NOTICE_DAYS = env.int("COLLAB_RENEWAL_NOTICE_DAYS", default=14)
COLLAB_APPEARANCE_CAP = env.int("COLLAB_APPEARANCE_CAP", default=10)
# The matcher (plan CN-05). Searches run only when a seeker asks, never in the
# nightly run; outward search is launched at one institution. A work matches a
# lane's slot at COLLAB_LANE_MATCH_COSINE and counts as "different" below
# COLLAB_LANE_DIFFER_COSINE. The model reads each lane's shortlist and may drop
# a candidate, never add one.
COLLAB_SEARCH_ENABLED = _cfg["features.collab_search"]
COLLAB_MAX_SCOPE = env("COLLAB_MAX_SCOPE", default="institution")
COLLAB_LANE_MATCH_COSINE = env.float("COLLAB_LANE_MATCH_COSINE", default=0.70)
# A slot against one of a person's concepts (a short phrase) — higher than the
# sentence threshold, because short phrases for different methods sit close.
COLLAB_CONCEPT_MATCH_COSINE = env.float("COLLAB_CONCEPT_MATCH_COSINE", default=0.80)
COLLAB_LANE_DIFFER_COSINE = env.float("COLLAB_LANE_DIFFER_COSINE", default=0.55)
COLLAB_SHORTLIST_PER_LANE = env.int("COLLAB_SHORTLIST_PER_LANE", default=8)
COLLAB_RESULTS_PER_LANE = env.int("COLLAB_RESULTS_PER_LANE", default=3)
COLLAB_SEARCHES_PER_DAY = env.int("COLLAB_SEARCHES_PER_DAY", default=20)
# Graph features (plan CN-07). An introduction path is at most
# COLLAB_INTRO_MAX_HOPS co-authorships long and names only people open to the
# seeker. "Assemble a team" is offered for COLLAB_TEAM_MIN_GAPS or more gaps and
# proposes up to COLLAB_TEAM_MAX_SIZE people, trading match strength against
# co-authorship distance at COLLAB_TEAM_DISTANCE_WEIGHT per hop.
COLLAB_INTRO_MAX_HOPS = env.int("COLLAB_INTRO_MAX_HOPS", default=3)
COLLAB_TEAM_MIN_GAPS = env.int("COLLAB_TEAM_MIN_GAPS", default=3)
COLLAB_TEAM_MAX_SIZE = env.int("COLLAB_TEAM_MAX_SIZE", default=4)
COLLAB_TEAM_DISTANCE_WEIGHT = env.float("COLLAB_TEAM_DISTANCE_WEIGHT", default=0.15)
# Evaluation (plan CN-08). Search may widen past COLLAB_MAX_SCOPE only when,
# over the last COLLAB_WIDEN_WINDOW_DAYS, at least COLLAB_WIDEN_MIN_RATINGS
# results were rated, at most COLLAB_WIDEN_MAX_NOT_RELEVANT of them "not
# relevant", at most COLLAB_WIDEN_MAX_SHARE_AT_CAP of person-weeks sat at the
# appearance cap, and every harm check was zero. `collab_evaluation` reports
# it; the widening itself is a deliberate change to COLLAB_MAX_SCOPE.
COLLAB_WIDEN_WINDOW_DAYS = env.int("COLLAB_WIDEN_WINDOW_DAYS", default=28)
COLLAB_WIDEN_MIN_RATINGS = env.int("COLLAB_WIDEN_MIN_RATINGS", default=100)
COLLAB_WIDEN_MAX_NOT_RELEVANT = env.float("COLLAB_WIDEN_MAX_NOT_RELEVANT", default=0.5)
COLLAB_WIDEN_MAX_SHARE_AT_CAP = env.float("COLLAB_WIDEN_MAX_SHARE_AT_CAP", default=0.05)
COLLAB_INSTITUTIONS_PATH = env(
    "COLLAB_INSTITUTIONS_PATH",
    default=str(ROOT_DIR / "app" / "public" / "data" / "institutions.json"),
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

# --- Slack (ambient Plan 11) ------------------------------------------------------
# Off by default: the events endpoint answers 404 until it is on and a signing
# secret is set. Workspaces install the app through Slack's OAuth (client id and
# secret); requests are verified by signature before anything is read.
SLACK_ENABLED = _cfg["features.slack"]
SLACK_SIGNING_SECRET = env_str("SLACK_SIGNING_SECRET", "")
SLACK_CLIENT_ID = env_str("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = env_str("SLACK_CLIENT_SECRET", "")
# A request older than this is refused (Slack's own replay guidance).
SLACK_REQUEST_MAX_AGE_SECONDS = env.int("SLACK_REQUEST_MAX_AGE_SECONDS", default=300)
SLACK_LINK_CODE_MINUTES = env.int("SLACK_LINK_CODE_MINUTES", default=15)
SLACK_OUTBOX_RETRY_SECONDS = env.int("SLACK_OUTBOX_RETRY_SECONDS", default=300)
SLACK_OUTBOX_MAX_ATTEMPTS = env.int("SLACK_OUTBOX_MAX_ATTEMPTS", default=5)
SLACK_OUTBOX_BATCH_LIMIT = env.int("SLACK_OUTBOX_BATCH_LIMIT", default=50)

# --- Meeting transcripts (ambient Plan 11) ---------------------------------------
# Off by default. A transcript is read at the next hourly read and its text
# expires from the buffer after AMBIENT_TRANSCRIPT_TTL_HOURS (clamped by the
# buffer's own ceiling). Speech is cheap: what a meeting yields weighs
# AMBIENT_TRANSCRIPT_WEIGHT of the same thing said in writing, and only project
# developments (decisions, blockers, commitments) are kept.
AMBIENT_TRANSCRIPTS_ENABLED = _cfg["features.ambient_transcripts"]
AMBIENT_TRANSCRIPT_TTL_HOURS = env.int("AMBIENT_TRANSCRIPT_TTL_HOURS", default=3)
AMBIENT_TRANSCRIPT_WEIGHT = env.float("AMBIENT_TRANSCRIPT_WEIGHT", default=0.3)
AMBIENT_TRANSCRIPT_MAX_BYTES = env.int(
    "AMBIENT_TRANSCRIPT_MAX_BYTES", default=2_000_000
)

# --- Microsoft Teams (ambient Plan 11) ----------------------------------------------
# Off by default: the messaging endpoint answers 404 until it is on. Every
# request carries a Bot Framework JWT, verified (RS256, issuer, audience = the
# app id, the serviceUrl claim) against Microsoft's published keys before
# anything is read.
TEAMS_ENABLED = _cfg["features.teams"]
TEAMS_APP_ID = env_str("TEAMS_APP_ID", "")
TEAMS_APP_PASSWORD = env_str("TEAMS_APP_PASSWORD", "")
TEAMS_OPENID_CONFIG_URL = env_str(
    "TEAMS_OPENID_CONFIG_URL",
    "https://login.botframework.com/v1/.well-known/openidconfiguration",
)
TEAMS_TOKEN_ISSUER = env_str("TEAMS_TOKEN_ISSUER", "https://api.botframework.com")
TEAMS_TOKEN_URL = env_str(
    "TEAMS_TOKEN_URL",
    "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
)
TEAMS_OUTBOX_MAX_ATTEMPTS = env.int("TEAMS_OUTBOX_MAX_ATTEMPTS", default=5)
TEAMS_OUTBOX_RETRY_SECONDS = env.int("TEAMS_OUTBOX_RETRY_SECONDS", default=300)


# Each loaded tool's own settings, published last under their Django names so
# a tool's [tools.<name>] section (or the env var it answers to) always wins.
_tools_host.publish_settings(globals(), TOOLS_REPORT, INSTANCE)
CELERY_BEAT_SCHEDULE.update(_tools_host.beat_schedule(TOOLS_REPORT, INSTANCE))

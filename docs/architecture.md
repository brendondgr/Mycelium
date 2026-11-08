# Mycelium Architecture

**Scope:** how the system is put together and who owns what. For *where* code
lives, read [`repo-map.md`](repo-map.md). For HTTP shapes, read
[`api-contract.md`](api-contract.md). For product direction, read
[`purpose.md`](purpose.md) and [`goals.md`](goals.md).

Mycelium is a full-stack monorepo with **root-level orchestration**: editable
config (`compose.yaml`, `.env.example`, `package.json`, the systemd units) lives
at the repository root, and all implementation and install state lives under
`web/`, separated by service boundary.

## Tech stack

| Layer | Technology | Location |
|---|---|---|
| Public marketing site | Astro 6, Tailwind v4, MDX — no framework JS shipped | `web/landing/` |
| Authenticated app | Next.js 16 App Router, React 19, Tailwind v4, Radix UI, TanStack Query/Table | `web/app/` |
| Shared design tokens | Tailwind v4 theme | `web/packages/config/src/theme.css` |
| Backend API & orchestration | Django 5, Django REST Framework | `web/backend/` |
| Background work | Celery 5 + Beat | `worker` / `beat` services |
| Relational store | PostgreSQL 17 + pgvector | `postgres` service |
| Cache / broker / job state | Redis 8 | `redis` service |
| Embeddings | fastembed / ONNX Runtime (`BAAI/bge-small-en-v1.5`), CPU or CUDA | `tools/retrieval/embedding.py` |
| LLM | OpenAI-compatible endpoint (self-hosted vLLM is the reference target) | `apps/core/llm.py` |
| Decision model | TypeSafe System One (`jev-1.13.0`, remote). With `RERANK_METHOD=typesafe` it re-orders the top window of every theme's slate, one (theme, item) question per call, for paid plans; the local stack still does retrieval and the pool. Sends each target's profile text and the candidate's public text off-host per pair | `apps/core/systemone.py`, `tools/recommendation/typesafe_rerank.py` |
| Edge gateway | Nginx, single origin | `web/infra/nginx/` |
| Python deps & commands | `uv` | `web/backend/` |
| Node workspace | npm workspaces | `web/` |

**Declared but unused.** `compose.yaml` runs **Neo4j** and **MinIO**, and
`settings.py` reads their env vars, but no application code touches either —
the object-storage phase is not built, and the knowledge graph is built in
Postgres instead (`apps/knowledge`, below): its questions are one or two hops,
and deleting a person must cascade through foreign keys rather than a sync job
across two stores. Whether multi-hop features (introduction paths, team
formation) ever justify Neo4j is decided by measurement in collaboration-network
plan CN-07. `cytoscape` is an unused `web/app` dependency. Treat all three as
reserved, not as working infrastructure.

## Repository layout

```text
mycelium/
├── CLAUDE.md, README.md, Makefile, package.json, compose.yaml, .env.example   # root orchestration
├── ops/                           # everything that runs on the host, outside the containers
│   ├── mycelium                   # stack manager CLI (start/stop/status/install-service)
│   ├── compose.gpu.yaml           # GPU override for the embedding containers
│   ├── setup/                     # create_admin.py, bootstrap.py (`make setup`)
│   ├── nightly/                   # manual_all.py (the nightly run), manual_mylo.py, per-stage runners
│   ├── systemd/                   # unit templates installed by `mycelium install-service`
│   ├── loadtest/                  # onboarding load test
│   └── research/                  # research-record tooling behind `make validate-research`
├── tools/                         # modular research tools, one folder each (see "Tools" below)
│   └── _framework/                # discovery, the import script, config, events, nightly planner
├── mylo/                          # host Discord bot package + daily-run observability
├── eval/                          # retrieval evaluation harness (own uv project)
├── docs/                          # direction, reference, skills, changelog
└── web/
    ├── landing/                   # Astro public site
    ├── app/                       # Next.js authenticated app
    ├── packages/config/           # shared theme tokens
    ├── art/, scripts/             # artwork masters + sync/dev-gateway scripts
    ├── backend/                   # Django API + Celery
    │   ├── config/                # settings, urls, celery, asgi/wsgi
    │   └── apps/                  # Django apps (see boundaries below)
    └── infra/nginx/               # gateway config
```

## Tools

Research capabilities are **tools**: one folder each under `tools/`, declared by
one `Tool` class in `tools/<name>/tool.py`, discovered rather than wired in. The
platform (`web/backend/apps/`) is the host and does not import tools. A tool
reads another only through the modules it `exports`, and only if it lists it in
`depends_on`. A foundation tool publishes events instead of calling up into
what is built on it. These rules are AST-checked, and the platform's remaining
imports of tools are a shrinking allowlist (`tools/_framework/platform_imports.txt`).

**The import script decides what runs.** Before Django starts,
`tools/_framework/loader.py` walks the tools in dependency order. It checks each
one's declaration, configuration and secrets, then probes it: Django is
started in a subprocess with only that tool and its dependencies installed, and
the tool's modules are imported and its health check run. Each tool ends
`LOADED`, `DISABLED`, `MISSING`, `BLOCKED` or `FAILED`. Only `LOADED` tools
enter `INSTALLED_APPS`, the URL table (spliced at the position their include
always had), the Beat schedule, the Django settings namespace and the nightly
plan.

- **Isolation.** A tool that does not load contributes nothing, and neither does
  anything that depends on it. The nightly run reports each skipped stage.
- **Strict mode.** Production is lenient; `tools.strict` (on in the test suite)
  makes any failure fatal. A `core` tool stops startup in every mode.
- **Caching.** The report is cached in `data/tools/` under a fingerprint of the
  code and the configuration, so only a change re-probes.

**Configuration** is the same four-layer merge as the rest of `mycelium.toml`.
The universal `[tools]` section sits alongside one `[tools.<name>]` section per
installed tool. A tool's keys keep their old environment-variable names and are
published under their old Django setting names while the tool is loaded.

| Tool | Depends on | Core | Responsibility |
|---|---|---|---|
| `retrieval` (`tools/retrieval/`, Django label `content`) | — | yes | The grounded corpus, knowing nothing about people: OpenAlex / PubMed / Semantic Scholar paper sources with a scan window and cross-source dedup, the open-source grants/conferences collector (`collect/`, pure HTTP, in-container), the Illinois Fellowship Finder scraper + ingest (`fellowships/`; the host-side Playwright entry is `host/scrape_fellowships.py`), the fellowship eligibility rule engine (`eligibility/`), the device-aware embedder, the external DOI/arXiv/URL resolver, `ContentItem` and its deadline projection, liveness, duplicate merging (publishing `retrieval.items_merging` so each owner repoints its own rows), the pgvector index and BM25 (`index.py`, `lexical.py`, the `Retrievable`/`VectorIndex` protocols), and corpus search. It keeps the `content` app label because the corpus tables and their migration history were created under it and the platform's `collab` and `knowledge` migrations depend on that history |
| `recommendation` (`tools/recommendation/`) | `retrieval` | yes | Ranking and filtering against profiles: the whole-corpus nightly ranking for every person, lab, department and project (`pipeline.py` for papers, `opportunities.py` for grants, conferences and fellowships), fusion, rerank, cluster admission, per-theme slates and the Top-25, model write-ups and verdicts, who-is-this-for and team profiles, refits on sign-up and profile edits. Owns `RelevanceScore`, `ItemComprehension`, `ProjectProfile`, `RelevanceEvent` (tables unchanged, label `recommendation`). Departments are scored only for whatever registers them through `service.register_department_source` (announcements do); recommendation never imports the delivery code |
| `delivery` (`tools/delivery/`) | `retrieval`, `recommendation` | yes | Puts what was ranked in front of people: the API the web app reads (feeds, saves, ignores, search, briefings, reminders, notifications, announcements), mounted at `api/` where the old include was; the daily briefing and PDF report, the Monday weekly, lab digests, Discord and Slack delivery, deadline reminders, project alerts and reflections, opportunity announcements, the share fan-out and collections. Owns the 22 models of what people do with items (label `delivery`, tables unchanged). Subscribes to `retrieval.items_merging`, registers announcement departments with recommendation, and marks reminders stale on Django's `pre_delete` of a `ContentItem` |

The folder guide is [`tools/README.md`](../tools/README.md); agent rules are in
[`skills/tools.md`](skills/tools.md).

## Service boundaries

**The browser never talks directly to Postgres, Redis, the worker, or the vector
store** — only to the public site and, through the Next.js proxy, the Django API.

| Concern | Owner | Notes |
|---|---|---|
| Public content | `web/landing/` (Astro) | Marketing, explanation, sign-up and self-hosting routes; no private data |
| Authenticated app behavior | `web/app/` (Next.js) | Session-gated UI; calls the API via a same-origin proxy |
| Backend orchestration | `web/backend/` (Django + DRF) | Auth, permissions, business logic, admin, audit, API contracts |
| Background work | Celery worker + Beat | Reminder ticks, outbox drain, project-profile recompute, seeding |
| Scheduled pipeline | Host `mylo-daily.timer` → `ops/nightly/manual_all.py` | The nightly research run (see below) |
| Discord gateway | Host `mylo-bot.service` → `python -m mylo.bot` | Slash commands, drift events, run observability |
| Data storage | Postgres / Redis | Durable records, vectors, queue/cache |

Single-origin routing through Nginx at `http://localhost:11050`:

| Path | Service |
|---|---|
| `/` and public pages | Astro landing |
| `/login`, `/signup`, `/app/*`, `/_next/*` | Next.js app |
| `/api/*`, `/admin/*` | Django |

**Why the nightly run is split across host and container.** `ops/nightly/manual_all.py` runs
on the host but executes almost every stage *inside* the backend container, where
the database and the PDF renderer are. Exactly one stage is genuinely host-bound:
the Illinois Fellowship Finder scrape (`tools/retrieval/host/scrape_fellowships.py`), which drives
Playwright the container does not carry. The grants/conferences collector is pure
HTTP and runs in-container like everything else. A third stage, the weekly dblp
venue-registry refresh (`refresh_dblp_registry`), is also in-container but sits on
its own slower cadence and **must precede** the conference collection, because the
collector's resolve stage joins against that cache for venue identity and ranks.

**Opportunity announcements** run as two in-container stages after scoring and
before the briefings: `announce_opportunities` (one Discord forum thread per newly
fitting grant, fellowship or conference, per server binding) and
`announce_opportunity_updates` (changed calls updated in place, nudges, the
closing-soon list, closing finished threads). Both exit 0 when a target fails, so
they never stop the run, and both do nothing while
`OPPORTUNITY_ANNOUNCEMENTS_ENABLED` is off.

## Backend app boundaries

| App | Responsibility |
|---|---|
| `core` | Shared infrastructure: health endpoint, the pgvector extension migration, the exactly-one-FK helper (`db.py`), the OpenAI-compatible LLM client (`llm.py`), and transactional email (`mail/`) |
| `accounts` | Identity & organization: users, profiles, departments, labs, memberships, permission roles, academic titles, audit events, derived membership. Owns session auth (CSRF, login/logout/me), the invite-only sign-up gate, lab invitations, the interests contract, and profile/lab intake (`intake/`) |
| `research` | Projects scoped to a user, lab, or department: membership, visibility over the org hierarchy, plan-gated creation and archiving, team collaboration (shares, feed, link ingest, seen ledger, events), and collections |
| `billing` | Subscriptions, per-seat billing, add-ons, and tier-based entitlement resolution. `entitlements.py` is the single read path; an expired plan reverts to Free at read time with no cleanup job. It is a module the instance switches on (`billing.mode` in `mycelium.toml`): with billing off (the default) no tier decides anything — every feature is granted and every limit comes from `[limits]` or a staff override; with `subscriptions` the limits come from `[limits.tiers.*]`, and features are withheld only if `billing.enforce_features` is also on |
| `integrations` | Discord identity and lab linking: OAuth, activation codes, guild install, the durable outbox, and the single ORM boundary in `services/resolve.py` |
| `ambient` | The evidence ledger for what Mylo understands from the lab's own conversation: connected surfaces and their consent, one person's per-platform opt-in, the transient raw-message buffer, the adapter contract, retention and deletion. **Ships off** (`AMBIENT_ENABLED=false`). Imports `integrations` and `research`; `content` reads it only through `ambient/read.py`, which an AST test enforces. Raw message text never reaches Postgres — it lives in Redis under a TTL and is deleted once a window has been read. The Mylo gateway writes to it only through `ambient/service.py`, in process, the way `integrations/services/resolve.py` already works; there is no HTTP ingest endpoint. Each message is attributed to a project on arrival from cheap deterministic signals, with a floor and a margin and an honest "unresolved" (`attribution.py`); the read re-scores what that left unresolved with semantic similarity and re-checks every speaker's eligibility first. `ProjectAttention` (7- and 28-day shares per person per project) is derived nightly. Project editors see and correct attributions at `/api/ambient/`. **Reading and deciding are split (Plan 04):** an hourly Beat task reads conversations that have gone quiet — within the buffer's TTL — into grounded observations (model-written, no quotes, no rule-based fallback) and links each topic to a concept through `knowledge/service.py`; a nightly step in `ops/nightly/manual_all.py` decides, per person and topic, one outcome (ignore, record, suggest, capability, propose, ask) from consistency across days and conversations, what the person already holds, and what they declined, and has the model explain it from its own notes. Deciding ships off (`AMBIENT_DELIBERATE_ENABLED=false`). **The evolving layer (Plan 05)** sits beside the declared profile and never inside it: suggestions become *pending* conversational edges in `apps/knowledge` (ranking nothing until the person says yes), told project facts become active `ProjectDevelopment`s with undo, ambient ones pending; confirmed explorations can join a person's paper search as their own down-weighted themes (`AMBIENT_DRIFT_ENABLED`, off); confirmed preferences, direction and learning goals reach the prompts; closed blockers and dropped methods reach the alerts; each report carries a `context_version`. **Asking and changing (Plans 06–09):**
- Nightly questions (`dialogue.py`) are answered by button or in the person's own words. A reader model maps a reply to a choice, and a chosen no is never recorded as a yes.
- Every answer is an append-only `ValidationRecord`.
- A yes that edits the declared profile is applied at the next nightly run through the interests contract, with provenance and an exact undo (`apply.py`, the only writer of `Profile.interests` here).
- A project's stated state changes only when an editor accepts a reflection proposal.
- Every change that took effect is an `AppliedChange` with undo, shown on the "Mylo & you" page and in the weekly's code-rendered "What changed" (`content/weekly_changes.py`, cited `[O#]`). A personal change can never match a lab query.

**Evaluation (Plan 10):** `evaluation.py` computes validation precision and ten harm checks (`evaluate_ambient`).

**Other platforms (Plan 11), all off:**
- Slack and Teams arrive at backend endpoints in `integrations`. These are their gateways, and the only backend modules allowed the `service.py` door. Each has its own single ORM boundary (`slack_resolve`, `teams_resolve`).
- Meeting transcripts are uploaded as one window each and yield project developments only. |
| `knowledge` | The knowledge graph, in Postgres: `Concept`s (one idea — a problem, method, setting, or research area — independent of who holds it) and `Edge`s from a person, project, lab, work, or content item to a concept, each carrying its **tier** — `declared` (a profile or a project's stated state), `demonstrated` (the person's papers, plan CN-02), or `conversational` (ambient understanding, pending until the person confirms it). Declared profiles and projects are mirrored in on save (a queued task) and reconciled by a 04:15 Beat sweep; nothing writes back to a profile. A model-free linker resolves wordings to concepts by alias, then embedding (cosine ≥ `KNOWLEDGE_MERGE_COSINE`), then minting; concepts minted from a private source stay in their owner's scope and reach the shared vocabulary only by promotion under a shared source's wording. People's own imported papers are read once each (`works.py`: a sentence and short terms per facet, a field-neutral restatement of the method, a vector per facet) and become `demonstrated` edges per work and rolled up per person (`demonstrated.py`) — on import and in a capped nightly step; they never shape the person's own ranking. Read through `knowledge/read.py`, whose functions each fix the tiers they may return — `discoverable_edges` can never return conversation — and written through `knowledge/service.py`; an AST test holds everything else behind the two doors. Depends on `accounts`, `research`, and the corpus embedder; nothing above it |
| `collab` | Collaboration matching on the knowledge core. So far: a funding call's **requirement slots** (problem, method, data, or a partner role; required or not), read once per call text apart from its verified extraction, and the **team-fit line** — which slots the reader, or their lab's stated profiles, already cover — stored on each grant score at scoring time and shown on grant cards. Reads the knowledge core only through `knowledge/read.py`'s functions that cannot return conversation (AST-enforced). `team_gap` reads required slots once they exist. **Being findable** is off by default: a person chooses an audience (institution, country, anywhere) judged on the institution their *verified* email's domain belongs to in the affiliation directory — a personal address can be neither found nor search, and no seeker looks past their own country — it lapses after six months, a person is shown to at most ten distinct seekers a week, and a preview shows exactly what a seeker would see. **Finding collaborators** (Q4) runs only when a seeker asks, from a call, a project or their own words: a hard gate (open, mutually visible, not a lab-mate or co-author, under the cap), four lanes (a method from another field, the same problem by another approach, the data, and in one's own field) filled slot by slot, and a model rerank that can drop a person and never add one; results are coarse pointers from declared or paper evidence only. The **co-authorship graph** (`knowledge.Coauthorship`, rebuilt by the nightly sweep) gives introduction paths through consenting people, "outside my network", and team formation — kept in Postgres (research decision D-007). The collaboration daily task runs six **harm checks** and logs an error on any non-zero; `run_analytics` carries the counts |
| `adminpanel` | Platform-admin API (staff/superuser only): user and lab rosters, subscription assignment, watch quotas. Every write records an `accounts.AuditEvent`. Mounted at `/api/admin/` |

There is no `graph`, `reports`, or `planner` app. Reporting lives in the `delivery` tool;
query-planning logic lives in `accounts/intake/agent.py` and `core/llm.py`; the
graph phase has not started.

## Data ownership

- **PostgreSQL + pgvector** — the source of truth for everything: users, labs,
  departments, memberships, permissions, profiles, projects, content items,
  relevance scores, saves, deadlines, reminders, notifications, subscriptions,
  seats, Discord identities, the outbox, and audit logs. Vector columns
  (`Profile.embedding`, `Project.embedding`, `ContentItem.embedding`) carry
  semantic vectors; `ContentItem.search_vector` is a trigger-maintained tsvector
  and there is a pg_trgm title index for fuzzy search.
- **Redis** — Celery broker/result backend plus several named caches (`signup`
  lockouts, the `scan` status flag, query embeddings). The `ambient`
  raw-message buffer has **its own instance** (`redis-ambient`, started with
  `--save "" --appendonly no` and no volume): it is the only store that ever
  holds a person's actual words, it holds them under a TTL measured in hours,
  and nothing copies them to Postgres or to disk — including a Redis snapshot.
  Inside Docker `AMBIENT_CACHE_URL` points at it; the host gateway reads it from
  `.env`. Unset, it falls back to db 6 of the main Redis, which persists.
- **Filesystem** — Discord outbox attachments (`DISCORD_OUTBOX_ATTACHMENT_DIR`)
  and the daily-run state file. Object storage is not wired up.

## Configuration & secrets

- **Operator policy lives in `mycelium.toml`** at the repo root (git-ignored;
  `mycelium.example.toml` is the committed `lab` template). It holds billing,
  limits, sign-up, email, optional features and nightly cost controls, resolved
  by `web/backend/config/instance.py` in four layers: built-in defaults →
  deployment profile (`personal` / `lab` / `department` / `institution`) →
  `mycelium.toml` → environment variables. Each key still answers to its old
  environment name (`AMBIENT_ENABLED`, `SIGNUP_GRANT_TIER`, ...), and
  `settings.py` re-exports the resolved values under those names. An invalid
  file stops the process at boot with the key that is wrong. `instance.py` is
  standard-library only so host tooling reads the same definitions. Secrets
  never go in the file.
- Settings load through **django-environ**. `config/settings.py` reads the root
  `.env` **and** `.env-mylo` (the Discord bot's token and channel ids — Django
  needs them too), then falls back to environment variables and safe defaults
  (SQLite when `DATABASE_URL` is unset).
- `.env.example` documents every *environment-only* variable (secrets,
  infrastructure, tuning); keys governed by `mycelium.toml` are listed there as
  pointers only, because a value in an env_file would override the file. Real
  `.env` files are git-ignored.
- `compose.yaml` overrides per-service URLs so containers reach `postgres:5432`
  and `redis:6379` on the Compose network, while host tooling uses the published
  `11450` / `11550` ports.

| Group | Variables |
|---|---|
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `PUBLIC_HOSTNAME` |
| Frontend wiring | `NEXT_PUBLIC_API_BASE_URL`, `API_INTERNAL_URL` |
| Data services | `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| LLM | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_REASONING`, `LLM_REASONING_STYLE`, `LLM_THINKING_BUDGET` |
| TypeSafe | `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` (pinned version, never `jev-latest`), `TYPESAFE_BASE_URL`, `TYPESAFE_TIMEOUT`, `TYPESAFE_MAX_RETRIES` |
| Slate reranker switch | `RERANK_METHOD` (`typesafe` default, or `local`), `TYPESAFE_RERANK_WINDOW`, `TYPESAFE_RERANK_CONTENT_TYPES`, `TYPESAFE_RERANK_CONCURRENCY`; `OPPORTUNITY_LLM_CONCURRENCY` for the opportunity scorer and `WRITEUP_LLM_CONCURRENCY` for the précis and per-theme write-up calls |
| Embedding | `EMBEDDING_DEVICE` (`auto`/`cuda`/`cpu`), `EMBEDDING_BATCH_SIZE_CPU`, `EMBEDDING_BATCH_SIZE_GPU` |
| Sign-up | `[signup]` in `mycelium.toml` (`mode` = `closed`/`invite`/`code`/`domain`/`open`, `allowed_domains`, `verify_email`); the code mode's secret `SIGNUP_ACCESS_CODE` (no default) and its ban `SIGNUP_CODE_MAX_FAILURES`, `SIGNUP_CODE_FAILURE_WINDOW_SECONDS`, `SIGNUP_CODE_LOCKOUT_SECONDS`. Logic in `apps/accounts/signup_policy.py` |
| Discord (`.env-mylo`) | `DISCORD_API_KEY`, `ERROR_CHANNEL`, `ACTIVATION_CHANNEL`, `SUMMARY_CHANNEL` |
| Email | `[email]` in `mycelium.toml` (`provider` = `none`/`resend`/`smtp`, `from`, `reply_to`, `smtp_*`); secrets `RESEND_API_KEY`, `EMAIL_HOST_PASSWORD`; `EMAIL_APP_BASE_URL`. The old `EMAIL_ENABLED=true` still means `resend` |
| Run analytics | `RUN_ANALYTICS_JSON_PATH`, `RUN_ANALYTICS_PDF_DIR`, `RUN_ANALYTICS_RETENTION_DAYS` |
| Opportunity collector | `COLLECT_CONTACT` |
| Knowledge core | `KNOWLEDGE_MERGE_COSINE`, `KNOWLEDGE_MAX_SURFACE_CHARS`, `KNOWLEDGE_PROJECT_ON_SAVE`, `KNOWLEDGE_SWEEP_HOUR`, `KNOWLEDGE_FACET_ON_IMPORT`, `KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP`, `KNOWLEDGE_FIELD_LOOKUPS_NIGHTLY_CAP` |
| Collaboration | `COLLAB_COVERAGE_COSINE`, `COLLAB_SLOTS_NIGHTLY_CAP`, `COLLAB_OPEN_MONTHS`, `COLLAB_RENEWAL_NOTICE_DAYS`, `COLLAB_APPEARANCE_CAP`, `COLLAB_INSTITUTIONS_PATH`, `COLLAB_SEARCH_ENABLED`, `COLLAB_MAX_SCOPE`, `COLLAB_LANE_MATCH_COSINE`, `COLLAB_CONCEPT_MATCH_COSINE`, `COLLAB_LANE_DIFFER_COSINE`, `COLLAB_SHORTLIST_PER_LANE`, `COLLAB_RESULTS_PER_LANE`, `COLLAB_SEARCHES_PER_DAY`, `COLLAB_INTRO_MAX_HOPS`, `COLLAB_TEAM_MIN_GAPS`, `COLLAB_TEAM_MAX_SIZE`, `COLLAB_TEAM_DISTANCE_WEIGHT`, `COLLAB_WIDEN_WINDOW_DAYS`, `COLLAB_WIDEN_MIN_RATINGS`, `COLLAB_WIDEN_MAX_NOT_RELEVANT`, `COLLAB_WIDEN_MAX_SHARE_AT_CAP` |
| Reserved (unused) | `NEO4J_*` (the co-authorship graph stays in Postgres, D-007), `S3_*` |

`COLLECT_CONTACT` is the one variable that does **not** go through django-environ:
`tools/retrieval/collect/core/http.py` reads it from `os.environ` **at import time**,
because it names the address in the outbound `User-Agent` every public source sees.
Setting it after Django has loaded has no effect, and — like the run-analytics
paths — a bare `KEY=` in an env_file arrives as an empty string and beats the
default, so `.env.example` ships it commented out rather than blank. The
extraction stage adds no variables of its own; it calls the same `LLM_*` client
every other model caller routes through.

`PUBLIC_HOSTNAME` backs every absolute URL Mycelium emits. Leaving it blank once
published `localhost` links into a lab's Discord channel; links that leave the
building now fall back to the public site rather than loopback.

Transactional email (`apps/core/mail/`) is the transport for anything that must
reach an inbox rather than a Discord DM — password resets, lab and department
invitations, verification codes — because those recipients are by definition not
yet linked to Discord. It is wired as a Django `EMAIL_BACKEND` over the Resend
API, so `django.core.mail` and Django's own password-reset machinery route
through it without a second transport to configure; `send_email` sits on top for
templated product mail, rendering a matched HTML and plain-text pair from
`web/backend/templates/email/`. There is no queue behind it: a flow that needs
delivery to survive an outage should copy the durable outbox in
`apps/integrations/services/outbox.py` rather than reinvent it.

`email.provider` defaults to **`none`** and unset falls back to Django's console
backend, because real mail is irreversible and a development mistake reaches real
addresses. Two operational cautions: the sending domain must carry SPF, DKIM and
(for Gmail) DMARC or the API accepts a message that is then silently dropped, and
the API key is send-only, so acceptance is visible here while delivery is only
visible in the Resend dashboard. `manage.py send_test_email --to <addr>` exercises
the whole path.

Account security rides that transport. Two mechanisms carry it: a six-digit code
(`apps/accounts/email_verification.py`) proving control of an address, and a
password reset link (`apps/accounts/password_reset.py`) signed by Django's own
`default_token_generator` — keyed on the current password hash, so a link dies
when it is used and `PASSWORD_RESET_TIMEOUT` bounds the rest. Codes are scoped to
a purpose (sign-up, email change, password change) and looked up by it, which is
a security property rather than bookkeeping: no flow can spend another's proof.

**A signed-in session is not authority over the password, and neither is the old
password.** Both routes to a new password — the signed-out link and the Account
page's code — demand exactly one thing: control of the account's mailbox. The
Account page does not ask for the current password, because the person changing a
password is very often the person who cannot remember it, and because anyone able
to satisfy such a check could sign out and take the same account through reset.
Requiring it would have blocked the common case while securing nothing. Changing
the *address* is the exception and does ask, since the mailbox is what proves a
password change and moving it is the one move that turns a borrowed browser into
a takeover.

Asking for a reset, by contrast, changes nothing at all: `request_reset` only
mails a link, so an unauthenticated endpoint can never be used to lock a stranger
out by typing their address.

**An institution is proved, never typed.** `Profile.institution` mirrors what
the verified address's domain resolves to in the affiliation directory
(`web/app/public/data/institutions.json`, read by `apps/accounts/institution.py`);
it is written only there, at verification and on the collaboration app's reads,
and every write path refuses a different one. The country that institution sits
in is the only location Mycelium knows. Collaboration scope, fellowship
eligibility and every "who this is for" line read that proved value, so claiming
an institution means holding a mailbox there.

**Verification is activation.** An account that has not answered a code sent to
its own address may sign in and browse, but cannot create a lab or department,
edit either's profile, or send an invitation — `require_verified_email` in
`apps/accounts/permissions.py` is the single gate. The reason is outward-facing:
Mycelium mails invitations to people who have never heard of it, so an account
whose own inbox has never replied does not get to originate that mail. The gate
sits on those writes rather than on sign-up because registration provisions the
org row inside its own transaction, at an instant when nobody is verified yet.
Email uniqueness is enforced by a partial unique index on `LOWER(auth_user.email)`
as well as by the serializer, because reset now looks an account up by address.

The LLM client supports structured reasoning levels (`none`/`low`/`medium`/
`high`) sent either as `reasoning_effort` (`LLM_REASONING_STYLE=effort`) or as a
`chat_template_kwargs.enable_thinking` toggle, and reads back the server's
separated `reasoning_content`. It lazily imports the `openai` SDK and accepts an
injected transport, so tests run fully offline. The optional `llm-tunnel` Compose
service is an SSH forward to a remote LLM host, run inside the Compose network.

## Ranking, the slate, and what counts as new

The nightly run **ranks the whole corpus** for every target against the profile
that target has that night, and re-establishes each feed from that ranking. Rank is
the fused BM25 + embedding order (`fusion.py`) and nothing else: a language-model
verdict explains an item, it never moves one.

**What a grant or conference ranks *on* did change.** Since the open-collector
migration, an opportunity's embedded text is not its raw source description — it
is a schema-checked, model-written extraction, verified by deterministic code
(bounds, venue identity, prose grounding, topic grounding, no invented specifics)
before it is stored, shown, or embedded. That was the point: raw source text is
not a uniform basis, since one funder writes ten times longer than another and
conference rows carry no CFP text at all. A record whose extraction fails every
bounded attempt is **refused** — it falls back to truncated raw text so it stays
retrievable, shows no AI summary, and records the fact in
`metadata["search_text_source"]` (`extracted` | `raw`), so a degraded run is
queryable and re-runnable rather than invisible. Ordering logic itself is
untouched, and the conference rank badges (CCF / CORE / THCPL) are **display
only** — they never enter relevance, thresholds, or the verdict. The
embedding basis moving is nonetheless a relevance change, and per
`docs/skills/global.md` any claim about its effect is an experiment under
`docs/research/experiments/`, not an assertion here.

Cost is contained by carry-forward rather than by narrowing the scan. A verdict
Mylo has already written is reused (`opportunity_llm.load_prior_llm_verdicts`), so
what re-ranking nightly costs is retrieval. Items that drop out of a ranking are
**retired, not deleted** (`opportunities._retire`): they lose `signals.suggested`
and their slate place but keep the verdict, so an item that dips out and returns
costs no second model call.

Refitting (`refit_*`, `run_refitting`, `ops/nightly/manual_mylo.py`) is still a separate
on-demand pass, run at sign-up and after a profile or focus edit. What makes it
different is `reuse_prior=False`: it re-sends every surfaced item to the model,
which is what a profile edit wants and what a nightly run must never do.

Each target keeps a **slate** per category — its top `top_feed.TOP_N` (25) by
relevance, recorded on the score rows as `top_rank` / `entered_top_on` /
`is_new_top`. The slate is the unit of the daily report, and **new means entered
the slate**, not arrived in the corpus. That inverts the test an item has to pass:
it is worth announcing when it is good enough to displace something the reader was
already being shown. It also makes the report answer to the reader — change a
focus, a cluster, or a watch term and the slate re-ranks, so whatever that change
promotes is reported as new, with no separate machinery.

The **daily report** (`briefing.report_scores`) shows the slate, every day, and
flags the entrants. Only entrants Mylo has not already written up go to the model;
the rest keep the write-up they have. When nothing entered, yesterday's body is
carried forward verbatim (`DailyBriefing.Origin.CARRIED`) rather than re-worded to
reach the same conclusions. Both the written briefing and the PDF read through that
one function, so they can never disagree about what the reader is being shown.

Feed reads still accumulate across runs (`views._accumulated_scores`,
`briefing._suggested_scores`), capped by `OPPORTUNITY_FEED_MAX`; the feed's own
week-long "New" pin is a separate, unchanged signal about arrival. Papers are the
exception to accumulation: retrieval is scoped to the latest gather batch, so the
Research Papers page shows only the current day's search.

`resend_user_report --user` and `repost_lab_report --lab` re-render and re-deliver
one target's report on demand (`content/report_resend.py`). They take their own
outbox dedupe key, because the daily key is per-day and made every same-day
re-send a silent no-op.

## Nightly run analytics

The nightly run measures itself. A final, non-fatal `run_analytics_report` stage
reads the rows the run just wrote — coverage, discovery, recommendations, report
delivery — plus the per-day LLM ledger (`core.LLMUsageDaily`, written from
`apps.core.llm.LLMClient.complete`, which is the one seam every LLM caller routes
through). It leaves the metrics at `RUN_ANALYTICS_JSON_PATH` and a PDF in
`RUN_ANALYTICS_PDF_DIR`.

The split exists because the two halves run in different worlds: the stages
execute in the backend container, where the database and the PDF renderer live,
while the Discord summary is posted from the **host**, by the same stdlib-only
runner that already reports a failed stage. The JSON file under the shared
`data/` bind mount is the seam; `mylo/analytics.py` reads it back and formats the
tables and bar charts, and `mylo/reporting.py` posts them with the PDF attached.

Both halves see the same bytes under **different roots** — `/app` inside the
container, the checkout path on the host — so the metrics file records the PDF's
location twice: `pdf_path` (the writer's own absolute path) and `pdf_relpath`
(relative to the shared root). The host resolves the attachment through
`analytics.resolve_pdf`, which re-anchors the relative form on its own checkout;
handing the container path straight to the reporter cost the attachment silently,
because an unreadable file is logged and the summary posts without it.

Both paths must also be left **unset** rather than set-and-blank. `.env.example`
is an env_file for the backend and worker, so a bare `KEY=` arrives as an empty
string and beats the setting's default; the empty path became `Path(".")`, which
put the PDF in the working directory and failed the JSON write outright. The data
paths therefore read through `env_str`, which treats blank as unset.

Measurement is deliberately outside `CONTAINER_STAGES`: a failure there means
users did not get their day, whereas a failure here only costs the summary its
detail. The run still announces itself either way.

## The ranking-stack seams

`tools/retrieval/protocols.py` declares two structural protocols so the ranking
stack can run without a database — which is what lets an offline harness measure
the *production* code instead of a copy of it.

- **`Retrievable`** — a candidate the stack can score: a stringable `id`, a
  `metadata` dict, and an optional `embedding`. `ContentItem` satisfies it
  already; `lexical.py`, `fusion.py`, and `ranking.py` annotate against it. This
  is a typing change only, with no runtime effect.
- **`VectorIndex`** — anything that answers nearest-neighbour queries.
  `retrieval.PgVectorIndex` wraps the existing pgvector query and is what
  production uses; `pipeline._build_pool` takes an optional `index` that defaults
  to it, and that single parameter is the entire integration surface.

The substitution is exact, not approximate: there is **no ANN index** on
`ContentItem.embedding` (no `hnsw`, no `ivfflat`), so every production vector
query is already a sequential scan ordered by cosine distance. An in-memory
index therefore computes the identical ranking. See `docs/evaluation.md`.

## Running locally

| Goal | Command |
|---|---|
| Full stack, single origin | `docker compose up` (or `make up`) → `http://localhost:11050` |
| Backend + data services only | `docker compose up backend` |
| Host dev gateway | `npm run dev` |
| Backend management command | `uv run --project web/backend python web/backend/manage.py <cmd>` |
| Backend tests | `npm run test` (or `uv run --directory web/backend python -m pytest`) |
| GPU embedding | `docker compose -f compose.yaml -f ops/compose.gpu.yaml up` |

Without `DATABASE_URL`, Django uses SQLite for quick checks — but pgvector tests
skip there, so anything touching vectors needs the Compose Postgres. Embedding
migrations depend on `core.0001_enable_pgvector`, so a fresh database provisions
the `vector` type before any table that uses it.

## The embedding model cache

The FastEmbed/ONNX model (`qdrant/bge-small-en-v1.5-onnx-q`, ~65–90 MB) downloads
lazily on first use into `data/models/fastembed/`, which `FASTEMBED_CACHE_PATH`
in `compose.yaml` points the backend and worker at through the `.:/app` bind
mount. It is git-ignored with the rest of `data/`, survives container recreates,
and re-downloads if deleted. Warm it once before a large concurrent run (a burst
of first requests can race the download):

```bash
docker compose exec -T backend uv run --project web/backend python -c \
  "from tools.retrieval.embedding import get_default_embedder; get_default_embedder()(['warm up'])"
```

GPU embedding needs the GPU flavour of fastembed, because plain `fastembed`
depends on the CPU-only `onnxruntime`: `uv sync --project web/backend --extra
embeddings-gpu` for the backend, `uv sync --no-group embeddings-cpu --group
embeddings-gpu` for the root runner env, or the `ops/compose.gpu.yaml` override for
containers (needs the nvidia-container-toolkit). `manage.py embedding_device
--benchmark` reports what is actually running; a CPU fallback is silent by
design. Both paths run the same graph, so stored vectors stay valid when the
device changes.

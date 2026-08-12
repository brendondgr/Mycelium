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
| Embeddings | fastembed / ONNX Runtime (`BAAI/bge-small-en-v1.5`), CPU or CUDA | `apps/scraper/embedding.py` |
| LLM | OpenAI-compatible endpoint (self-hosted vLLM is the reference target) | `apps/core/llm.py` |
| Edge gateway | Nginx, single origin | `web/infra/nginx/` |
| Python deps & commands | `uv` | `web/backend/` |
| Node workspace | npm workspaces | `web/` |

**Declared but unused.** `compose.yaml` runs **Neo4j** and **MinIO**, and
`settings.py` reads their env vars, but no application code touches either — the
graph phase and object-storage phase are not built. `cytoscape` is an unused
`web/app` dependency. Treat all three as reserved, not as working infrastructure.

## Repository layout

```text
mycelium/
├── CLAUDE.md, README.md, package.json, compose.yaml, .env.example   # root orchestration
├── run.py, manual_all.py, manual_mylo.py, pivot.py                  # host runners
├── mycelium*.service, mylo-daily.{service,timer}, mylo-bot.service  # systemd units
├── mylo/                          # host Discord bot package + daily-run observability
├── utils/                         # per-stage manual runners, vendored grants prototype
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

## Service boundaries

**The browser never talks directly to Postgres, Redis, the worker, or the vector
store** — only to the public site and, through the Next.js proxy, the Django API.

| Concern | Owner | Notes |
|---|---|---|
| Public content | `web/landing/` (Astro) | Marketing, pricing, explanation; no private data |
| Authenticated app behavior | `web/app/` (Next.js) | Session-gated UI; calls the API via a same-origin proxy |
| Backend orchestration | `web/backend/` (Django + DRF) | Auth, permissions, business logic, admin, audit, API contracts |
| Background work | Celery worker + Beat | Reminder ticks, outbox drain, project-profile recompute, seeding |
| Scheduled pipeline | Host `mylo-daily.timer` → `manual_all.py` | The nightly research run (see below) |
| Discord gateway | Host `mylo-bot.service` → `python -m mylo.bot` | Slash commands, drift events, run observability |
| Data storage | Postgres / Redis | Durable records, vectors, queue/cache |

Single-origin routing through Nginx at `http://localhost:11050`:

| Path | Service |
|---|---|
| `/` and public pages | Astro landing |
| `/login`, `/signup`, `/app/*`, `/_next/*` | Next.js app |
| `/api/*`, `/admin/*` | Django |

## Backend app boundaries

| App | Responsibility |
|---|---|
| `core` | Shared infrastructure: health endpoint, the pgvector extension migration, the exactly-one-FK helper (`db.py`), and the OpenAI-compatible LLM client (`llm.py`) |
| `accounts` | Identity & organization: users, profiles, departments, labs, memberships, permission roles, academic titles, audit events, derived membership. Owns session auth (CSRF, login/logout/me), the invite-only sign-up gate, lab invitations, the interests contract, and profile/lab intake (`intake/`) |
| `research` | Projects scoped to a user, lab, or department: membership, visibility over the org hierarchy, plan-gated creation and archiving, team collaboration (shares, feed, link ingest, seen ledger, events), and collections |
| `content` | The matching and delivery layer — the largest app. Deduplicated `ContentItem`s, per-target `RelevanceScore`s, the four feeds, clustering and fusion, the daily briefing and PDF report, saves, addressable deadlines, reminders, notifications, unified search, member fit, and the Discord digest producers |
| `billing` | Subscriptions, per-seat billing, add-ons, and tier-based entitlement resolution. `entitlements.py` is the single read path; an expired plan reverts to Free at read time with no cleanup job |
| `integrations` | Discord identity and lab linking: OAuth, activation codes, guild install, the durable outbox, and the single ORM boundary in `services/resolve.py` |
| `adminpanel` | Platform-admin API (staff/superuser only): user and lab rosters, subscription assignment, watch quotas. Every write records an `accounts.AuditEvent`. Mounted at `/api/admin/` |
| `scraper` | Ingestion: OpenAlex / PubMed / Semantic Scholar paper sources with a scan window and cross-source dedup, the Pivot-RP (ProQuest) grants / conferences / fellowships importer, the device-aware embedder, and the external DOI/arXiv/URL resolver |

There is no `graph`, `reports`, or `planner` app. Reporting lives in `content`;
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
  lockouts, the `scan` status flag, query embeddings).
- **Filesystem** — Discord outbox attachments (`DISCORD_OUTBOX_ATTACHMENT_DIR`)
  and the daily-run state file. Object storage is not wired up.

## Configuration & secrets

- Settings load through **django-environ**. `config/settings.py` reads the root
  `.env` **and** `.env-mylo` (the Discord bot's token and channel ids — Django
  needs them too), then falls back to environment variables and safe defaults
  (SQLite when `DATABASE_URL` is unset).
- `.env.example` documents every variable. Real `.env` files are git-ignored.
- `compose.yaml` overrides per-service URLs so containers reach `postgres:5432`
  and `redis:6379` on the Compose network, while host tooling uses the published
  `11450` / `11550` ports.

| Group | Variables |
|---|---|
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `PUBLIC_HOSTNAME` |
| Frontend wiring | `NEXT_PUBLIC_API_BASE_URL`, `API_INTERNAL_URL` |
| Data services | `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| LLM | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_REASONING`, `LLM_REASONING_STYLE`, `LLM_THINKING_BUDGET` |
| Embedding | `EMBEDDING_DEVICE` (`auto`/`cuda`/`cpu`), `EMBEDDING_BATCH_SIZE_CPU`, `EMBEDDING_BATCH_SIZE_GPU` |
| Sign-up gate | `SIGNUP_ACCESS_CODE`, `SIGNUP_CODE_MAX_FAILURES`, `SIGNUP_CODE_FAILURE_WINDOW_SECONDS`, `SIGNUP_CODE_LOCKOUT_SECONDS` |
| Discord (`.env-mylo`) | `DISCORD_API_KEY`, `ERROR_CHANNEL`, `ACTIVATION_CHANNEL`, `SUMMARY_CHANNEL` |
| Run analytics | `RUN_ANALYTICS_JSON_PATH`, `RUN_ANALYTICS_PDF_DIR`, `RUN_ANALYTICS_RETENTION_DAYS` |
| Reserved (unused) | `NEO4J_*`, `S3_*` |

`PUBLIC_HOSTNAME` backs every absolute URL Mycelium emits. Leaving it blank once
published `localhost` links into a lab's Discord channel; links that leave the
building now fall back to the public site rather than loopback.

The LLM client supports structured reasoning levels (`none`/`low`/`medium`/
`high`) sent either as `reasoning_effort` (`LLM_REASONING_STYLE=effort`) or as a
`chat_template_kwargs.enable_thinking` toggle, and reads back the server's
separated `reasoning_content`. It lazily imports the `openai` SDK and accepts an
injected transport, so tests run fully offline. The optional `llm-tunnel` Compose
service is an SSH forward to a remote LLM host, run inside the Compose network.

## The two recommendation processes

This split is load-bearing; changing one without the other corrupts feeds.

- **Daily append** — the nightly run scores only items created that day
  (`created_on=run_date`) and **appends** them. It never rewrites or deletes what
  Mylo already wrote.
- **On-demand replace** — refitting (`refit_*`, `run_refitting`, `manual_mylo.py`)
  scores the **whole corpus** and **replaces**. It runs at sign-up and after a
  profile or focus edit, and must never be scheduled into the daily chain.

Reads accumulate across runs (`views._accumulated_scores`,
`briefing._suggested_scores`), capped by `OPPORTUNITY_FEED_MAX`. Papers are the
exception: retrieval is scoped to the latest gather batch, so the Research Papers
page shows only the current day's search.

The **daily report** reads through a narrower gate than the feeds do
(`briefing.report_scores`): an item appears only if it first surfaced on the run
date and its relevance clears `REPORT_RELEVANCE_THRESHOLD`. A feed is browsable
and can carry the accumulated tail; a once-a-day report cannot, and a report that
relaxes its floor to fill the page is a report people stop opening. Both the
written briefing and the PDF read through that one function, so they can never
disagree about what the day held.

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

Measurement is deliberately outside `CONTAINER_STAGES`: a failure there means
users did not get their day, whereas a failure here only costs the summary its
detail. The run still announces itself either way.

## The ranking-stack seams

`apps/content/protocols.py` declares two structural protocols so the ranking
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
| Full stack, single origin | `docker compose up` (or `python run.py`) → `http://localhost:11050` |
| Backend + data services only | `docker compose up backend` |
| Host dev gateway | `npm run dev` |
| Backend management command | `uv run --project web/backend python web/backend/manage.py <cmd>` |
| Backend tests | `npm run test` (or `uv run --directory web/backend python -m pytest`) |
| GPU embedding | `docker compose -f compose.yaml -f compose.gpu.yaml up` |

Without `DATABASE_URL`, Django uses SQLite for quick checks — but pgvector tests
skip there, so anything touching vectors needs the Compose Postgres. Embedding
migrations depend on `core.0001_enable_pgvector`, so a fresh database provisions
the `vector` type before any table that uses it.

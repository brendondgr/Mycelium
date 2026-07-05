# Mycelium Architecture

**Status:** Foundation finalized (June 21, 2026) — repo structure, tech stack,
service boundaries, and data/secrets management are in place and running.
**See also:** [`docs/skills/repo-structure.md`](skills/repo-structure.md) (the
canonical layout standard this document applies), [`docs/purpose.md`](purpose.md),
[`docs/goals.md`](goals.md), and [`docs/api-contract.md`](api-contract.md).

Mycelium is a full-stack monorepo with **root-level orchestration**: editable
config (`compose.yaml`, `.env.example`, `package.json`) lives at the repository
root, and all implementation/install state lives under `web/`, separated by
service boundary. A new contributor should be able to identify root config, the
public site, the app, the Django API, the worker layer, infra, and docs without
guessing.

## Tech stack

| Layer | Technology | Location |
|---|---|---|
| Public marketing site | Astro, Tailwind, MDX, GSAP, React islands | `web/landing/` |
| Authenticated app | Next.js (App Router), React, Tailwind, shadcn/ui, TanStack Query/Table, Cytoscape.js | `web/app/` |
| Shared design tokens | Tailwind v4 theme tokens | `web/packages/config/` |
| Backend API & orchestration | Django, Django REST Framework | `web/backend/` |
| Background work | Celery | `web/backend/` (worker process) |
| Relational store | PostgreSQL 17 + **pgvector** | `postgres` service |
| Graph store | Neo4j 5 | `neo4j` service |
| Cache / broker / job state | Redis 8 | `redis` service |
| Object storage | S3-compatible (MinIO locally) | `minio` service |
| Edge gateway | Nginx (single-origin routing) | `web/infra/nginx/` |
| Python deps & commands | `uv` | `web/backend/` |
| Node workspace | npm workspaces | `web/` |

## Repository layout

```text
mycelium/
├── README.md, package.json, compose.yaml, .env.example   # root orchestration
├── docs/                          # purpose, goals, styles, architecture, api-contract, skills, plans
└── web/
    ├── landing/                   # Astro public site
    ├── app/                       # Next.js authenticated app
    ├── packages/config/           # shared theme tokens
    ├── backend/                   # Django API + Celery
    │   ├── config/                # settings, urls, celery, asgi/wsgi
    │   ├── apps/                   # Django apps (see boundaries below)
    │   ├── manage.py, pyproject.toml, uv.lock
    └── infra/nginx/               # gateway config
```

Root scripts delegate into `web/` so the site and Django server can be built and
run from the repository root (`npm run dev`, `npm run build`, `npm run test`).

## Service boundaries (separation of concerns)

Five distinct responsibilities, each with a clear owner. **The browser never
talks directly to Postgres, Neo4j, Redis, object storage, workers, or the vector
store** — only to the public site and, through the Next.js proxy, the Django API.

| Concern | Owner | Notes |
|---|---|---|
| Public content | `web/landing/` (Astro) | Marketing, pricing, explanation; no private data |
| Authenticated app behavior | `web/app/` (Next.js) | Session-gated UI; calls the API via a same-origin proxy |
| Backend orchestration | `web/backend/` (Django + DRF) | Auth, permissions, business logic, admin, audit, API contracts |
| Background work | Celery workers | Research scans, matching, extraction, graph updates, reports, digests |
| Data storage | Postgres / Neo4j / Redis / S3 | Durable records, relationships, queue/cache, blobs |

Single-origin routing through Nginx at `http://localhost:11050`:

| Path | Service |
|---|---|
| `/` and public pages | Astro landing |
| `/login`, `/signup`, `/app/*`, `/_next/*` | Next.js app |
| `/api/*`, `/admin/*` | Django |

## Backend app boundaries (as built)

The Django apps below realize the conceptual `auth` / `labs` / `scraper` /
`graph` / `reports` boundaries from the early plan. Identity and labs were
consolidated into `accounts`; the matching and billing layers became their own
apps; the planner, graph, and reporting apps are planned but not yet built.

| App | Responsibility |
|---|---|
| `core` | Shared infrastructure: health endpoint, the pgvector extension migration, the polymorphic exactly-one-FK helper, and the OpenAI-compatible LLM client (`apps/core/llm.py`) |
| `accounts` | Identity & organization: users, profiles, departments, labs, memberships, permission roles, academic titles, audit events, plus derived-membership services. Owns session auth (CSRF, login/logout/me) |
| `research` | Research context: projects (scoped to a user, lab, or department), project membership, and project visibility over the org hierarchy (members; lab heads; the department head above any involved lab) |
| `content` | Matching layer: deduplicated content items (papers, grants, fellowships) keyed by source + external id, and per-target relevance scores |
| `billing` | Subscriptions, per-seat billing, and tier-based entitlement resolution |
| `scraper` | Literature ingestion: ported OpenAlex/PubMed/Semantic Scholar source scrapers + registry, a publication-date scan window (today −2mo → +1mo), cross-source and against-store de-duplication, optional fastembed embedding, and upsert into `content.ContentItem`. Triggered by a Celery task or `scan_literature` management command — a placeholder wired to no schedule or member profile yet |
| _planned_ | `planner` (knowledge-graph query-planning agent — routing, liveness, self-evaluation; early logic currently in `accounts/intake/agent.py` and `core/llm.py`), `graph` (Neo4j orchestration), `reports` (digests, reports, alerts) |

## Data ownership

- **PostgreSQL + pgvector** — source of truth for users, labs, departments,
  memberships, permissions, profiles, projects, content items, relevance scores,
  subscriptions, seats, and audit logs. pgvector columns
  (`Profile.embedding`, `Project.embedding`, `ContentItem.embedding`) carry
  semantic vectors; the dimension is intentionally unlocked until a scoring model
  is chosen.
- **Neo4j** — structured relationships for people, projects, claims, evidence,
  papers, opportunities, and research goals (graph phase).
- **Redis** — Celery broker/result backend, caching, and short-lived job state.
- **Object storage (S3/MinIO)** — PDFs, uploads, generated reports, exports, and
  figures.

## Configuration, environment & secrets management

- Settings load through **django-environ**: `config/settings.py` reads a `.env`
  file at the repository root, then falls back to environment variables and safe
  local defaults (e.g. SQLite when `DATABASE_URL` is unset).
- **`.env.example`** at the root documents every required variable. The real
  `.env` is **git-ignored** (`.env`, `.env.*`, with `.env.example` explicitly
  exempted), so secrets are never committed.
- **`compose.yaml`** injects per-service URLs (Postgres, Redis, Neo4j, MinIO)
  for the Compose network and points the backend at the shared `.env.example`
  defaults.

| Group | Variables |
|---|---|
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Frontend wiring | `NEXT_PUBLIC_API_BASE_URL`, `API_INTERNAL_URL` |
| Data services | `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` |
| Object storage | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` |
| LLM | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_REASONING`, `LLM_REASONING_STYLE` |

The LLM group configures an OpenAI-compatible endpoint (a self-hosted **vLLM**
server is the reference target). `apps/core/llm.py` exposes a reusable
`LLMClient` that future features (planner drafting, relevance rationales, digest
and report drafting) route through. It supports structured **reasoning levels**
(`none`/`low`/`medium`/`high`) sent either as vLLM's `reasoning_effort`
(`LLM_REASONING_STYLE=effort`) or as a `chat_template_kwargs.enable_thinking`
toggle (`thinking`), and reads back the server's separated `reasoning_content`.
The server's reasoning parser and tool definitions are assumed to be configured
server-side. The client lazily imports the `openai` SDK and accepts an injected
transport, so importing it requires no SDK and tests run fully offline.

Secrets (`DJANGO_SECRET_KEY`, database credentials, `NEO4J_PASSWORD`, S3 keys)
come only from `.env` or the deployment environment. In production, `DEBUG` is
off, which turns on secure session and CSRF cookies; real secret values must
replace the `change-me` placeholders.

## Running locally

| Goal | Command |
|---|---|
| Full stack, single origin | `docker compose up` (or `python run.py`) → `http://localhost:11050` |
| Backend + data services only | `docker compose up backend` |
| Dev gateway (host processes) | `npm run dev` |
| Backend management command | `uv run --project web/backend python web/backend/manage.py <cmd>` |
| Backend tests | `npm run test` (or `uv run --directory web/backend python -m pytest`) |

Run migrations against Postgres by setting `DATABASE_URL`; without it, Django
uses the local SQLite database for quick checks. Embedding-column migrations
depend on `core.0001_enable_pgvector`, so a fresh database provisions the
`vector` type before any table that uses it.

## Foundation checklist (Month 1, Week 1)

- [x] Repo structure and tech stack finalized: Django backend, Postgres, Celery,
  and clear app boundaries (documented above).
- [x] Public content, authenticated app behavior, backend orchestration,
  background work, and data storage separated by service boundary.
- [x] Postgres configured with environment and secrets management
  (`django-environ` + git-ignored `.env`, documented in `.env.example`).
- [x] **Milestone:** Django project runs locally with Postgres connected
  (verified: `vendor=postgresql`, pgvector enabled).

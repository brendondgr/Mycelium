# Repository Structure Skill

Use this skill when defining, documenting, or enforcing the Mycelium repository
layout.

This skill describes the **rules**. For the actual file-level layout and a
task→path lookup, see [`../repo-map.md`](../repo-map.md) and keep it in sync when
top-level areas move. For the *why* behind the boundaries, see
[`../architecture.md`](../architecture.md).

## Core Rules

- Treat Mycelium as a full-stack monorepo with root-level orchestration.
- Keep project documentation in `docs/`.
- Keep web frontend, backend, and infrastructure implementation under `web/`,
  separated by service boundary.
- Keep editable orchestration config at the repository root: `compose.yaml`,
  `.env.example`, `package.json`, the systemd units, and the host runners.
- Build and run workflows should be designed from the repository root.
- Prefer a named module over a catch-all. Two catch-alls exist and are grandfathered:
  root `utils/` (per-stage manual runners and a vendored grants prototype) and
  `web/scripts/` (the dev gateway and the art sync). Do not add new ones.

## Actual layout

```text
mycelium/
├── CLAUDE.md, README.md, package.json, compose.yaml, compose.gpu.yaml, .env.example
├── run.py, manual_all.py, manual_mylo.py, pivot.py, create_admin.py, loadtest.py
├── mycelium*.service, mylo-daily.{service,timer}, mylo-bot.service
├── mylo/                      # host Discord bot + daily-run observability
├── utils/                     # per-stage manual runners, vendored grants prototype
├── models/                    # downloaded embedding model cache
├── docs/
│   ├── purpose.md, goals.md, styles.md
│   ├── architecture.md, api-contract.md, repo-map.md
│   ├── discord-integration.md, loadtest.md, research-audit.md, changelog.md
│   ├── skills/, chats/, Resources/
└── web/
    ├── package.json, package-lock.json, node_modules/
    ├── landing/               # Astro public site
    ├── app/                   # Next.js authenticated app
    ├── packages/config/       # shared Tailwind v4 theme tokens
    ├── art/, scripts/
    ├── backend/               # Django API + Celery (config/, apps/, manage.py, pyproject.toml)
    └── infra/nginx/
```

Root scripts call into `web/` so the site and the Django server can be built and
run from the repository root. Implementation files and install state belong under
`web/`; root config is for editing and orchestration.

## Service Boundaries

- `web/`: Node workspace root and install state.
- `web/landing/`: Astro public site — marketing, pricing, explanation. No private
  data and no framework JavaScript shipped.
- `web/app/`: Next.js App Router authenticated workspace.
- `web/packages/config/`: shared Tailwind v4 tokens used by both.
- `web/backend/`: Django API — auth, permissions, business logic, orchestration,
  admin, audit logs, API contracts. Django apps are `core`, `accounts`,
  `research`, `content`, `billing`, `integrations`, `adminpanel`, `scraper`.
- `web/backend` workers: Celery tasks for reminder ticks, the Discord outbox
  drain, project-profile recompute, and project seeding.
- Host runners: the nightly research pipeline (`manual_all.py`, fired by
  `mylo-daily.timer`) and the Discord gateway (`mylo/`) run on the host, not in
  Celery.
- `web/infra/`: Nginx gateway config.
- `docs/`: direction, architecture, API contract, repo map, operational guides,
  canonical skills, and the changelog.

## Data Ownership

- **Postgres + pgvector** is the source of truth for everything: users, labs,
  departments, memberships, permissions, profiles, projects, content items,
  relevance scores, saves, deadlines, reminders, notifications, subscriptions,
  seats, Discord identities, the outbox, and audit logs. Semantic retrieval uses
  pgvector columns on the same database; there is no separate vector store.
- **Redis** backs Celery plus named caches (signup lockouts, scan status, query
  embeddings).
- **Filesystem** holds Discord outbox attachments and the daily-run state file.
- **Neo4j and MinIO run in Compose but no code uses them.** Do not describe them
  as working infrastructure, and do not add a dependency on either without
  building the phase that needs it.

## Validation

- A new contributor should be able to identify root config, the public site, the
  app, the Django API, the worker layer, the host runners, infra files, and docs
  without guessing.
- The browser must never talk directly to Postgres, Redis, workers, or vector
  columns — only to the public site and, through the Next.js proxy, the API.
- When a top-level area moves, `docs/repo-map.md` changes in the same commit.

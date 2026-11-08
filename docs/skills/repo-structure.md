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
- Keep the repository root to what a reader expects there: the README, licence,
  contributing guide, `CLAUDE.md`, `Makefile`, `compose.yaml`, `package.json`,
  the Python project files, and the env templates. Everything that runs on the
  host goes in `ops/`; runtime state goes in the git-ignored `data/`.
- Research capabilities live in `tools/`, one self-contained folder per tool,
  loaded by discovery (see [`tools.md`](tools.md)). The platform — identity,
  organizations, profiles, projects, billing, integrations, the app shell —
  stays in `web/backend/apps/` and does not import tools.
- Build and run workflows should be designed from the repository root.
- Prefer a named module over a catch-all. `web/scripts/` (the dev gateway and the
  art sync) is grandfathered; do not add new catch-alls, and do not add scripts
  to the root.

## Actual layout

```text
mycelium/
├── CLAUDE.md, README.md, CONTRIBUTING.md, LICENSE, NOTICE
├── Makefile, package.json, compose.yaml, pyproject.toml, uv.lock, .env.example, .env-mylo.example
├── tools/                     # modular research tools, one folder each; _framework/ loads them
├── ops/                       # host-side: stack CLI, setup, nightly run, scrapers, systemd, loadtest, research tooling
├── mylo/                      # host Discord bot + daily-run observability
├── eval/                      # retrieval evaluation harness (own uv project)
├── docs/
│   ├── purpose.md, goals.md, styles.md
│   ├── architecture.md, api-contract.md, repo-map.md
│   ├── discord-integration.md, loadtest.md, research-audit.md, changelog.md
│   ├── skills/, plans/, research/
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
- `web/landing/`: Astro public site — marketing and explanation. No private
  data and no framework JavaScript shipped.
- `web/app/`: Next.js App Router authenticated workspace.
- `web/packages/config/`: shared Tailwind v4 tokens used by both.
- `web/backend/`: Django API — auth, permissions, business logic, orchestration,
  admin, audit logs, API contracts. Django apps are `core`, `accounts`,
  `research`, `content`, `billing`, `integrations`, `adminpanel`, `scraper`.
- `web/backend` workers: Celery tasks for reminder ticks, the Discord outbox
  drain, project-profile recompute, and project seeding.
- Host runners: the nightly research pipeline (`ops/nightly/manual_all.py`, fired by
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

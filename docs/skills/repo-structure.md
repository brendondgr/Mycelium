# Repository Structure Skill

Use this skill when defining, documenting, or enforcing the Mycelium repository
layout.

## Core Rules

- Treat Mycelium as a full-stack monorepo with root-level orchestration.
- Keep project documentation in `docs/`.
- Keep web frontend, backend, worker, and infrastructure implementation under
  `web/`, separated by service boundary.
- Keep editable orchestration config at the repository root when possible.
- Avoid catch-all folders such as `misc/`, `utils/`, or `helpers/`.
- Build and run workflows should be designed from the repository root.

## Planned Layout

Use this as the target structure when the app is scaffolded:

```text
mycelium/
|-- README.md
|-- package.json
|-- compose.yaml
|-- .env.example
|-- docs/
|   |-- skills/
|   |-- architecture.md
|   |-- api-contract.md
|   |-- security.md
|   `-- deployment.md
|-- web/
|   |-- package.json
|   |-- package-lock.json
|   |-- node_modules/
|   |-- landing/
|   |   |-- astro.config.mjs
|   |   |-- src/
|   |   `-- components.json
|   |-- app/
|   |   |-- next.config.ts
|   |   |-- src/
|   |   |-- public/
|   |   `-- components.json
|   |-- packages/
|   |   `-- config/
|   |       `-- src/theme.css
|   |-- backend/
|   |   |-- pyproject.toml
|   |   |-- uv.lock
|   |   |-- manage.py
|   |   |-- config/
|   |   `-- apps/
|   `-- infra/
|       |-- nginx/
|       `-- docker/
`-- scripts/
```

Root scripts should call into `web/` so the website and Django server can still
be built and run from the repository root. Implementation files and install
state belong under `web/`; root config is for editing and orchestration.

## Service Boundaries

- `web/`: Node workspace root and install state for public site, dynamic app,
  shared config, backend, and local infrastructure.
- `web/landing/`: Astro public site, Tailwind, MDX, GSAP, React islands, and
  public marketing/content routes.
- `web/app/`: Next.js App Router, React UI, Tailwind, shadcn/ui and Radix UI
  components, Framer Motion, Cytoscape.js, TanStack Query/Table, React Hook
  Form, graph views, reports, and authenticated app shell routes.
- `web/packages/config/`: shared Tailwind v4 color tokens and design-system
  configuration used by both Astro and Next.js.
- `web/backend/`: Django API, auth, labs, memberships, permissions, reports,
  documents, opportunities, jobs, audit logs, graph orchestration, and admin.
- `web/backend` workers: Celery tasks for literature scans, grant and
  fellowship matching, report generation, PDF processing, graph updates, and
  alerts.
- `web/infra/`: Nginx config, Dockerfiles, deployment support, and local infra.
- `docs/`: architecture, API contracts, security notes, deployment guidance,
  design system notes, and canonical skills.

## Data Ownership

- Postgres is the source of truth for users, labs, permissions, projects,
  reports, jobs, opportunities, notifications, audit logs, and billing records.
- pgvector or Qdrant handles semantic retrieval over papers, notes, reports,
  grant text, and document chunks.
- Neo4j stores structured relationships for lab profiles, people, projects,
  claims, evidence, papers, opportunities, and research goals.
- Object storage stores PDFs, uploaded files, generated reports, exports, and
  figures.
- Redis supports Celery, caching, job state, and short-lived coordination.

## Validation

- A new contributor should be able to identify root config, the web app, Django
  API, worker layer, infra files, docs, and root run command without guessing.
- The browser must never talk directly to Postgres, Neo4j, Redis, object
  storage, workers, or vector stores.

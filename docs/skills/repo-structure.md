# Repository Structure Skill

Use this skill when defining, documenting, or enforcing the Mycelium repository
layout.

## Core Rules

- Treat Mycelium as a full-stack monorepo with root-level orchestration.
- Keep project documentation in `docs/`.
- Keep future frontend, backend, worker, and infrastructure code separated by
  service boundary.
- Avoid catch-all folders such as `misc/`, `utils/`, or `helpers/`.
- Do not add dependency scaffolding unless the user explicitly asks for it.
- Build and run workflows should be designed from the repository root.

## Planned Layout

Use this as the target structure when the app is scaffolded:

```text
mycelium/
├── README.md
├── compose.yaml
├── .env.example
├── docs/
│   ├── skills/
│   ├── architecture.md
│   ├── api-contract.md
│   ├── security.md
│   └── deployment.md
├── frontend/
│   └── Next.js app
├── backend/
│   └── Django project and apps
├── infra/
│   ├── nginx/
│   └── docker/
└── scripts/
```

`compose.yaml` should eventually start the frontend, Django API, workers,
Redis, Postgres, Neo4j, object storage, and Nginx from the root. Until those
services exist, documentation may describe the plan without creating empty
runtime files.

## Service Boundaries

- `frontend/`: Next.js App Router, React UI, Tailwind, shadcn/ui and Radix UI
  components, charts, tables, graph views, reports, and app shell routes.
- `backend/`: Django API, auth, labs, memberships, permissions, reports,
  documents, opportunities, jobs, audit logs, graph orchestration, and admin.
- `backend` workers: Celery tasks for literature scans, grant and fellowship
  matching, report generation, PDF processing, graph updates, and alerts.
- `infra/`: Nginx config, Dockerfiles, Compose support, deployment notes, and
  environment examples.
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

- A new contributor should be able to identify the frontend, Django API, worker
  layer, infra files, docs, and root run command without guessing.
- The browser must never talk directly to Postgres, Neo4j, Redis, object
  storage, workers, or vector stores.

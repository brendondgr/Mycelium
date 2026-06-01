# Mycelium

Mycelium is a planned lab intelligence platform for research teams. It is meant
to help labs track research goals, monitor papers, match grants and fellowships,
build evidence-backed reports, and maintain a living knowledge graph of people,
projects, claims, opportunities, and lab priorities.

## Planned Stack

- Frontend: Next.js, React, Tailwind, shadcn/ui, Radix UI.
- Backend: Django and Django REST Framework for API, auth, permissions,
  orchestration, and admin.
- Workers: Celery and Redis for long-running research scans, opportunity
  matching, graph updates, report generation, and alerts.
- Data: Postgres with pgvector, Neo4j, Redis, and S3-compatible object storage.
- Deployment: Nginx in front of the frontend and API, with Docker Compose as
  the preferred initial orchestration path.

## Repository Status

This repository currently contains planning and skill documentation. Runtime
application code has not been scaffolded yet.

Future development should keep build and run workflows rooted at the repository
root. The preferred single-command local path is a root-level `compose.yaml`
that starts the Next.js frontend, Django API, workers, Nginx, and data services.

## Documentation

- `docs/chats/` contains source conversations that define the product,
  architecture, and visual direction.
- `docs/skills/` contains canonical agent guidance for planning, repository
  structure, website architecture, frontend UI, mobile behavior, and
  accessibility.

# Mycelium

Mycelium is a planned lab intelligence platform for research teams. It is meant
to help labs track research goals, monitor papers, match grants and fellowships,
build evidence-backed reports, and maintain a living knowledge graph of people,
projects, claims, opportunities, and lab priorities.

## Planned Stack

- Web app: Next.js, React, Tailwind, shadcn/ui, Radix UI, Django, Django REST
  Framework, Celery, and local web infrastructure under `web/`.
- Workers: Celery and Redis for long-running research scans, opportunity
  matching, graph updates, report generation, and alerts.
- Data: Postgres with pgvector, Neo4j, Redis, and S3-compatible object storage.
- Deployment: Nginx in front of the web app and API, with Docker Compose as
  the preferred initial orchestration path.

## Repository Status

This repository currently contains planning and skill documentation. Runtime
application code has not been scaffolded yet.

Future development should keep build and run workflows rooted at the repository
root. Root scripts delegate into `web/`, where the Next.js app, Django backend,
Nginx config, and Node install state live. Editable orchestration config such as
`compose.yaml` and `.env.example` stays at the repository root.

## Documentation

- `docs/chats/` contains source conversations that define the product,
  architecture, and visual direction.
- `docs/skills/` contains canonical agent guidance for planning, repository
  structure, website architecture, frontend UI, mobile behavior, and
  accessibility.

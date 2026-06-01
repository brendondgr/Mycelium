# Mycelium

Mycelium is a planned lab intelligence platform for research teams. It is meant
to help labs track research goals, monitor papers, match grants and fellowships,
build evidence-backed reports, and maintain a living knowledge graph of people,
projects, claims, opportunities, and lab priorities.

## Planned Stack

- Public landing site: Astro, Tailwind, MDX, GSAP, React islands, and shared
  Mycelium theme tokens under `web/landing/`.
- Dynamic lab app: Next.js, React, Tailwind, shadcn/ui, Radix UI, Framer
  Motion, Cytoscape.js, TanStack Query/Table, React Hook Form, and Zod under
  `web/app/`.
- Backend: Django, Django REST Framework, Celery, and local web infrastructure
  under `web/backend/` and `web/infra/`.
- Workers: Celery and Redis for long-running research scans, opportunity
  matching, graph updates, report generation, and alerts.
- Data: Postgres with pgvector, Neo4j, Redis, and S3-compatible object storage.
- Deployment: Nginx in front of the web app and API, with Docker Compose as
  the preferred initial orchestration path.

## Repository Status

This repository now has the basic full-stack scaffold in place. Root scripts
delegate into `web/`, where the Node workspace, Astro landing site, Next.js
app, Django backend, Nginx config, and Node install state live.

Editable orchestration config such as `compose.yaml`, `.env.example`, and the
root `package.json` stays at the repository root.

## Root Commands

- `npm run dev`: run Astro, Next.js, and Django together.
- `npm run dev:landing`: run only the Astro landing site on port 4321.
- `npm run dev:web`: run only the Next.js app on port 3000.
- `npm run dev:backend`: run only the Django server on port 8000.
- `npm run build`: build the shared config, Astro landing site, and Next.js app.
- `npm run lint`: check Astro, Next.js, and backend Python linting.
- `npm run test`: run backend tests.

## Documentation

- `docs/chats/` contains source conversations that define the product,
  architecture, and visual direction.
- `docs/skills/` contains canonical agent guidance for planning, repository
  structure, website architecture, frontend UI, mobile behavior, and
  accessibility.

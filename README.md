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

## Docker Backend Setup

The preferred local backend path is Docker Compose. The backend container uses
the `ghcr.io/astral-sh/uv:python3.13-bookworm` image, installs the Python
environment from `web/backend/`, and runs the Django development server on port
8000.

Prerequisites:

- Docker Desktop or another Docker Compose compatible runtime.
- The root `.env.example` file, which is already wired into the backend
  service for local defaults. `compose.yaml` overrides service URLs such as
  Postgres and Redis so containers talk over the Compose network.

Start the Django backend and its local service dependencies:

```sh
docker compose up backend
```

This starts Postgres, Redis, Neo4j, MinIO, and the Django backend. The backend
is available at:

- API health check: `http://localhost:8000/api/health/`
- Django admin route: `http://localhost:8000/admin/`

Stop the backend container stack:

```sh
docker compose down
```

To run the full local web stack through Docker Compose, including Nginx, Astro,
Next.js, and the backend:

```sh
docker compose up
```

Nginx is exposed at `http://localhost:9911`, with landing traffic routed to
Astro, app traffic routed to Next.js, and API/admin traffic routed to Django.

If the landing container cannot resolve `@mycelium/config/theme.css`, reset
container volumes so `node_modules` is recreated inside Docker:

```sh
docker compose down -v
docker compose up
```

## Root Commands

- `npm run dev`: run the dev gateway, Astro, Next.js, and Django together on
  **http://localhost:9911**.
- `npm run dev:landing`: run only the Astro landing site on port 4321.
- `npm run dev:web`: run only the Next.js app on port 3001 (bypasses gateway).
- `npm run dev:backend`: run only the Django server on port 8000.
- `npm run build`: build the shared config, Astro landing site, and Next.js app.
- `npm run lint`: check Astro, Next.js, and backend Python linting.
- `npm run test`: run backend tests.
- `npm run compose:up`: run the full Docker Compose stack.
- `npm run compose:down`: stop the Docker Compose stack.

## Documentation

- `docs/architecture.md` records the finalized repo structure, tech stack,
  service boundaries, data ownership, and environment/secrets management.
- `docs/purpose.md`, `docs/goals.md`, and `docs/styles.md` hold the canonical
  product direction; `docs/api-contract.md` holds committed API shapes.
- `docs/chats/` contains source conversations that define the product,
  architecture, and visual direction.
- `docs/skills/` contains canonical agent guidance for planning, repository
  structure, website architecture, frontend UI, mobile behavior, and
  accessibility.

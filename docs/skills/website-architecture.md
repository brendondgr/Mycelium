# Website Architecture Skill

Use this skill when planning, scaffolding, or restructuring Mycelium's public
site, authenticated lab app, Django API, or Dockerized deployment.

## Core Rules

- Use Next.js as the Node web server for the public site and authenticated
  lab workspace.
- Use Django as the backend API and orchestration layer.
- Route public app pages through Next.js and API/admin traffic through Django.
- Keep the Next.js app, Django backend, local infrastructure, and Node install
  state inside `web/`.
- Plan build, run, and deployment commands from the repository root.
- Root scripts should launch commands from the repository root while delegating
  runtime files to `web/`.
- Keep editable orchestration config at the root when the tool supports it.

## Runtime Shape

```text
Browser
  -> Nginx
  -> Next.js web app for /, /app, /login, dashboards, reports, and UI routes
  -> Django API for /api and /admin
  -> Postgres, Redis/Celery, Neo4j, vector search, and object storage
```

The Node server renders the web app. Django owns business logic, auth,
permissions, orchestration, data access, admin, and job creation.

## Required Planning Artifact

Before generating web code, define:

1. Application mode: public route, authenticated app route, or backend API.
2. User roles and auth boundaries.
3. Route map.
4. Data-flow map.
5. Frontend/backend boundary.
6. Repository layout.
7. Required docs.
8. Root-level build, run, and test commands.

## Route Expectations

Public routes should cover landing, product explanation, use cases, demo,
pricing or pilot information, blog or docs, contact, and login entry.

Authenticated routes should use a lab-aware shape such as:

```text
/app/[labSlug]/dashboard
/app/[labSlug]/research-feed
/app/[labSlug]/papers
/app/[labSlug]/projects
/app/[labSlug]/members
/app/[labSlug]/goals
/app/[labSlug]/grants
/app/[labSlug]/fellowships
/app/[labSlug]/reports
/app/[labSlug]/knowledge-graph
/app/[labSlug]/settings
```

Every authenticated route must state required role, lab membership checks, data
dependencies, API endpoints, loading states, empty states, and error states.

## Backend and API Contracts

- Django REST Framework is the default API layer unless a later decision
  replaces it.
- Django should own accounts, labs, memberships, object-level permissions,
  projects, reports, documents, opportunities, jobs, graph operations, audit
  logs, and admin workflows.
- Use Django or Celery for long-running research scans, grant matching,
  fellowship matching, extraction, report generation, and graph updates.
- Create `docs/api-contract.md` before the web app depends on explicit API
  payloads.

## Security Baseline

- Nginx is the public entrypoint for TLS, routing, rate limits, static/media
  handling, request limits, compression, and security headers.
- The web app must call Django only through approved API routes.
- Every lab-scoped endpoint must enforce authentication, lab membership,
  role permission, object-level permission, and audit logging where sensitive.
- Do not expose database, graph, queue, object storage, or worker services to
  the browser.

# Website Architecture Skill

Use this skill when planning, scaffolding, or restructuring Mycelium's public
site, authenticated lab app, Django API, or Dockerized deployment.

## Core Rules

- Astro serves the public landing/content site; it ships no framework JavaScript.
- Next.js (App Router) serves the authenticated lab workspace.
- Django + DRF is the backend API and orchestration layer.
- Nginx is the single public entrypoint: public traffic to Astro, app traffic to
  Next.js, `/api` and `/admin` to Django.
- Keep the Astro site, Next.js app, Django backend, infra config, and Node
  install state inside `web/`.
- Plan build, run, and deployment commands from the repository root; root scripts
  delegate runtime files to `web/`.
- Keep editable orchestration config at the root.

## Runtime shape

```text
Browser
  -> Nginx (:11050, single origin)
     -> Astro       /  and public pages
     -> Next.js     /login, /signup, /app/*, /_next/*
     -> Django      /api/*, /admin/*
                    -> Postgres + pgvector, Redis, Celery worker + beat
Host (outside the gateway)
  -> mylo-daily.timer  -> ops/nightly/manual_all.py   (the nightly research run)
  -> mylo-bot.service  -> python -m mylo.bot (the Discord gateway)
```

Astro owns the public content-heavy site. Next.js renders the dynamic workspace
and proxies `/api` same-origin. Django owns business logic, auth, permissions,
orchestration, data access, admin, and job creation.

## Required planning artifact

Before generating web code, define:

1. Application mode: public route, authenticated app route, or backend API.
2. User roles and auth boundaries.
3. Route map.
4. Data-flow map.
5. Frontend/backend boundary.
6. Repository layout.
7. Required docs.
8. Root-level build, run, and test commands.

## Route expectations

**Public** (`web/landing/src/pages/`) — four pages only: `index`, `product`,
`about`, `contact`. Adding a fifth needs a reason; `/solutions`, `/resources`,
`/research`, and `/demo` were removed as stubs that duplicated the homepage, and
`/pricing` was removed for the open-source release (it redirects to `/`). Every
"Sign up" CTA points at the real `/signup` (free with a sign-up code); the other
way in is self-hosting, linked to `/#self-host` and the source repository.

**Authenticated** (`web/app/src/app/app/`) — the workspace is **scope-switched,
not slug-routed**. Routes are flat under `(workspace)` and the active scope
(personal vs. a specific lab) lives in `portal-context.tsx`, persisted to
`localStorage`:

```text
/app/overview      /app/daily        /app/research-papers
/app/grants        /app/fellowships  /app/conferences
/app/saves         /app/reminders    /app/search
/app/projects      /app/projects/[projectId]
/app/labs          /app/members      /app/profile
/app/billing       /app/admin        /app/department/[id]
/app/onboarding    (first run only)
```

Do not introduce `/app/[labSlug]/…` routes. A lab page is the personal page with
`currentLab` set — that is what keeps the two from drifting apart.

Every authenticated route must state required role, lab membership checks, data
dependencies, API endpoints, and its loading, empty, populated, error, and
permission-denied states.

## Backend and API contracts

- Django REST Framework is the API layer.
- Django owns accounts, labs, memberships, object-level permissions, projects,
  content matching, reminders, billing, integrations, audit logs, and admin.
- Long-running work splits two ways: **Celery** for in-app background jobs
  (reminder ticks, outbox drain, profile recompute, project seeding) and the
  **host daily timer** for the nightly research pipeline. Do not move the daily
  pipeline into Celery Beat, and do not schedule a whole-corpus refit.
- Register every POST-able route **both** with and without a trailing slash — the
  Next `/api` proxy strips it and `APPEND_SLASH` cannot redirect an unsafe method.
- Update [`../api-contract.md`](../api-contract.md) in the same change as any
  payload the web app depends on.

## Security baseline

- Nginx is the public entrypoint for TLS, routing, rate limits, static handling,
  request limits, compression, and security headers.
- `PUBLIC_HOSTNAME` backs every absolute URL Mycelium emits. A blank value once
  published `localhost` links into a lab's Discord channel — anything leaving the
  building must fall back to the public site, never loopback.
- Session cookies are namespaced (`mycelium_sessionid` / `mycelium_csrftoken`) so
  a co-hosted localhost app cannot collide with them.
- Every lab-scoped endpoint must enforce authentication, lab membership, role
  permission, object-level permission, and audit logging where sensitive.
- Do not expose the database, queue, or worker services to the browser.

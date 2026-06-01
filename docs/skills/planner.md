# Planner Skill

Use this skill to produce clear implementation plans, migration plans, and
sequenced work breakdowns for Mycelium before coding.

## Core Rules

- Keep plans scoped to the Mycelium repository and its planned architecture.
- State assumptions explicitly when the docs or code do not decide something.
- Call out gaps, dependencies, security risks, and data ownership issues.
- Prefer concrete repository paths, service names, commands, and artifacts.
- Do not invent dependency setup or runtime files when the user asks for a
  documentation-only pass.

## Mycelium Defaults

- Frontend: Next.js App Router, React, Tailwind, shadcn/ui, Radix UI.
- Backend: Django, Django REST Framework, Django admin, object-level
  authorization, audit logging.
- Workers: Celery with Redis for research scans, opportunity matching, graph
  updates, report generation, alerts, and scheduled jobs.
- Data: Postgres as source of truth, pgvector or Qdrant for semantic retrieval,
  Neo4j for relationship graphs, object storage for files and exports.
- Deployment: Nginx in front of Next.js and Django, Docker Compose first, with
  root-level commands that delegate runtime files to `web/`.

## Output Shape

- Brief objective.
- Assumptions or open questions.
- Ordered implementation phases.
- Public interfaces, routes, schemas, or docs that will change.
- Validation and acceptance criteria.
- Explicit exclusions.

## Validation

- Confirm root-level run expectations are clear.
- Confirm web/backend ownership is not ambiguous.
- Confirm security-sensitive flows mention auth, lab membership, object-level
  permission, and logging.

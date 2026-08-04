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

- Frontend: Astro for the public site (no framework JS shipped), Next.js App
  Router + React + Tailwind v4 + Radix primitives for the authenticated app.
- Backend: Django, Django REST Framework, Django admin, object-level
  authorization, audit logging.
- Background work splits two ways, and a plan must say which it means: **Celery +
  Redis** for in-app jobs (reminder ticks, Discord outbox drain, profile
  recompute, project seeding) and the **host `mylo-daily.timer`** running
  `manual_all.py` for the nightly research pipeline.
- Data: Postgres is the source of truth and pgvector on the same database is the
  semantic index. There is no separate vector store, no graph store in use, and
  no object storage in use — Neo4j and MinIO run in Compose but nothing reads
  them. A plan that assumes any of those is planning new infrastructure.
- Deployment: Nginx in front of Astro, Next.js, and Django; Docker Compose first,
  with root-level commands that delegate runtime files to `web/`.

## Non-negotiables to check in every plan

- **Two recommendation processes.** The daily run scores only that day's new
  items and **appends**; whole-corpus **replace** passes (refitting) are
  on-demand only. A plan must never schedule a refit into the daily chain.
- **Personal / lab / project parity.** A lab or project feed is the personal feed
  with a different `MatchTarget`, through the same serializers. New feed behavior
  goes in the shared path, not a lab-only fork.
- **Entitlements.** Any new capability states its tier gate and reads it through
  `billing.entitlements`, the single read path.
- **Trailing slashes.** New POST routes register both forms.

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
- Name the validation command for each phase. Backend work runs through
  `uv run --project web/backend …`; anything touching vectors needs the Compose
  Postgres, since pgvector tests skip on SQLite.

## After the work ships

A plan is a working document, not a record. When the work lands, delete the plan
and write the outcome into `docs/changelog.md` plus whichever canonical doc the
change affects (`repo-map.md`, `api-contract.md`, `architecture.md`). Leaving a
stale plan behind is how the documentation stops being trustworthy.

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

- **Rank nightly, write up sparingly.** The daily run ranks the **whole corpus**
  for every target against its current profile, so a preference change is visible
  the next morning. The model is the scarce resource, not retrieval: carry-forward
  reuses verdicts already written, and only items entering a target's Top-25 are
  sent for a fresh write-up. A plan that saves cost by narrowing what gets *ranked*
  is optimising the wrong half. Refitting stays on-demand (sign-up / profile
  edits) because it re-sends every surfaced item to the model.
- **New means "entered the Top-25", never "arrived today".** Anything a plan calls
  new must be a change in what the reader is *shown*, not a fact about ingestion —
  see `apps/content/top_feed.py`.
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

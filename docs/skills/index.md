# Mycelium Skill Registry

Canonical skill definitions for this repository live in `docs/skills/`.

The folders under `.agents/skills/`, `.claude/skills/`, and `.cursor/rules/`
are tool entrypoints that should point back to these canonical docs. Keep the
behavioral guidance here so all agents share the same project assumptions.

## Canonical Skills

| Skill | Canonical Doc | Entry Folder |
| --- | --- | --- |
| Plan creation | [planner.md](./planner.md) | `plan/` |
| Repository structure | [repo-structure.md](./repo-structure.md) | `repo-structure/` |
| Website architecture | [website-architecture.md](./website-architecture.md) | `website-architecture/` |
| UI frontend | [ui-frontend.md](./ui-frontend.md) | `ui-frontend/` |
| Mobile friendly | [mobile-friendly.md](./mobile-friendly.md) | `mobile-friendly/` |
| ADA compliance | [ada-compliance.md](./ada-compliance.md) | `ada-compliance/` |

## Project Defaults

- Mycelium is a lab intelligence platform for research discovery, lab memory,
  grants, fellowships, reports, and knowledge graph backed evidence trails.
- The planned stack is Next.js, React, Tailwind, Django, Django REST Framework,
  Celery, Redis, Postgres with pgvector, Neo4j, object storage, Nginx, and
  Docker Compose.
- Future build and run commands should be launched from the repository root.
  Root scripts should delegate application files to `web/`, while editable
  orchestration config such as `compose.yaml` stays at the root.

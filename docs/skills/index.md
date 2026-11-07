# Mycelium Skill Registry

Canonical skill definitions for this repository live in `docs/skills/`.

The folders under `.agents/skills/`, `.claude/skills/`, and `.cursor/rules/` are
tool entrypoints and nothing more — each is a stub pointing back at the canonical
doc here. Keep the behavioral guidance in this directory so every agent shares
the same project assumptions, and when you add a skill, add all three
entrypoints.

## Canonical skills

| Skill | Canonical doc | Entry folder | Load it when |
|---|---|---|---|
| Global project guidance | [global.md](./global.md) | `global/` | Always, at the start of a session |
| Plan creation | [planner.md](./planner.md) | `plan/` | Sequencing work before coding |
| Repository structure | [repo-structure.md](./repo-structure.md) | `repo-structure/` | Moving or adding a top-level area |
| Website architecture | [website-architecture.md](./website-architecture.md) | `website-architecture/` | Routes, service boundaries, deployment shape |
| UI frontend | [ui-frontend.md](./ui-frontend.md) | `ui-frontend/` | Components, pages, visual system |
| Mobile friendly | [mobile-friendly.md](./mobile-friendly.md) | `mobile-friendly/` | Responsive behavior |
| ADA compliance | [ada-compliance.md](./ada-compliance.md) | `ada-compliance/` | WCAG 2.2 AA work |
| Discord bot (discord.py) | [discord-bot.md](./discord-bot.md) | `discord-bot/` | Anything touching `mylo/` or slash commands |

Most canonical skills are a single document. `discord-bot` additionally ships
verified reference implementations in [`discord-bot/`](./discord-bot/) — copy
from those rather than writing interaction plumbing from memory.

## Project defaults

- Mycelium is an open-source academic research assistant any lab can run on its
  own computers — profiles,
  literature monitoring, grants, fellowships, conferences, reports, and
  reminders. It is not a paper search tool or a chatbot.
- Canonical direction lives in [`../purpose.md`](../purpose.md),
  [`../styles.md`](../styles.md), and [`../goals.md`](../goals.md). Load `global`
  before starting work.
- The stack as built: Astro (public site, no framework JS), Next.js App Router
  (app), Django + DRF (API), Celery + Redis (in-app jobs), a host systemd timer
  (the nightly research run), Postgres + pgvector (everything durable, including
  semantic retrieval), Nginx, and Docker Compose. Neo4j and MinIO run in Compose
  but no code uses them.
- Run commands from the repository root; root scripts delegate into `web/`, while
  editable orchestration config stays at the root. Use `uv` for backend
  dependencies, commands, linting, and tests.

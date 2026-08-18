# Mycelium

## Research record

This is a research repository. All experiments, results, figures, and findings
live in [`docs/research/`](docs/research/). Nothing that will appear in a paper
is recorded anywhere else. Before running an experiment, read
[`docs/research/AGENT_INSTRUCTIONS.md`](docs/research/AGENT_INSTRUCTIONS.md).

---

Mycelium is a lab intelligence platform for research teams. It builds a living
profile of a lab and its members, ingests literature and funding sources every
day, scores what it finds against that profile, and delivers the result as an
in-app feed, a written daily report, and a Discord digest.

What is running today:

- **Personal and lab workspaces** — session auth, labs, departments, memberships,
  roles, projects (with team collaboration, collections, and shared reading
  lists), and an invite-only sign-up gate.
- **Interest profiles** — author import (OpenAlex / Semantic Scholar / Google
  Scholar / ORCID) plus optional résumé parsing, LLM synthesis into themed
  interest clusters, and an editing surface for people, labs, and projects.
- **Four recommendation feeds** — research papers, grants, fellowships, and
  conferences, each scored for a user, a lab, or a project, each with a percent
  match and a written reason.
- **Daily report** — a sectioned written briefing per user and per lab, served
  in-app, DM'd as a PDF, and posted to a lab's Discord channel.
- **Deadline reminders** — saved items, addressable deadlines, and Discord-
  delivered reminders with lead times, snoozing, and a manage page.
- **Unified search** over the whole corpus, fusing full-text, vector, and fuzzy
  channels.
- **Billing & entitlements** — tiered plans with per-seat billing for labs and
  departments, enforced in the API, the daily pipelines, and the frontend.
- **Discord integration** — identity linking, guild activation, slash commands, a
  durable outbox, and drift detection.
- **Platform admin** — a staff-only roster with subscription and quota writes.

## Stack

| Layer | Technology | Location |
|---|---|---|
| Public marketing site | Astro 6, Tailwind v4, MDX (zero framework JS shipped) | `web/landing/` |
| Authenticated app | Next.js 16 (App Router), React 19, Tailwind v4, Radix UI, TanStack Query/Table | `web/app/` |
| Shared design tokens | Tailwind v4 theme | `web/packages/config/` |
| Backend API | Django 5 + Django REST Framework | `web/backend/` |
| Background work | Celery + Celery Beat | `web/backend/` (`worker`, `beat` services) |
| Relational store | PostgreSQL 17 + pgvector | `postgres` service |
| Cache / broker | Redis 8 | `redis` service |
| Embeddings | fastembed / ONNX Runtime, CPU or CUDA | `web/backend/apps/scraper/embedding.py` |
| LLM | any OpenAI-compatible endpoint (vLLM is the reference target) | `web/backend/apps/core/llm.py` |
| Edge gateway | Nginx, single origin | `web/infra/nginx/` |
| Python deps & commands | `uv` | `web/backend/` |
| Node workspace | npm workspaces | `web/` |

Neo4j and MinIO run in `compose.yaml` and have settings entries, but no
application code reads them yet — the graph and object-storage phases are not
built. `cytoscape` is likewise declared in `web/app` but unused.

## Running locally

The whole stack is Docker Compose:

```bash
docker compose up
```

Nginx serves everything on a single origin at **http://localhost:11050** —
landing at `/`, the app at `/app/*`, `/login`, `/signup`, and Django at `/api/*`
and `/admin/*`. `python run.py` wraps the same thing (`up`, `down`, `restart`,
`logs`, `status`, `--build`).

Host-published ports follow `11050 + 100·n`: landing `11150`, app `11250`,
Django `11350`, Postgres `11450`, Redis `11550`, Neo4j `11650`/`11750`, MinIO
`11850`/`11950`. Only the gateway is needed for normal use; the rest exist for
host tooling.

Root commands:

| Command | What it does |
|---|---|
| `npm run dev` | Dev gateway + Astro + Next.js + Django on http://localhost:11050 |
| `npm run dev:landing` | Astro only, port 4321 |
| `npm run dev:web` | Next.js only, port 3001 (bypasses the gateway) |
| `npm run dev:backend` | Django only, port 8000 |
| `npm run build` | Build shared config, landing, and app |
| `npm run lint` | Astro check, Next.js eslint, backend ruff |
| `npm run test` | Backend pytest |
| `npm run compose:up` / `compose:down` | Full Compose stack |

## Running the stack

`scripts/mycelium` is the one entry point for the whole environment — it drives
the systemd units when they are installed and Docker Compose when they are not.

| Command | What it does |
|---|---|
| `mycelium restart` | The full cycle: stop, wipe the frontend build caches, start, wait for the API, apply migrations, restart Mylo, report endpoint health |
| `mycelium start` / `stop` | Same steps, one direction only |
| `mycelium build` | Rebuild images, then the full start cycle |
| `mycelium migrate` | Apply migrations against an already-running stack |
| `mycelium status` | Container state, Mylo state, live endpoint health |
| `mycelium logs` | Follow combined Compose logs |
| `mycelium install-service` | Install and enable the host systemd units (needs `sudo`) |

A restart is a full environment reset, not just a container bounce. Node modules
and art assets are re-synced by the `web-deps` service on every start; the Next
and Astro caches are deleted while the stack is down, so the dev servers never
serve modules compiled against an older schema. Migrations are applied only
after the API answers — the backend container migrates itself before serving, so
waiting for health is what keeps two `migrate` processes off the same DDL lock.
Mylo restarts last, so the bot never attaches to a database it is newer than.

Pass `--keep-cache` to skip the cache wipe (a faster restart when nothing
frontend-facing changed) or `--no-migrate` to bring the stack up without
touching the database.

Backend management commands run through `uv`:

```bash
uv run --project web/backend python web/backend/manage.py <command>
```

Configuration comes from a git-ignored root `.env` (every variable is documented
in `.env.example`) plus `.env-mylo` for the Discord bot's token and channel ids.
Both are read by `web/backend/config/settings.py`.

## The daily run

The nightly pipeline is a **host** systemd timer, not Celery Beat.
`mylo-daily.timer` fires `manual_all.py` at 07:00; it scrapes the opportunity
sources on the host, then runs each backend stage in order inside the container:

`run_daily_suggestions` → `run_daily_opportunities --no-prune` →
`run_reminder_tick` → `prune_opportunities` → `generate_daily_briefing` →
`send_daily_discord_reports` → `send_lab_digests`

The daily run only ever **appends** the day's new items. Re-scoring the whole
corpus is the on-demand refit pass (`manual_mylo.py` / `run_refitting`), run at
sign-up and after profile edits — never on a schedule.

Other host units: `mycelium.service` (stack up at boot), `mycelium-update.service`
(image pull + rolling restart), `mylo-bot.service` (the persistent Discord
gateway, `python -m mylo.bot`).

## Documentation

Start at [`docs/`](docs/README.md). The short version:

- **Direction** — [`docs/purpose.md`](docs/purpose.md),
  [`docs/goals.md`](docs/goals.md), [`docs/styles.md`](docs/styles.md).
- **Navigation** — [`docs/repo-map.md`](docs/repo-map.md) maps a task to a path.
  Read it before searching the tree.
- **Reference** — [`docs/architecture.md`](docs/architecture.md),
  [`docs/api-contract.md`](docs/api-contract.md),
  [`docs/discord-integration.md`](docs/discord-integration.md),
  [`docs/loadtest.md`](docs/loadtest.md),
  [`docs/research-audit.md`](docs/research-audit.md).
- **Agent guidance** — [`CLAUDE.md`](CLAUDE.md) and
  [`docs/skills/`](docs/skills/index.md).
- **History** — [`docs/changelog.md`](docs/changelog.md).

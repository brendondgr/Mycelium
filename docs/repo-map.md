# Mycelium Repository Map

**Purpose:** locate code without searching. Read this first when you need to find
where a feature lives, then open the specific file. This map replaces blind
`find` / `grep` / `ls` sweeps — those burn tokens; this file is one read.

**Keep it accurate:** when you add, move, or rename a top-level area (a Django app,
an app route group, a `lib/` module, an infra file), update the matching row here
in the same change. This map is only useful while it is trusted.

**See also (don't duplicate):** [`architecture.md`](architecture.md) for the *why*
(service boundaries, data ownership, tech stack), [`api-contract.md`](api-contract.md)
for committed HTTP shapes, [`skills/repo-structure.md`](skills/repo-structure.md)
for the layout standard.

---

## Where do I look for…? (task → location)

| I need to work on… | Start here |
|---|---|
| A public marketing/landing page | `web/landing/src/pages/*.astro` (+ `.mdx`) |
| An authenticated app page/route | `web/app/src/app/app/**` (Next.js App Router) |
| A React component used in the portal | `web/app/src/components/portal/` |
| Onboarding / profile-edit flow (UI) | `web/app/src/components/onboarding/` + route `app/app/onboarding/` |
| Lab overview / onboarding / switch (UI) | `web/app/src/components/portal/sections/{lab-overview-section,lab-onboarding,labs-section}.tsx`, `portal/{lab-switcher,portal-sidebar}.tsx` |
| Onboarding / profile intake (backend) | `web/backend/apps/accounts/intake/` (`lab.py` = lab profile synthesis) |
| Lab watch + lab profile synthesis (backend) | `web/backend/apps/accounts/` — `LabWatchPreference` model, `LabWatchView` + `LabIntakeSynthesizeView` (`views.py`, `urls.py`) |
| Login / signup / logout (UI) | `web/app/src/components/auth/` + routes `app/src/app/{login,signup}` |
| Session auth, CSRF, `/me` (backend) | `web/backend/apps/accounts/` (`views.py`, `urls.py`) |
| Users, labs, departments, memberships, roles | `web/backend/apps/accounts/models.py` |
| Projects & project visibility | `web/backend/apps/research/` (list/create + lab-projects browse + self-join/leave/add-member in `views.py`) |
| Daily research suggestions pipeline | `web/backend/apps/content/` (`pipeline.py`, `interests_query.py`, `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, `suggest.py`) |
| Daily grants/conferences matching (1am) | `web/backend/apps/content/` (`opportunities.py`, `opportunity_llm.py`, `pinning.py`) + task/command `run_daily_opportunities`; root `manual_opportunities.py` |
| Pivot-RP (ProQuest) grants/conferences ingest | `web/backend/apps/scraper/pivot/` (`importer.py`, `ingest.py`, `records.py`, `grants.py`, `conferences.py`, `scrape.py`, `login.py`); commands `pivot_login` / `scrape_pivot` / `ingest_pivot`; root runner `pivot.py` (login → scrape → import → distribute) |
| Opportunities / conferences / deadlines / saves API | `web/backend/apps/content/{views,serializers,urls}.py` |
| Papers/grants/fellowships/conferences items, scores, saves | `web/backend/apps/content/models.py` (`ContentItem`, `RelevanceScore`, `SavedOpportunity`) |
| Literature scraping / source adapters | `web/backend/apps/scraper/` (`sources/`, `ingest.py`, `window.py`) |
| The LLM client | `web/backend/apps/core/llm.py` |
| Billing / subscriptions / entitlements | `web/backend/apps/billing/` |
| Knowledge-graph query planner (agent) | not a standalone app yet — logic in `accounts/intake/agent.py` + `core/llm.py` |
| Django settings / URLs / Celery / ASGI | `web/backend/config/` |
| Frontend → API calls & data hooks | `web/app/src/lib/` and `web/app/src/lib/portal/` |
| Shared design tokens / theme | `web/packages/config/src/theme.css` |
| Nginx / gateway routing | `web/infra/nginx/` |
| Root run/build commands | `run.py`, `manual_search.py` (papers) / `manual_opportunities.py` (grants/conferences matching), `pivot.py` (`all` = one in-process scrape→dedup→recommend; also `login`/`scrape`/`import`/`distribute`), `package.json`, `compose.yaml` |
| Env vars / secrets contract | `.env.example` (documented in `architecture.md`) |

---

## Frontend — `web/app/` (Next.js App Router)

```text
web/app/src/
├── app/                         # routes (App Router)
│   ├── layout.tsx, page.tsx     # root shell + entry
│   ├── login/, signup/          # auth pages
│   └── app/                     # authenticated area
│       ├── onboarding/          # first-run + profile-edit flow
│       ├── [labSlug]/dashboard/ # per-lab dashboard
│       └── (workspace)/         # portal shell + pages:
│           #   overview, daily, research-papers, deadlines,
│           #   members, opportunities, projects/[projectId],
│           #   profile, reports  (layout.tsx = workspace chrome)
├── components/
│   ├── auth/                    # login/signup/logout forms + brand panel
│   ├── onboarding/              # onboarding flow, stages, synthesis progress
│   ├── portal/                  # header, sidebar, nav, search, shell (+ primitives/, sections/)
│   ├── brand/, layout/, ui/     # brand marks, layout wrappers, shadcn/ui primitives
└── lib/
    ├── api-url.ts, auth-*.ts    # API base URL + auth client/server/types
    ├── utils.ts
    └── portal/                  # client, hooks, routes, types, theme, completeness
```

`web/landing/` is the separate **Astro** public site (`src/pages/`, `src/components/`,
`src/data/`, `src/layouts/`). `web/art/` holds source art assets (logo, Mylo, frontpage).

## Backend — `web/backend/apps/` (Django + DRF + Celery)

Each app has the usual `models.py` / `views.py` / `serializers.py` / `urls.py` /
`admin.py`; only the notable extras are listed. Conceptual responsibilities and
data ownership live in [`architecture.md`](architecture.md#backend-app-boundaries-as-built).

| App | Notable files beyond the CRUD basics |
|---|---|
| `core` | `llm.py` (LLM client), `db.py` (exactly-one-FK helper), `people.py`, `views.py` (health) |
| `accounts` | `intake/` (profile import→synthesize, see below), `services.py`, `provisioning.py`, `permissions.py`, `aggregates.py`, `embedding.py`, `interests.py`, `signals.py`, `management/commands/` |
| `research` | projects scoped to user/lab/department + visibility rules |
| `content` | papers **and** grants/conferences. Daily papers: `pipeline.py`, `interests_query.py`, `retrieval.py` (pgvector), `lexical.py` (BM25), `fusion.py`, `ranking.py`, `suggest.py`. Opportunities: `opportunities.py` (per-user grants/conf match, reuses `fuse_interests_pool`), `opportunity_llm.py` (scope/eligibility/topic scoring), `pinning.py` (New + 1-week pin). `embeddings.py`, `guards.py`, `runlog.py`, `tasks.py` (Celery — `run_daily_suggestions` 6am, `run_daily_opportunities` 1am), `management/commands/` |
| `billing` | `entitlements.py`, `services.py` (subscriptions, per-seat, tiers) |
| `scraper` | `sources/` (openalex, pubmed, semanticscholar + `base`, `registry`, `dedup`, `record`), `ingest.py`, `window.py` (scan window), `embedding.py`, `tasks.py`, `management/commands/scan_literature`. `pivot/` = vendored Pivot-RP (ProQuest) grants/conferences: `importer.py`/`ingest.py` (upsert+prune into `ContentItem`), `records.py`, `normalize.py`, `deadlines.py`, `status.py`, Playwright `grants.py`/`conferences.py`/`login.py`/`scrape.py` (optional `pivot` extra); command `ingest_pivot` |

> The `planner`, `graph`, and `reports` apps are **planned, not yet built** (see
> `architecture.md`). The planner's early logic currently lives in
> `accounts/intake/agent.py` and `core/llm.py`.

`accounts/intake/` (profile onboarding pipeline):
`retrievers/` (openalex, scholar, semantic) → `normalizers/` → `extract.py` /
`resolve.py` / `merge.py` / `aggregate.py` → `synthesize.py` / `statement.py` →
`drafts.py`, `importer.py`, `resume.py`, `agent.py`, `errors.py`.

`web/backend/config/`: `settings.py`, `urls.py`, `celery.py`, `asgi.py`, `wsgi.py`,
`debug_middleware.py`. `web/backend/templates/` + `static/` serve Django admin/health.

## Other top-level areas

| Path | What |
|---|---|
| `docs/` | canonical direction (`purpose`, `styles`, `goals`), `architecture.md`, `api-contract.md`, `changelog.md`, `skills/`, `plans/`, `chats/`, `Resources/` |
| `compose.yaml`, `run.py`, `package.json` | root orchestration; `run.py` / `npm run *` delegate into `web/` |
| `scripts/`, `mycelium*.service` | management scripts + systemd units |
| `web/infra/nginx/` | single-origin gateway routing |

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
| Onboarding / profile-edit flow (UI) | `web/app/src/components/onboarding/` + route `app/app/onboarding/`. Steps in order: About → Import → Review → **Watch** ("What should Mylo keep an eye on?") → **Fellowship eligibility** (only shown when the Fellowships signal is kept on; citizenship/stage/fields/restrictions saved in `interests.eligibility`). The watch step toggles papers/grants/fellowships/**conferences** individually. First-run finish shows the live match window (`onboarding-match.tsx`) instead of jumping to the overview |
| Post-onboarding live match (backend) | `web/backend/apps/content/onboarding_match.py` (`onboarding_match_area` reuses `refit_user` for one area over the existing corpus) + `OnboardingMatchView` → `POST /api/content/onboarding/match/` |
| Lab overview / onboarding / switch (UI) | `web/app/src/components/portal/sections/{lab-overview-section,lab-onboarding,labs-section}.tsx`, `portal/{lab-switcher,portal-sidebar}.tsx` |
| Grants page + filter rail / fellowships / conferences (UI) | `web/app/src/components/portal/sections/{opportunities-section,grant-filters,fellowships-section,fellowship-filters,conferences-section}.tsx`. Grants (`/app/grants`) has a client-side filter rail (`grant-filters.tsx`, pure `filterAndSortGrants` — collapsible sponsor/topic facets, AND-inclusive topic match; list caps to top 25 until "Show all"); Fellowships (`/app/fellowships`) mirrors it (`fellowship-filters.tsx`, pure `filterAndSortFellowships` — tier/deadline/field/stage/award-type/citizenship facets) over the eligibility-matched feed |
| Onboarding / profile intake (backend) | `web/backend/apps/accounts/intake/` (`lab.py` = lab profile synthesis) |
| Lab watch + lab profile synthesis (backend) | `web/backend/apps/accounts/` — `LabWatchPreference` model, `LabWatchView` + `LabIntakeSynthesizeView` (`views.py`, `urls.py`) |
| Login / signup / logout (UI) | `web/app/src/components/auth/` + routes `app/src/app/{login,signup}` |
| Session auth, CSRF, `/me` (backend) | `web/backend/apps/accounts/` (`views.py`, `urls.py`) |
| Users, labs, departments, memberships, roles | `web/backend/apps/accounts/models.py` |
| Projects & project visibility | `web/backend/apps/research/` (list/create + lab-projects browse + self-join/leave/add-member + **project detail/edit** `ProjectDetailView` (GET any viewer, PATCH name/`focus` for owner or lab manager) in `views.py`; a project's research **focus** = areas/keywords/statement/watch_topics stored in `goals`, normalized by `content.targets.project_interests`) |
| Matcher scoring **target** (user/lab/project) | `web/backend/apps/content/targets.py` — `MatchTarget` + `target_for_user`/`_lab`/`_project`; the paper (`pipeline.recommend_for_target`) and grant/conference (`opportunities.match_opportunities_for_target`) engines score for any target and persist under the right `RelevanceScore.target_*`. Convenience: `recommend_for_lab`/`_project`, `run_opportunities_for_lab`/`_project`, `refitting.refit_lab`/`refit_project`. The daily batches fan out to labs + lab projects over the shared corpus. Fellowships stay user-only |
| Lab / project recommendation feeds (read) | `content/views.py` `LabRecommendationsView` (`GET /api/labs/<slug>/recommendations/`) + `ProjectRecommendationsView` (`GET /api/projects/<id>/recommendations/`) — combined papers+grants+conferences + counts + `interested` (lab members who personally matched an item = the who's-interested layer). UI: real counts on the lab overview, recommended papers + Mylo picks on project detail (`lab-overview-section.tsx`, `project-detail-section.tsx`) |
| Daily research suggestions pipeline | `web/backend/apps/content/` (`pipeline.py`, `interests_query.py`, `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, `suggest.py`) |
| Daily grants/conferences/fellowships matching (1am) | `web/backend/apps/content/` (`opportunities.py`, `fellowships.py` (eligibility rule engine — the hard gate), `opportunity_llm.py` (LLM report for grants/conferences **and** fellowships, incl. `generate_fellowship_suggestions` which overlays a tailored report on the eligibility-gated list), `pinning.py`) + task/command `run_daily_opportunities`; runner `utils/manual/manual_opportunities.py` |
| On-demand refitting (re-personalize all 4 areas, no scan/ingest) | `web/backend/apps/content/refitting.py` (reuses `recommend_for_user` + `run_opportunities_for_user`) + command `run_refitting` (`--max N\|all`); runner `utils/manual/manual_refitting.py` |
| Pivot-RP (ProQuest) grants/conferences/fellowships ingest | `web/backend/apps/scraper/pivot/` (`importer.py`, `ingest.py`, `records.py`, `grants.py`, `conferences.py`, `fellowships/` (Illinois Fellowship Finder — no Pivot login), `scrape.py` (three areas in parallel), `login.py`); commands `pivot_login` / `scrape_pivot` / `ingest_pivot`; root runner `pivot.py` (login → scrape → import → distribute) |
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
| Root run/build commands | `run.py`, `manual_all.py` (root orchestrator — runs search → opportunities → refit for all users, one after another), `pivot.py` (`all` = one in-process scrape→dedup→recommend; also `login`/`scrape`/`import`/`distribute`), `package.json`, `compose.yaml` |
| Manual pipeline runners (per stage) | `utils/manual/` — `_runner.py` (shared Compose discovery + backend-up guard + `run_manage`), `manual_search.py` (papers), `manual_opportunities.py` (grants/conferences/fellowships matching), `manual_refitting.py` (re-personalize existing top results — LLM re-score, no scan/ingest); the root `manual_all.py` chains all three |
| Env vars / secrets contract | `.env.example` (documented in `architecture.md`) |
| Onboarding load / stress test | root `loadtest.py` (async HTTP client, `uv run`) + `loadtest_interests.py` (static interest catalog); cleanup command `accounts/management/commands/loadtest_purge.py`; guide `docs/loadtest.md` |

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
│           #   overview, daily, research-papers, opportunities (= Grants),
│           #   fellowships, conferences, deadlines, members,
│           #   projects/[projectId], profile, reports
│           #   (layout.tsx = workspace chrome)
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
| `content` | papers **and** grants/conferences/fellowships. Daily papers: `pipeline.py`, `interests_query.py`, `retrieval.py` (pgvector), `lexical.py` (BM25), `fusion.py`, `ranking.py`, `suggest.py`. `targets.py` (`MatchTarget` — score for a user/lab/project, see the task→location table). Opportunities: `opportunities.py` (grants/conf/fellowship match for any target), `fellowships.py` (deterministic eligibility rule engine — the hard eligibility gate + fit ranker, no LLM), `opportunity_llm.py` (LLM report + percent-match for grants, conferences, **and** fellowships; fellowships gate on the rule engine first, then `generate_fellowship_suggestions` overlays a tailored report, falling back to the rule summary when the model is down), `pinning.py` (New + 1-week pin). `refitting.py` (on-demand re-personalize all four areas over existing top results — LLM re-score, no scan/ingest; command `run_refitting`). `embeddings.py`, `guards.py`, `runlog.py`, `tasks.py` (Celery — `run_daily_suggestions` 6am, `run_daily_opportunities` 1am covers all three areas), `management/commands/` |
| `billing` | `entitlements.py`, `services.py` (subscriptions, per-seat, tiers) |
| `scraper` | `sources/` (openalex, pubmed, semanticscholar + `base`, `registry`, `dedup`, `record`), `ingest.py`, `window.py` (scan window), `embedding.py`, `tasks.py`, `management/commands/scan_literature`. `pivot/` = vendored Pivot-RP (ProQuest) grants/conferences + Illinois fellowships: `importer.py`/`ingest.py` (upsert+prune into `ContentItem`, keyed per source), `records.py`, `normalize.py`, `deadlines.py`, `status.py`, Playwright `grants.py`/`conferences.py`/`fellowships/`/`login.py`/`scrape.py` (parallel areas; optional `pivot` extra); command `ingest_pivot` |

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

# Projects: plan-based limits, guided creation, clusters, fellowships & the short-list digest

**Status:** in progress
**Worktree:** `.claude/worktrees/project-tiers` (branch `worktree-project-tiers`)
**Owner:** this session

## Objective

Make projects a fully functional, plan-gated feature:

1. Gate project creation with **per-scope, per-plan caps** (count active/non-archived projects only).
2. Add **archiving** — an archived project stops getting new recommendations (dropped from the daily fan-out and refit) but keeps its already-stored recommendations visible. Never delete.
3. Add a **guided creation flow** (name → one plain-language "what is this project about?" step → Mylo composes clusters), reusing the existing `composeClusters` machinery.
4. Give projects the **v2 interest-cluster contract** so their scoring runs cluster-scoped like user/lab profiles.
5. Add **project fellowships** matched by the project's *interests* (no personal-eligibility gate) — eligibility is a person attribute a project doesn't have.
6. Add a per-project **short-list digest**: top **10 papers / 5 grants / 5 fellowships / 5 conferences** (conferences excluding passed deadlines), each with the existing LLM "why recommended" explanation. The scoring pipeline is unchanged (BM25 → embedding → RRF → rerank → LLM top-10); the digest is selection + display over stored scores.
7. Add **recommendation customization** per project (which of papers/grants/fellowships/conferences to run) and surface archive/limit state in the customization UI.

## Decisions (from the user, 2026-07-20)

- **Caps count active (non-archived) projects.** Archiving frees a slot.
  - Personal projects, by the user's effective tier: **Free = 2, Spore = 5** (Lab/Canopy individuals default to 5 — assumption, see Open Questions).
  - **Lab-scoped** projects: **10** (requires the lab to hold `TEAM_WORKSPACE`; a Free/unsubscribed lab = 0).
  - **Department-scoped** projects: **30** (Canopy).
- **Spore individuals get personal projects with daily recommendations.** Free keeps projects (cap 2) but, being an on-demand tier, gets seeding-on-create + on-demand only, never the daily push (Free is already excluded from `select_users`).
- **Within a lab, only owners/admins/PIs create projects** (`user_can_edit_lab_profile` = lead PI or owner/admin).
- **Archived = no new search results; the oldest stored results stay visible. Never delete a project.**
- **Project fellowships rank on project interests** (research-fit), not qualifications. Keep the existing *user* fellowship behavior (hard eligibility gate, then interests-primary ranking) — that already matches intent; verify, don't rewrite.
- **Short list = the same pipeline** (BM25 → embedding → RRF → rerank → top 10) then the LLM writes the Mylo "why recommended" for the final items.

## Assumptions / open questions

- **A1.** Lab/Canopy *individual* personal-project cap = 5 (same as Spore). Only Free differs (2). Revisit if the user wants paid individuals to get more personal projects.
- **A2.** "Archived still in search results" = the archived project's **already-stored** `RelevanceScore` rows remain readable on the project page. It is *not* a new project-search surface. (Global unified search is a content-corpus search and has no project scoping; unchanged.)
- **A3.** Over-cap on downgrade: never delete. The first `cap` non-archived projects (oldest-first by `created_at`) stay active/scored; the rest render read-only with an "over your plan limit — archive or upgrade" banner and are excluded from scoring. Mirrors `effective_watch_topics`.
- **A4.** Seeding on create runs in the background (Celery), with a per-project "researching…" flag reusing the `scan_status` pattern. The request returns immediately.

## Ordered implementation phases

Each phase ends with a concrete validation command and is committed separately.

### Phase 0 — Worktree & plan (this doc)
- Create worktree, write & commit this plan.
- **Validate:** `git -C <worktree> status` clean except this doc.

### Phase 1 — Data model: archive + entitlement caps (backend)
- `apps/research/models.py`: add `Project.is_archived` (bool, default False, indexed) + `archived_at` (nullable). Add a `Project.objects.active()` queryset helper (non-archived).
- Migration `research/000X_project_archive`.
- `apps/billing/entitlements.py`: add
  - `PERSONAL_PROJECT_CAPS = {Free:2, Spore:5, Lab:5, Canopy:5}`, `LAB_PROJECT_CAP = 10`, `DEPARTMENT_PROJECT_CAP = 30`.
  - `personal_project_cap(user)`, `lab_project_cap(lab)` (0 unless `TEAM_WORKSPACE`), `department_project_cap(dept)` (0 unless Canopy/`DEPARTMENT_ROUTING`).
  - `project_cap_for_scope(scope, owner)` dispatcher + `active_project_count(scope, owner)` + `within_project_cap(...)`.
- **Validate:** `uv run --project web/backend pytest apps/billing apps/research -q` (new unit tests for caps + migration applies).

### Phase 2 — Creation gating, department scope, archive endpoints (backend)
- `apps/research/serializers.py`: `ProjectCreateSerializer` accepts `focus` ({areas, keywords, statement, watch_topics, clusters}) and `department` slug alongside `lab`; validates `clusters` via the shared `validate_interests` contract; writes `goals.interests` (+ `clusters`) + `goals.watch_topics` on create (reuse the update serializer's focus-merge).
- `apps/research/views.py` `perform_create`:
  - Resolve scope (personal / lab / department) with permission checks: lab → `user_can_edit_lab_profile`; department → `user_can_edit_dept_profile`; personal → the caller.
  - **Atomic cap check**: `transaction.atomic()` + `select_for_update` on the scope-owner row, count active projects, raise `PermissionDenied`/`ValidationError` with `{cap, active, scope}` when at limit.
  - Kick off background seeding (Phase 6).
- New endpoints: `POST /api/projects/<pk>/archive/` and `/unarchive/` (permission = `_user_can_edit`; unarchive re-checks cap). Audit `project.archive` / `project.unarchive`.
- `ProjectSerializer`: expose `is_archived`, `is_over_cap` (computed in the list view context), and `focus.clusters`.
- **Validate:** `uv run --project web/backend pytest apps/research -q` (create caps per scope, permission matrix, archive/unarchive, over-cap read).

### Phase 3 — Projects get v2 clusters (backend)
- `apps/content/targets.py` `project_interests()`: read + emit `goals.interests.clusters` when present; keep the flat fallback for legacy projects.
- `target_for_project()`: when clusters are present, keep the declared cluster partition authoritative — merge team signal into **keywords** only (don't create orphan areas outside clusters); still prefer `stored_vector`.
- `ProjectUpdateSerializer` (already merges focus): persist `focus.clusters` into `goals.interests.clusters`, validated as a partition of `focus.areas`.
- **Validate:** `uv run --project web/backend pytest apps/content -q -k "cluster or target or project"` — a 2-cluster project dispatches to `fuse_clusters_pool`; a clusterless one stays flat.

### Phase 4 — Project fellowships by interest (backend)
- `apps/content/fellowships.py`: add an interest-only path — either `match_fellowships(..., skip_eligibility=True)` or `match_fellowships_by_interest(...)` — that skips the eligibility + tier gates, requires `embed_by_id`, uses embedding cosine as the primary signal (`rule_fit = 1.0`), drops `closed`/`suspended`, and omits tier/gates_failed/reasons from output.
- `apps/content/opportunities.py`: generalize `_persist_fellowships` to take `persist_kwargs` (not hardcoded `target_user`); add a project fellowship branch to `run_opportunities_for_target` (so projects get grants + conferences + **fellowships**). Build the fellowship embedding pool for the project target.
- `apps/content/opportunity_llm.py`: add a project-fellowship system prompt ("judge on fit to the project's research interests/goals, not personal eligibility").
- `apps/content/refitting.py`: `refit_project` includes fellowships (extend `TARGET_AREAS` for the project path, or a project-specific area tuple). `refit_lab` stays grants/conferences only.
- **Verify (no change):** user fellowship ranking already gates on eligibility then ranks by interest (0.65 embed / 0.35 rule) — add/confirm a test asserting interests dominate ranking among eligible fellowships.
- **Validate:** `uv run --project web/backend pytest apps/content -q -k "fellowship"` (project fellowships persist under `target_project`, skip eligibility, rank by embedding; user path unchanged).

### Phase 5 — Read payload: project fellowships + short-list selection (backend)
- `apps/content/views.py` `ProjectRecommendationsView` / `_recommendations_payload`: for a **project** target, include `fellowships` from `target_project` `RelevanceScore`s via the normal `FellowshipSerializer` (tier/gates empty), plus fellowship `counts` + `window_counts`.
- Add a **digest** shape (either a `?digest=1` param or a dedicated `GET /api/projects/<pk>/digest/`): top 10 papers, top 5 grants, top 5 fellowships, top 5 conferences with a future/None deadline (exclude passed), each carrying the existing `match_percent`/`headline`/`reason`. Selection only — no new scoring.
- **Validate:** `uv run --project web/backend pytest apps/content -q -k "recommend or digest or project"`.

### Phase 6 — Seeding on create + daily fan-out (backend)
- `apps/content/tasks.py`:
  - New `seed_project_recommendations(project_id)` task → `refit_project` (papers/grants/conferences/fellowships) + clear the project scan flag.
  - `select_targets`: exclude archived projects; add **personal projects of `select_users`** (Spore+), **department projects of active departments**, and cap each scope to its `project_cap` (oldest-first) so over-cap projects aren't scored.
- `apps/content/scan_status.py`: add project-scoped inflight flag helpers (mirror the user paper-scan flag).
- `perform_create` enqueues `seed_project_recommendations`.
- **Validate:** `uv run --project web/backend pytest apps/content -q -k "select_targets or seed"`; manual `uv run --project web/backend python manage.py shell` dry check that archived/over-cap projects are excluded.

### Phase 7 — Recommendation customization per project (backend)
- Store `goals.watch_categories` (subset of papers/grants/fellowships/conferences; default all). `select_targets`/seed/refit honor it (skip unselected areas).
- `ProjectUpdateSerializer` accepts `watch_categories`; `ProjectSerializer` exposes it.
- **Validate:** `uv run --project web/backend pytest apps/research apps/content -q -k "categor"`.

### Phase 8 — Frontend: guided creation wizard (web/app)
- `lib/portal/`: extend `createProject` mutation to send `{name, lab?|department?, focus}`; add `archiveProject`/`unarchiveProject`, `useProjectDigest`; extend `Project`/`ProjectFocus`/`TargetRecommendations` types (`is_archived`, `is_over_cap`, `clusters`, project `fellowships`, `watch_categories`).
- `projects-list-section.tsx`: enable "New project" → open the wizard; disable when at cap with an explanatory tooltip; show archived section + over-cap banner.
- New `components/portal/projects/create-project-wizard.tsx`: Step 1 name + scope picker (only scopes with permission & headroom); Step 2 free-text purpose → `composeClusters` → `ClusterOrganizer` review. Submit → create → show "Mylo is researching…".
- **Validate:** `npm run -w web/app typecheck`, `npm run -w web/app lint`, `npm run -w web/app build` (preview is pinned to the main checkout, so verify via tsc/eslint/build per the worktree-preview note; no browser check in the worktree).

### Phase 9 — Frontend: short-list digest + settings (web/app)
- `project-detail-section.tsx`: add a "Mylo's picks for this project" digest block (10/5/5/5) using `useProjectDigest`; render fellowships with the existing `FellowshipRow`; render each item's `reason`/`match_percent`.
- Project settings surface: category toggles (`watch_categories`), archive/unarchive control, over-cap/limit messaging.
- **Validate:** typecheck + lint + build as Phase 8.

### Phase 10 — Docs, changelog, repo-map
- Update `docs/repo-map.md` rows (Projects, entitlements, fellowships user→project note), `docs/changelog.md` (schema per global.md), and `docs/architecture.md` if the entitlement surface changes.
- **Validate:** markdown/link check; final full backend suite `uv run --project web/backend pytest -q` (pgvector tests need the compose Postgres `DATABASE_URL` at :11450; they skip on SQLite).

### Phase 11 — Merge & clean up
- Merge local `main` into the branch, resolve conflicts, re-run backend suite + frontend build.
- Commit everything; **do not push**.
- Merge branch → `main` (local), delete the worktree (`git worktree remove`), confirm no stray worktree remains.

## Public interfaces that change

- **Routes:** `POST /api/projects/` (now takes `focus`, `department`); `POST /api/projects/<pk>/archive/`, `/unarchive/`; project recommendations payload gains project `fellowships`; new project digest (`?digest=1` or `/digest/`).
- **Schema:** `Project.is_archived`, `archived_at`; `goals.interests.clusters`, `goals.watch_categories`.
- **Entitlements:** new project-cap resolvers in `billing/entitlements.py`.
- **Serializers:** `ProjectSerializer` (+`is_archived`,`is_over_cap`,`focus.clusters`,`watch_categories`), `ProjectCreateSerializer`/`ProjectUpdateSerializer` (focus+clusters+categories+department).

## Security / permissions checklist

- Project create: personal = caller; lab = `user_can_edit_lab_profile`; department = `user_can_edit_dept_profile`. Caps enforced atomically.
- Archive/unarchive: `_user_can_edit` (personal owner or lab/dept manager).
- Fellowship interest-matching for a project never reads a person's eligibility/citizenship — no cross-user PII leak into a shared project surface.
- Audit events for create/archive/unarchive (extends existing project audit).
- Daily fan-out only scores active, in-cap, entitled targets (Free personal projects never get a scheduled push).

## Explicit exclusions

- No global project-search surface (A2).
- No department-level recommendation *digest* UI this pass (department projects still score + read via the project surface).
- No Neo4j/graph work; no billing/checkout changes (caps read the existing subscription state).
- Lab fellowships keep their member-eligibility-union model (unchanged); only *project* fellowships use the interest path.

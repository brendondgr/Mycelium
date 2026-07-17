# Lab Workspace Overhaul — Implementation Plan

**Correlation ID:** `20260716-lab-workspace-overhaul`
**Status:** done — all phases implemented, verified (601 backend tests on pgvector, frontend tsc + eslint, live browser end-to-end), and merged to `main`. Merged concurrent `main` work (lab-scoped saves/reminders) in with a merge migration.

## Objective

Make the lab workspace a first-class, visually distinct experience that is clearly
different from the personal workspace, and reorganize both overviews so the daily
report is the centerpiece instead of an isolated page.

Concretely:

1. Replace the header dropdown "switch context" with a **left/right toggle**:
   left = Personal, right = Lab. With multiple labs, the Lab side opens a
   dropdown to pick which lab, then activates it.
2. **Remove the "Labs" group from the left sidebar.** Lab creation/browse moves
   into the switcher's lab dropdown.
3. Give the lab workspace a **branded sidebar**: a lab identity block at the top
   (uploaded **logo** centered, or the lab name in text when there's no logo),
   with the `Workspace` / `Research` nav groups beneath it. Every nav
   destination (Overview, Daily, Research Papers, Grants, Fellowships,
   Conferences) is **lab-scoped** when a lab is active.
4. **Permissions:** in a lab, the `Profile` nav becomes the **lab
   configuration/information editor** and is visible/editable only to PIs
   (`is_lead`), owners, and admins. `Saves` stays visible to everyone. Only
   PIs/admins can create **lab reminders**.
5. **Fold the daily report into the Overview** (both personal and lab):
   - Left column: the written daily report (personal Mylo Report; lab = a new
     LLM-authored lab briefing).
   - Right column (lab): tight lab statistics — purpose / what Mylo watches on
     top, then **articles / grants / conferences / fellowships found
     today / last week / last month / last year**, plus members & projects.
   - Remove the standalone `Daily` page from the sidebar (both contexts).
6. Add the ability to **upload a lab logo**.

## Decisions (from the user)

- The daily-report-into-overview change applies to **both** personal and lab
  workspaces.
- The lab daily report is a **full LLM-authored lab briefing** (new backend
  generation stage on the daily run), mirroring the personal Mylo Report.

## Assumptions

- Lab logo is stored as a Django `ImageField` (adds `Pillow`) and served
  **through the existing `/api/` gateway** via a dedicated DRF view, so no nginx
  `/media/` location or new static plumbing is required.
- Time-window "found today/week/month/year" counts derive from
  `RelevanceScore.created_at` (real DB column, set when Mylo scores/append the
  row for the target), scoped by `target_lab`.
- The lab briefing reuses the existing multi-agent writer in
  `apps/content/briefing_agents.py`; only the gather + persistence + read
  surface + daily-run fan-out are new.
- Working on a **feature branch in the main checkout** (not a separate
  worktree) so the Preview MCP can browser-verify the frontend (the preview is
  pinned to the main checkout). Branch merges back to `main` at the end.

## Key files (verified during discovery)

**Backend**
- `web/backend/apps/accounts/models.py` — `Lab` (L48–77), `LabMembership`
  (roles + `is_lead`), `LabProfile` (OneToOne).
- `web/backend/apps/accounts/permissions.py` — `user_can_manage_lab`
  (owner/admin), `user_can_edit_lab_profile` (is_lead OR owner/admin),
  `user_has_lab_access`.
- `web/backend/apps/accounts/{views,serializers,urls}.py` — `LabProfileView`,
  `LabProfileSerializer`, lab routes under `/api/auth/labs/<slug>/…`.
- `web/backend/apps/content/views.py` — `LabRecommendationsView` +
  `_recommendations_payload` (counts = `len()`, no time windows yet).
- `web/backend/apps/content/briefing.py` + `briefing_agents.py` +
  `DailyBriefing` model (OneToOne per user) + `DailyBriefingView` +
  `generate_daily_briefing` command (stage 4 of `manual_all.py`).
- `web/backend/apps/content/reminders.py` `create_subscription` (L146, gate at
  L177 uses `user_can_manage_lab`).
- `web/backend/config/{settings.py,urls.py}` — `MEDIA_*` declared, unserved.

**Frontend**
- `web/app/src/components/portal/portal-header.tsx`, `lab-switcher.tsx`,
  `portal-sidebar.tsx`, `lab-nav-item.tsx`, `portal-mobile-nav.tsx`,
  `portal-context.tsx`, `workspace-shell.tsx`.
- `web/app/src/components/portal/sections/{overview-section,lab-overview-section,daily-reports-section,labs-section,lab-onboarding,profile-section}.tsx`.
- `web/app/src/lib/portal/{routes,types,hooks,client,mutations}.ts`.
- Route pages under `web/app/src/app/app/(workspace)/*/page.tsx`.

## Phases

### Phase 1 — Backend: lab logo (upload + serve)
- Add `Lab.logo = ImageField(upload_to="lab-logos/", null=True, blank=True)`;
  add `Pillow` to backend deps; migration.
- `LabLogoView` at `/api/auth/labs/<slug>/logo/`:
  - `GET` streams the file (`FileResponse`, correct content-type,
    `X-Content-Type-Options: nosniff`); 404 when unset. Any lab member.
  - `POST`/`PUT` multipart upload (validate ≤2MB, PNG/JPG/WebP); gated by
    `user_can_edit_lab_profile`.
  - `DELETE` clears it; same gate.
- Expose `logo_url` (the API URL, or null) on the `MyLab` serializer (switcher
  payload) and on `LabProfileSerializer`.
- Docs: `api-contract.md`.
- **Validate:** `uv run --project web/backend python manage.py makemigrations
  --check` then migrate; unit test upload/serve/permission via `manage.py test`
  or a scripted request; confirm a non-manager gets 403.

### Phase 2 — Backend: lab time-window stats
- Add `window_counts` to `_recommendations_payload`: per area
  (`papers/grants/conferences/fellowships`) → `{today, week, month, year}`
  computed from `RelevanceScore.created_at` filtered by `target_lab` (+ member
  fan-out for fellowships).
- Keep the existing `counts` for back-compat.
- Docs: `api-contract.md`, `types.ts` mirror in Phase 6.
- **Validate:** scripted call against a seeded lab; counts monotonic
  (today ≤ week ≤ month ≤ year).

### Phase 3 — Backend: lab LLM briefing
- Generalize `DailyBriefing` to target a lab: add nullable `lab` FK, enforce
  user-XOR-lab (via `core.db` exactly-one helper); migration.
- `generate_briefing_for_lab(lab)` in `briefing.py` reusing `briefing_agents.py`
  and `targets.target_for_lab` + lab suggested scores.
- `LabDailyBriefingView` → `GET /api/labs/<slug>/daily-briefing/` (member read).
- Wire into `generate_daily_briefing` command to **also** fan out to labs;
  **audit `manual_all.py`** (stage 4) — briefing is a per-run replace summary,
  consistent with append-only recommendation semantics; no reorder of stages.
- Docs: `api-contract.md`, `repo-map.md`, `AGENTS`/global daily-run note.
- **Validate:** run `generate_daily_briefing` for a seeded entitled lab; confirm
  a `DailyBriefing` row with `lab` set and non-empty body (or deterministic
  fallback); confirm the endpoint returns it.

### Phase 4 — Backend: reminder gate includes PIs
- Change the lab-reminder gate in `create_subscription` from
  `user_can_manage_lab` to `user_can_edit_lab_profile` (adds `is_lead` PIs) so
  "admins/PIs can create reminders" holds. Mirror in `reminders_views.py`.
- **Validate:** a PI (is_lead, non-admin) can create a lab reminder; a plain
  member still cannot.

### Phase 5 — Frontend data layer
- `types.ts`: add `logo_url` to `MyLab`; `WindowCounts` + `window_counts` on
  `TargetRecommendations`; reuse `DailyBriefing` type for the lab endpoint.
- `client.ts`: `fetchLabDailyBriefing(slug)`.
- `mutations.ts`: `uploadLabLogo(slug, file)` / `deleteLabLogo(slug)` (multipart,
  mirrors `synthesizeLabProfile`).
- `hooks.ts`: `useLabDailyBriefing(slug)`, `useUploadLabLogo`/`useDeleteLabLogo`;
  ensure `useLabRecommendations` surfaces `window_counts`.

### Phase 6 — Frontend: workspace switcher toggle
- Rewrite `lab-switcher.tsx` as a segmented **Personal | Lab** toggle. Lab side:
  single lab → activate directly; multiple labs → dropdown to choose; includes a
  "Create / browse labs" affordance (opens the labs management surface).
- Update `portal-context.tsx` if needed (scope already tracked); verify
  switching actually rescopes (the reported "not working" bug — confirm the
  section dispatch keys off `currentLab`).

### Phase 7 — Frontend: sidebar overhaul
- `portal-sidebar.tsx`:
  - Lab identity block at top: logo (centered) or lab name; caption line.
  - **Remove the `Labs` group** (delete `lab-nav-item` usage there).
  - Lab context: `Profile` (= lab config) shown only to PIs/owners/admins;
    remove standalone `Daily`; keep Overview, Research Papers, Grants,
    Fellowships, Conferences, Saves.
  - Personal context: keep current items minus the standalone `Daily`
    (folded into overview).
- `portal-mobile-nav.tsx`: mirror the same context-aware items.
- Move lab create/browse into the switcher (Phase 6) so the sidebar no longer
  needs the Labs group.

### Phase 8 — Frontend: lab overview redesign
- `lab-overview-section.tsx`: two-column layout — left = the lab LLM briefing
  (reuse the `MarkdownProse` + Mylo Report treatment); right = a tight stack:
  purpose / what Mylo watches, then a compact **time-window stats** block
  (articles/grants/conferences/fellowships × today/week/month/year), then
  members & projects. Remove oversized cards; make it dense and "tight fitting".

### Phase 9 — Frontend: personal overview redesign
- `overview-section.tsx`: fold the personal Mylo Report into the overview (left),
  keep papers/deadlines/quick-nav on the right; drop the standalone Daily page
  from nav. Tighten spacing.

### Phase 10 — Frontend: lab config editor as "Profile"
- In lab context, the `Profile` route renders a lab configuration editor
  (reuse/extend `LabEditor` + lab profile fields) **plus a logo upload control**.
  Gate the route to PIs/owners/admins (non-managers get a permission-denied
  state and no nav item).
- Fold the old `labs-section` management (invite, Discord, members, projects,
  create lab) into reachable places: create/browse via the switcher; management
  via the lab Profile/config editor.

### Phase 11 — Frontend: lab-scoped feed pages
- `research-papers`, `grants`, `fellowships`, `conferences` sections dispatch on
  `currentLab`: when a lab is active, render the lab feed from
  `useLabRecommendations` (fellowships use the `LabFellowship` union shape);
  else the personal feed. Reminder "Remind me" affordance gated to PIs/admins in
  lab context.

### Phase 12 — Docs, verification, commit, merge
- Update `repo-map.md`, `api-contract.md`, `styles.md`/`purpose.md` if direction
  shifted, `changelog.md` (schema per global skill).
- Full verification: backend tests; `web` typecheck + lint + build; Preview MCP
  browser pass across both workspaces, all states (loading/empty/populated/
  error/permission-denied/mobile/dark).
- Commit per phase (concise, no AI attribution). Merge the feature branch to
  `main`, resolving conflicts.

## Acceptance criteria

- Switching Personal ⇄ Lab is a visible left/right toggle and actually rescopes.
- The sidebar has no `Labs` group; the lab sidebar shows the logo (or name) and
  lab-scoped destinations.
- A member without PI/owner/admin sees no lab `Profile`/config and cannot create
  lab reminders; a PI can.
- The lab overview shows the LLM briefing (left) and tight time-window stats
  (right); the standalone Daily page is gone from nav.
- A lab logo can be uploaded, is shown in the sidebar, and persists.
- Personal overview shows its Mylo Report inline.
- `web` build + lint + typecheck pass; backend migrations apply; docs updated.

## Exclusions

- No change to the scraping/ingest or opportunity-matching pipelines beyond the
  new briefing gather + read surfaces.
- No department-workspace variant (labs only).
- No nginx/static infra change (logo served through `/api/`).

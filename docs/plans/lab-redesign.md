# Lab Redesign — Implementation Plan

**Correlation ID:** 20260705-lab-redesign
**Branch/worktree:** `worktree-lab-redesign` (branched from origin/main, local main merged in)

## Objective

Make the lab experience a real, first-class workspace: the workspace switcher
drives lab context, the sidebar reflects the active lab, the lab front page
becomes an engaging overview modeled on the personal overview, and a lab has its
own LLM-assisted onboarding (purpose, focus, tags, and what Milo watches).

## Product decisions (confirmed with user)

1. **Overview metrics** — papers recommended / grants found / conferences
   matching are **placeholder / honest "coming soon"** cards for now. No content
   pipeline work in this change (grants + conferences have no pipeline yet).
2. **Lab onboarding input** — a mix: the user **manually fills** purpose/focus/tags
   **and may optionally provide source material** (example papers, other people's
   profiles/portfolios, pasted text). That material is fed to the LLM for
   synthesis. Manual is always possible; LLM synthesis is an assist.
3. **Lab watch storage** — new **`LabWatchPreference`** model (parallel to the
   per-user `WatchPreference`).

## Current state (from repo mapping)

- Backend already has `LabProfile` (statement, areas, funding_needs,
  strategic_needs, interests, embeddings), auto-created on lab creation, with a
  permission-gated `GET/PATCH /auth/labs/<slug>/profile/` endpoint and serializer.
- Account provisioning already handles `personal`/`lab`/`department` correctly.
- `WatchPreference` is **per-user only**.
- Frontend `labScope` (React state, default `ALL_LABS_SLUG` = "__all__") is the
  lab-context driver; navigation section is URL-derived. The switcher shows
  "All labs"; the sidebar shows a generic "Lab" label; `labs-section.tsx` lists
  lab cards then a management detail; `overview-section.tsx` is the personal
  overview to model against.

## Mapping requests → changes

| Req | Change |
|---|---|
| 1. Sidebar shows lab name | `portal-sidebar.tsx`: "Lab" group label → active lab name when scoped |
| 2. Clean lab top nav | `labs-section.tsx`: drop the lab-card list when a lab is active; show that lab's management directly |
| 3. Lab overview front page | new `lab-overview-section.tsx`; `OverviewSection` branches on `currentLab` |
| 4. Lab onboarding | new `lab-onboarding.tsx` (multi-step, LLM-assisted) rendered inline in the lab overview when the lab has no profile yet; backend synth endpoint |
| 5. Account types / context switch | rename `ALL_LABS_SLUG` → `PERSONAL_SLUG` ("Personal workspace" default); switcher = Personal + one item per lab; switching a lab reflects in sidebar + overview |

## Phase A — Backend: lab watch + lab intake synthesis

1. `accounts/models.py`: add `LabWatchPreference` (OneToOne `Lab`, `topics`,
   `categories`, `cadence` reusing `WatchCadence`). Auto-create in
   `signals.py` on `Lab` post_save (get_or_create alongside `LabProfile`).
2. Migration `0013_labwatchpreference` (+ data step to backfill existing labs).
3. `serializers.py`: `LabWatchPreferenceSerializer`. `views.py`:
   `LabWatchView` (RetrieveUpdate) at `auth/labs/<slug>/watch/` — read = lab
   member, write = `user_can_edit_lab_profile`. `urls.py`: wire it.
4. `intake/lab.py`: `synthesize_lab_interests(description, areas_hint,
   source_text, *, complete=None)` reusing `extract.extract_profile_fields` +
   `statement.draft_statement`; deterministic fallback when no LLM. Returns
   `{statement, areas, keywords}`.
5. `views.py`: `LabIntakeSynthesizeView` (POST) at
   `auth/labs/<slug>/intake/synthesize/`, permission = edit-profile. Returns
   `{statement, areas, keywords}`.
6. Confirm `LabProfileSerializer` can persist keywords (via `interests`); extend
   if needed so onboarding can save keywords.

**Validate:** `uv run --project web/backend python manage.py makemigrations
--check` then makemigrations + migrate; `manage.py check`; a focused test/shell
run of `synthesize_lab_interests` (fallback path) and the new endpoints; run
existing accounts tests.

## Phase B — Frontend: context switching, switcher, sidebar

7. `lib/portal/types.ts`: rename `ALL_LABS_SLUG` → `PERSONAL_SLUG`
   (value `"__personal__"`); update `hooks.ts`, `portal-context.tsx` references.
8. `portal-context.tsx`: default `labScope = PERSONAL_SLUG`; `scopeLabel` for
   personal = "your personal workspace".
9. `lab-switcher.tsx`: closed label = lab name or "Personal workspace"; dropdown
   = "Personal workspace" (primary) + one item per lab; drop the "All labs" item.
10. `portal-sidebar.tsx`: Lab group label = `currentLab?.name ?? "Lab"`.

**Validate:** lint + typecheck; run dev; DOM-read the switcher/sidebar reflect a
selected lab.

## Phase C — Frontend: lab overview front page + labs-section cleanup

11. new `sections/lab-overview-section.tsx`: greeting + date + "You're viewing
    {lab.name}"; three placeholder metric cards (papers/grants/conferences with
    honest "coming soon"); lab summary (statement/areas) + management
    quick-actions. If profile empty and user can manage → render onboarding.
12. `overview-section.tsx`: branch to `LabOverviewSection` when `currentLab`.
13. `labs-section.tsx`: when `currentLab`, show `LabDetail` directly (no card
    list). When personal scope, keep the browse list + Create lab.

**Validate:** lint + typecheck; run dev; DOM-read personal overview vs lab
overview; empty-profile → onboarding shows.

## Phase D — Frontend: lab onboarding flow

14. new `onboarding/lab-onboarding.tsx` (or under portal/sections): steps —
    (1) purpose + focus + tags, (2) optional source material, (3) what Milo
    watches, (4) review & save. "Synthesize with Mylo" calls the synth endpoint
    to prefill. Save → PATCH lab profile + save lab watch.
15. `lib/portal/`: client + hooks + mutations for lab watch (get/save) and lab
    intake synthesize; types for lab watch.

**Validate:** lint + typecheck; run dev; DOM-read the flow; synth prefill (LLM or
fallback); save persists (GET reflects it).

## Phase E — Docs, changelog, commit, merge

16. Update `docs/repo-map.md` (new lab endpoints/components) and
    `docs/changelog.md` (per global schema, correlation `20260705-lab-redesign`).
17. Commit per phase (human-authored, no AI attribution). Merge worktree → main,
    fixing conflicts; do not stage the user's unrelated uncommitted changes.

## Exclusions

- No grants/conferences ingestion or scoring pipeline (metrics are placeholders).
- No change to the daily content pipeline to run per-lab (paper metric stays a
  placeholder for now).
- No department onboarding parity (labs only).

## Acceptance criteria

- Switcher shows "Personal workspace" + labs (no "All labs"); selecting a lab
  updates sidebar label + renders the lab overview.
- Lab overview mirrors the personal overview (greeting/date/metrics) with honest
  placeholder metrics and lab-level management actions.
- A lab with no profile shows inline onboarding capturing tags, focus, purpose,
  and watch settings, with an optional LLM synthesis step; saving persists to
  `LabProfile` + `LabWatchPreference`.
- Backend migrations apply cleanly; `manage.py check` passes; frontend lints and
  type-checks; verified in a running dev server.

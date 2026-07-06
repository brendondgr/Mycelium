# Plan: Grant filters + Grants/Fellowships page split

## Objective

Give the Opportunities page a left-hand **filter rail** (between the main
workspace sidebar and the grants list) and move **Fellowships** onto its own
page/route/nav item so grants get the full width and the two opportunity types
stop getting confused.

## Assumptions / decisions

- **All filtering is client-side.** The grants API returns the entire latest run
  in one payload (`apps/content/views.py` `_latest_run_scores` → `GrantsView`,
  no pagination), so filters narrow already-fetched data in memory. **No backend
  changes.**
- **Fellowships is a frontend-only placeholder.** There is no fellowship feed,
  view, serializer, or matcher today — the old "Fellowships" column was a static
  "In progress" empty state. The split therefore adds no hook/endpoint.
- The grants nav item + heading are renamed **"Grants"** (route stays
  `/app/opportunities` to avoid churn). Fellowships gets `/app/fellowships`.
- Filter set (first pass): match strength, deadline window, deadline type,
  sponsor, matched topic, new-only, saved-only, match source, and sort.
  **Deferred:** funding-amount range (needs a numeric parser for the free-text
  `amount`).

## Interfaces / files changed

- `web/app/src/lib/portal/routes.ts` — add `fellowships` to `SectionKey`,
  `SECTION_ROUTES`, and `sectionFromPathname`.
- `web/app/src/components/portal/portal-sidebar.tsx` +
  `portal-mobile-nav.tsx` — rename Opportunities→"Grants" (BankIcon), add a
  Fellowships item (SparkleIcon).
- `web/app/src/app/app/(workspace)/fellowships/page.tsx` — **new** route.
- `web/app/src/components/portal/sections/fellowships-section.tsx` — **new**
  (the moved placeholder).
- `web/app/src/components/portal/sections/grant-filters.tsx` — **new**; pure
  `filterAndSortGrants` / `deriveGrantFilterOptions` / `hasActiveGrantFilters`
  plus the `GrantFilters` rail UI (sticky desktop, collapsible below `lg`).
- `web/app/src/components/portal/sections/opportunities-section.tsx` — drop the
  fellowships column, rename to Grants, wire in the rail + filtered list +
  "no matches" empty state.
- `docs/repo-map.md`, `docs/changelog.md` — keep the map/log accurate.

## Implementation phases (validate before advancing)

- **P0 — Worktree.** Branch off local `HEAD`; hardlink-copy `web/node_modules`.
  Validate: baseline `npx next build` passes.
- **P1 — Fellowships split.** Routes, page, section, nav (desktop + mobile).
  Validate: `tsc --noEmit`.
- **P2 — Grants + filter rail.** `grant-filters.tsx` + rewired section.
  Validate: `tsc`, `eslint`, `next build` (route `/app/fellowships` present).
- **P3 — Docs.** repo-map, this plan, changelog.
- **P4 — Commit** (no push).
- **P5 — Merge to main.** Merge local `main` into the worktree first, re-build,
  then merge into `main`. No push.

## Validation / acceptance

- `cd web/app && npx tsc --noEmit` — clean.
- `npx eslint <changed files>` — clean.
- `npx next build` — succeeds; `/app/opportunities` and `/app/fellowships` both
  build.
- Grants page shows the filter rail; filters narrow the list; "Clear all"
  resets; empty states cover loading / error / no-data / no-match.
- No frontend test harness exists in the repo, so the pure filter logic is
  verified by typecheck + review rather than a new test framework.

## Exclusions

- Funding-amount range filter (needs an amount parser).
- Any backend/matcher work; fellowship data (stays a placeholder).

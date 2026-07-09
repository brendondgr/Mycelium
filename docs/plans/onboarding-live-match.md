# Plan — Onboarding reorder + live post-onboarding matching

## Objective

Two changes to the first-run onboarding flow (`web/app/src/app/app/onboarding/`):

1. **Reorder + gate the fellowship step.** Move "What should Mylo keep an eye on?"
   (watch) *before* the "Fellowship eligibility" step, and only show the
   eligibility step when the user has the **Fellowships** signal toggled on.
   Add a **Conferences** watch toggle so all four opportunity areas are
   individually opt-in.
2. **Live matching window.** When a user finishes onboarding, instead of
   redirecting straight to `/app/overview`, show an interactive window that
   matches their saved interests against papers, grants, fellowships, and
   conferences — one area at a time, narrating what it is doing ("Reading
   through research papers…") and filling a live results table (area → matches).
   Only the areas the user opted into are run. When it finishes, the user
   continues into the workspace.

## Assumptions / decisions

- **Corpus-only matching** (confirmed with user): the live match surfaces the
  top matches from the already-scraped daily corpus via the existing pipelines.
  "Trigger a fresh scrape when < 25 matches" is documented as a follow-up — a
  synchronous live scrape in the onboarding request is too slow/fragile.
- **Conferences gets its own watch toggle** (confirmed): all four areas are
  opt-in. `WatchPreference.categories` is a free-form JSON string list
  (`accounts/serializers.py:194` just cleans the list — no enum), so no
  migration is needed.
- Reuse `apps/content/refitting.refit_user(user, areas=(area,), persist=True)` —
  it already runs papers via `recommend_for_user` and grants/conferences/
  fellowships via `run_opportunities_for_user` over the existing store (no scan/
  ingest), returns per-area counts, and persists `RelevanceScore` rows the
  workspace pages then read normally.
- Frontend drives the match **sequentially, one POST per area**, so each request
  is a single area (bounded latency) and the table builds row-by-row. No SSE /
  streaming server complexity.
- Work on branch `onboarding-live-match` in the main checkout (preview
  verification is pinned to the main checkout). Commit, do not push.

## Implementation phases

### Phase 1 — Backend match endpoint
- `apps/content/onboarding_match.py` (new): `onboarding_match_area(user, area, *, complete=None) -> dict`.
  Validates `area ∈ {papers, grants, conferences, fellowships}`, calls
  `refit_user(user, areas=(area,), persist=True, complete=complete)`, reads the
  per-area summary, and pulls a small `sample` (top ~6 titles + match_percent)
  from the freshly persisted latest-run `RelevanceScore` rows for that
  user + content type. Returns `{area, status, matched, llm, fallback, sample}`.
- `apps/content/views.py`: `OnboardingMatchView(APIView)` — `IsAuthenticated`,
  POST `{area}` → `onboarding_match_area(request.user, area)`; 400 on bad area.
- `apps/content/urls.py`: `onboarding/match/` (+ no-slash) → the view.
- **Validate:** `uv run --project web/backend python manage.py check`; ruff;
  a focused test calling `onboarding_match_area` with a stub `complete`.

### Phase 2 — Frontend API client + types
- `lib/portal/types.ts`: `OnboardingMatchArea`, `OnboardingMatchResult`.
- `lib/auth-client.ts`: `runOnboardingMatch(area)` — POST with CSRF (reuses the
  existing `ensureCsrfCookie`/`readCsrfToken` helpers), content base
  (`buildApiUrl(getPublicApiBase(), "onboarding", "match")`).

### Phase 3 — Onboarding flow reorder + gating
- `onboarding-flow.tsx`:
  - Add `conferences` to `WATCH_CATEGORIES` and to the default `watchCats`.
  - Replace the fixed `STEP_LABELS` / `panels` with a dynamically-built
    `activeSteps` list: About, Import, Review, **Watch**, then
    **Eligibility only when `watchCats.fellowships`**.
  - Make navigation key-based (`primaryAction`, `reviewBlocked`, `primaryLabel`,
    `back`) instead of hard-coded step indices, so a 4- or 5-step flow both work.

### Phase 4 — Live matching window
- `components/onboarding/onboarding-match.tsx` (new): props `{ areas, onDone }`.
  Runs the areas sequentially (papers → grants → fellowships → conferences,
  filtered to opted-in), narrates the current area, and fills a results table
  (area, status, matches, note). Per-area errors mark the row and continue.
  Reduced-motion safe. "Enter Mycelium" when done → `onDone()`.
- Wire `finish()` (non-edit): save profile/interests/watch, then
  `setScreen("matching")` (new screen state) with the opted-in areas; the match
  window's `onDone` does `router.replace("/app/overview")`.

### Phase 5 — Docs + validation + commit
- Update `docs/repo-map.md` (onboarding order/count, new module + endpoint,
  conferences toggle) and `docs/changelog.md`.
- Backend: `manage.py check`, ruff, content tests. Frontend: lint, `tsc`, build.
- Preview-verify: onboarding step order, fellowship step hidden when Fellowships
  is off, matching window narrates + tabulates.
- Commit on branch `onboarding-live-match` (no push).

## Interfaces that change

- **New** `POST /api/content/onboarding/match/` `{area}` →
  `{area, status, matched, llm, fallback, sample[]}` (auth: own user only).
- `WatchPreference.categories` may now include `"conferences"` (no schema change).
- Onboarding step order/count changes; post-onboarding no longer redirects
  straight to `/app/overview` (goes through the match window first).

## Acceptance criteria

- Watch step precedes eligibility; eligibility step is absent when Fellowships is
  off and present when on; step counter/branch reflect the live step count.
- Conferences toggle present and persisted in `categories`.
- Finishing onboarding shows the live match window, narrates each opted-in area,
  tabulates match counts, then enters the workspace.
- Only opted-in areas are matched. Backend endpoint is auth-scoped to the caller.
- Backend `check`/ruff/tests pass; frontend lint/tsc/build pass.

## Explicit exclusions

- No live scrape/rescan when an area has < 25 matches (documented follow-up).
- No SSE/websocket streaming (sequential per-area POSTs instead).
- No changes to the daily Celery jobs or the workspace feed pages.

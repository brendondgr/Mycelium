# Two-Process Recommendations

**Status:** done · **Correlation ID:** `20260713-two-process-recs`

## Objective

Split recommendation generation into two distinct processes, because they are not
the same job and today they share one code path:

1. **First sign-up** — score the user against **all currently available items**
   (the whole corpus) so a new user gets a full initial feed from their stated
   background.
2. **Daily search** — score **only the items scraped that day** (the new, unique
   items), threshold them, and **append** the passers to the user's existing
   feed. Yesterday's matches stay; they are not re-evaluated.

**Research papers are the deliberate exception.** Papers never accumulate: the
Research Papers page shows only the **latest gather batch** — "what is new for the
search that day" — and never mixes in items from a previous day's search.

## Current behaviour (what we are changing)

- **Papers** (`content/pipeline.py::recommend_for_user` / `recommend_for_target`):
  a 2026-07-11 change removed the `created_on=latest_gather_date()` scoping, so the
  Research Papers page now **retains the whole corpus** (old + new mixed). We revert
  this. `latest_gather_date()` still exists in `content/retrieval.py`.
- **Opportunities** (`content/opportunities.py::run_daily_opportunities_batch`): the
  daily run **re-scores the whole corpus** every night for every user. The read
  layer (`views._latest_scores`, `briefing._latest_suggested`) shows only the
  **latest `run_at`**, so accumulation only "works" because everything is re-scored
  daily. We switch the daily run to score **new items only** and make the read layer
  **accumulate** (union of every run's suggested rows).
- **Sign-up** = `content/onboarding_match.py` → `refitting.refit_user` over the whole
  corpus (correct already — keep it, and make it the authoritative whole-corpus pass).

Data-model facts relied on: `RelevanceScore.content` is `CASCADE` (pruned items drop
their scores) and unique per `(content, target_*)`, so `update_or_create` keeps one
row per pair. `ContentItem.created_at` is the immutable ingest date; opportunities
also carry immutable `metadata.first_seen`.

## Design decisions (confirmed with the user)

- **Daily opportunities:** score only that day's new items and append to a feed that
  persists until each item is pruned at its deadline; sign-up/refit still scores the
  whole corpus. → read layer changes from "latest run" to "all suggested rows".
- **Papers at sign-up (hybrid):** match the latest batch with **no scan**; if there
  are **≥ 30** high-quality suggestions (**≥ 80 %** match) show them; otherwise kick
  off a **background scan** for the user's watch topics and show a
  "scanning new articles for you" state.

## Assumptions

- "New today" for opportunities = `ContentItem.created_at::date == run date` (same as
  `metadata.first_seen` for a genuinely new item; a re-scraped existing item keeps its
  original `created_at`, so it is correctly excluded).
- Papers use `latest_gather_date(PAPER)` (freshest day *any* paper was gathered), so a
  quiet scan day shows the last good batch rather than an empty page — never mixing
  days.
- `replace` semantics are derivable: a **whole-corpus** run (`created_on is None`,
  i.e. sign-up/refit) replaces the target's suggested set for the area; a
  **new-only** run (`created_on` set, i.e. daily) accumulates.
- A Celery worker + Redis are available (compose `worker` service) for the background
  scan.

## Ordered implementation phases

Each phase is independently validated and committed. Phases 2 and 3 are ordered so
main is never left in a broken state (read-accumulate lands before daily-new-only).

1. **Papers fresh-only revert** — `pipeline.py`: pass
   `created_on=latest_gather_date(PAPER)` into `fuse_interests_pool` / `_single_vector`
   in `recommend_for_user` and `recommend_for_target`. Update docstrings. Rewrite
   `test_pipeline.py::test_recommend_retains_older_papers_and_pins_fresh` → fresh-only.
2. **Opportunity feeds accumulate on read + refit replace** — `views.py`: add
   `_accumulated_scores` (all suggested rows across runs, pinned-first then match/score
   desc, capped by `OPPORTUNITY_FEED_MAX`) and point the grants/conferences/fellowships
   personal feeds and the lab/project grants/conferences at it (papers stay
   latest-run). `briefing.py`: opportunity categories accumulate, papers stay
   latest-run. `opportunities.py::_persist`: add `replace` mode (whole-corpus runs drop
   this target's prior suggested rows for the area not in the new set).
3. **Daily opportunities score new items only** — `opportunities.py`: thread
   `created_on` so `run_daily_opportunities_batch` scopes matching to items first-seen
   today (`_prepare_match`, `_prepare_fellowship_match`, `_fellowship_embed_by_id`).
   Serial/refit/onboarding pass `created_on=None`. Derive `replace = created_on is None`.
4. **Papers onboarding hybrid + background scan** — `onboarding_match.py`: if the
   latest-batch papers match yields < 30 suggestions ≥ 80 %, enqueue
   `content.tasks.scan_and_recommend_for_user` (dedup via a cache key) and return status
   `scanning`. `DailyReportView` returns a `scanning` flag while the key is set. New
   settings + `.env.example` entries.
5. **Frontend scanning state** — `onboarding-match.tsx` renders a `scanning` papers
   row; `research-papers-section.tsx` shows a scanning banner. Verify with
   `tsc` + `eslint` + `next build` (preview is pinned to the main checkout, so no live
   browser verify from the worktree).
6. **Full suite, docs, merge** — full `apps/content` suite + `ruff`; update
   `docs/repo-map.md`, `docs/changelog.md`, memory; merge the worktree branch into local
   `main` (left unpushed).

## Public interfaces / schemas that change

- `GET /api/daily-report/` gains a `scanning: bool` field.
- `POST /api/content/onboarding/match/` (papers) may return `status: "scanning"`.
- Opportunity feed reads (`/api/opportunities/grants|conferences/`,
  `/api/opportunities/fellowships/`, lab/project recommendations) now return the
  accumulated feed rather than the latest run.
- New settings (root `.env`): `OPPORTUNITY_FEED_MAX`,
  `PAPER_ONBOARDING_MIN_HIGH_QUALITY`, `PAPER_ONBOARDING_HIGH_QUALITY_PERCENT`.
- New Celery task `apps.content.scan_and_recommend_for_user`.

## Validation & acceptance criteria

- Backend: `apps/content` suite green against a pgvector Postgres; `ruff check` clean.
- Papers: a run persists/surfaces only the latest gather day; an older still-matching
  paper is **not** in the feed.
- Opportunities: after two daily runs on different days, both days' passing items are in
  the feed; a daily run only scores items first-seen that day.
- Onboarding: a sparse latest batch returns `scanning` and enqueues one scan; a rich
  batch (≥ 30 ≥ 80 %) does not.
- Frontend: `tsc`, `eslint`, `next build` clean; scanning state renders.

## Exclusions

- No change to the literature scan window, the fusion/threshold math, the LLM prompts,
  pinning windows, or the search (`/api/search/`) pipeline.
- No new graph/report work; departments remain out of scope for opportunity targets.
- No live browser verification of the frontend from the worktree (preview is pinned to
  the main checkout); static verification only.

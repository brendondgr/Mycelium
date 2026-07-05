# Two-Phase Batch Ingest → Recommend — Implementation Plan

## Objective

Split the daily research pipeline from its current **per-user serial** shape
(each user scans → dedups → embeds → recommends in isolation) into two phases:

1. **Global ingest (once per run):** gather the union of every selected user's
   search terms, run each unique term through the sources once, dedup as we go,
   embed all genuinely-new papers in a single batched pass, and upsert them into
   the shared `ContentItem` store.
2. **Per-user recommend:** for each user, retrieve + fuse + rank + suggest against
   the now-populated shared store — **no scanning or paper-embedding per user.**

This removes the two big inefficiencies: the same shared topic being **re-searched
once per user** (N× external API calls), and papers being embedded inside each
user's turn instead of once in a single large batch (where CPU/GPU parallelism
actually pays off).

Grounded in the current code: `apps/content/pipeline.py::run_for_user`,
`apps/content/tasks.py::run_daily_suggestions`, `apps/scraper/ingest.py::scan`.

## Locked decisions

1. **Search-term pool = the union of users' `WatchPreference.topics`**, deduped
   case-insensitively. This preserves today's separation of concerns established
   by the fusion work: **watch topics drive the *search*; `interests.areas` drive
   the *ranking*.** (Switching the pool to areas or the union of both is a
   one-line change in `gather_scan_queries` if wanted later.)
2. **Recommendation stays scoped to users who have watch topics** — same
   population that contributes search terms, identical to today. A user with no
   topics still returns `no_watch_topics` (they haven't opted into monitoring).
   Recommending to topic-less users from the shared store is a deliberate
   non-goal for this pass.
3. **Global dedup is the store's job** (as today): `scan` already dedups
   cross-source and against already-stored rows, and upserts by
   `(source, external_id)`. Running the *union* of terms through one `scan` call
   means the whole run's new papers are deduped and embedded together, in one pass.
4. **Single-user runs (`--user`) keep working**: `run_for_user` stays as
   "scan this user's topics, then recommend" so existing tests and the CLI
   `--user` path are unchanged in behaviour.

## Public interfaces changing

`apps/content/pipeline.py`:
- **New** `gather_scan_queries(users, *, per_user_limit, global_limit=None, log=None) -> list[str]`
  — union of users' watch topics, deduped, order-preserving, optionally capped
  (logs the count / any truncation — no silent caps).
- **New** `recommend_for_user(user, *, ..., scan_summary=None) -> RunResult`
  — everything `run_for_user` does *after* the scan (embed profile, fuse /
  single-vector, suggest, persist). No scan inside.
- **New** `run_daily_batch(users, *, ..., search_fn=None, scan_embedder=None) -> BatchResult`
  — Phase 1 (`gather_scan_queries` → one `scan`) then Phase 2 (loop
  `recommend_for_user`). Returns the global `ScanSummary` + per-user `RunResult`s.
- **Refactor** `run_for_user` to reuse `recommend_for_user` (scan this user's
  topics, then delegate). Behaviour and signature unchanged.

`apps/content/tasks.py::run_daily_suggestions`:
- Replace the per-user `for` loop with a single `run_daily_batch` call; log the
  global ingest summary once, then each user's recommend result. Return shape
  stays a list of per-user dicts (plus an ingest summary entry).

No model, migration, API-contract, serializer, or frontend change. `RunResult`
gains no new required fields (per-user `scanned_new`/`embedded` become 0 in the
batch path since ingestion is global; the global counts live in the run log and
the returned ingest summary).

## Implementation phases (validate each before the next)

### Phase 0 — Scaffolding
- Worktree off `main`; host venv; confirm baseline `apps/content` suite green.

### Phase 1 — `gather_scan_queries` (pure-ish)
- Union of `build_queries(_watch_topics(u), limit=per_user_limit)` across users,
  deduped case-insensitively, order-preserving; optional `global_limit` with a
  log line when it truncates.
- **Validate:** unit tests — three users with overlapping topics collapse to the
  unique union; per-user and global limits respected; empty users → `[]`.

### Phase 2 — Extract `recommend_for_user`
- Move the post-scan body of `run_for_user` into `recommend_for_user`; keep the
  `no_profile` / `no_watch_topics` / `no_embedder` / `no_results` statuses.
- Refactor `run_for_user` = scan this user's topics → `recommend_for_user(...,
  scan_summary=summary)`. Signature and behaviour unchanged.
- **Validate:** the existing `test_pipeline.py` suite (single-vector fallback,
  fusion, idempotence, dry-run, graceful degradation) stays green **unchanged**.

### Phase 3 — `run_daily_batch`
- Phase 1 gather → one `scan` over the union → Phase 2 loop
  `recommend_for_user(scan_summary=None)`. Per-user failures are caught and
  logged (one bad profile never sinks the batch), matching today.
- **Validate:** the efficiency regression — N users sharing topics trigger the
  sources **once per unique term**, not once per user (count calls to an injected
  `search_fn`); every user still gets recommendations from the shared store; a
  paper pulled by one user's term is recommendable to another user.

### Phase 4 — Wire the task + command
- `tasks.run_daily_suggestions` calls `run_daily_batch`; log the ingest summary
  once, then per-user lines. Keep the `--async` / `select_users` surface.
- **Validate:** full backend suite green on pgvector; `run_daily_suggestions`
  management command still runs (dry-run smoke against the throwaway pgvector DB);
  `manual_search.py` still triggers the same path.

### Phase 5 — Finalize
- Update `docs/repo-map.md`, `docs/changelog.md`, and the
  `daily-research-suggestions` memory to describe the two-phase shape.
- `ruff` clean; commit (no push); merge worktree → `main`.

## Validation & acceptance criteria

- Host venv workaround: `export UV_PROJECT_ENVIRONMENT=/home/bdgr/.cache/mycelium-backend-venv`.
- Offline: `DATABASE_URL="sqlite:///…" uv run --directory web/backend python -m pytest apps/content -q`.
- pgvector: throwaway `pgvector/pgvector:pg17` on `:5433`, full suite.
- `uv run --project web/backend ruff check web/backend`.
- **Acceptance:** shared search terms are searched once regardless of user count
  (efficiency test); every current per-user behaviour/status preserved; existing
  `test_pipeline.py` green unchanged; suite + lint green; docs + memory updated;
  committed (not pushed); worktree merged to `main`.

## Security / data ownership

No auth-surface change. Ingestion writes only global `ContentItem` rows;
recommendation writes only `RelevanceScore` rows scoped to `target_user`. No
cross-user data exposure is introduced — the shared store was always global; only
the *orchestration* changes.

## Explicit exclusions

- Parallelizing the per-user recommend loop or the scan (threads/Celery fan-out)
  — separate follow-up; this pass is about removing redundant work, not
  concurrency. Noted as the next efficiency lever.
- Recommending to users with no watch topics (decision 2).
- Changing the search-term pool to areas / union (decision 1).
- onnxruntime thread tuning / GPU execution providers.

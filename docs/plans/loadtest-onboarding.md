# Plan: Onboarding Load-Test Harness

## Objective

A configurable, deterministic load-test harness that stress-tests Mycelium's
server-side compute by simulating concurrent user onboarding over a time window:
account creation, profile filling, watch preferences, and the per-area
recommendation match (embedding retrieval + LLM scoring). It streams a live
console dashboard during the run, produces a summary table + detailed CSV after,
and deletes every fake user it created.

The harness is a **pure HTTP client** (it exercises the real API the browser
uses) plus one **Django management command** for cleanup (the only correct way to
cascade-delete a user, since there is no HTTP delete-user endpoint).

## Onboarding sequence per simulated user (mirrors the real UI flow)

The browser flow (`web/app/src/components/onboarding/onboarding-flow.tsx` +
`lib/auth-client.ts`) maps to these calls against the Django API
(`http://127.0.0.1:8000/api` by default):

1. `GET  /api/auth/csrf/` — obtain the `csrftoken` cookie.
2. `POST /api/auth/register/` — `account_type="personal"`, marker username/email.
   Creates User + Profile (signal) + Subscription + Seat, logs in (session cookie).
3. `PATCH /api/auth/profile/me/` — role + institution basics (Profile save → embedding hook).
4. `POST /api/auth/intake/confirm/` — deterministic `interests` built from the
   user's 2–3 selected catalog interests (Profile save → embedding hook = **embedding generation**).
5. `PATCH /api/auth/watch/me/` — topics + variable `categories` (most users all four; a random subset drops some) + cadence.
6. For each opted-in area in `[papers, grants, fellowships, conferences]`
   (gated by the watch categories): `POST /api/onboarding/match/` `{area}` — the
   heavy path: retrieve → fuse → LLM score over the existing corpus, persists
   `RelevanceScore` rows. Response `{matched, llm, fallback, sample}` feeds the metrics
   (`llm` = genuine model scores, `fallback` = deterministic; each call = **embedding filtering/search**).

CSRF: read the current `csrftoken` from the cookie jar before each unsafe request
and send it as `X-CSRFToken` (Django rotates the token on login, so re-read each time).

## Assumptions / constraints

- **Register throttle**: `DEFAULT_THROTTLE_RATES["register"]` defaults to `20/hour`
  per anon IP. A bulk run WILL be throttled. The server must be started with
  `DJANGO_REGISTER_THROTTLE_RATE` set high/disabled (e.g. `1000000/hour`). The
  client counts 429s as errors and can retry with backoff. Documented in the README.
- **Fake-user profile is deterministic**, not LLM-generated: interests come from a
  static catalog; the LLM stress comes from the match step, per the task's key design note.
  An optional `--synthesize` flag additionally exercises `POST /api/auth/intake/synthesize`
  with a résumé built from the selected interests (off by default).
- **Cleanup** cascades cleanly for `account_type="personal"`: deleting the User
  cascades Profile (OneToOne), Subscription (`scope_user` CASCADE), Seat
  (`member`/`payer_user`/`subscription` CASCADE), RelevanceScore (`target_user`
  CASCADE), SavedOpportunity, audit events. No orphaned Lab/Department.
- Base URL points at Django directly (`:8000`) to stress backend compute, not the Next proxy.
- Corpus may be empty on a fresh DB → match returns `matched=0` without error; the
  harness still exercises retrieval/scoring and validates end-to-end.

## Files

| Path | What |
|---|---|
| `loadtest.py` (root) | PEP-723 uv script: async client, scheduler, live dashboard, analytics. `uv run loadtest.py …` |
| `loadtest/__init__.py`, `loadtest/interests.py` | Static catalog of ~150 diverse interests + deck-based near-uniform selector |
| `loadtest/README.md` | How to run, the throttle env requirement, cleanup, output formats |
| `web/backend/apps/accounts/management/commands/loadtest_purge.py` | Delete fake users by marker (`--email-domain` / `--username-prefix` / `--run-id`), `--dry-run`, safety guard |

## Configuration (CLI flags)

`--users` (default 500), `--window` (seconds/`Xm`, default 30m), `--base-url`,
`--max-concurrency` (default 50), `--seed`, `--all-categories-fraction` (default 0.8),
`--synthesize` (default off), `--out-dir`, `--run-id`, `--no-cleanup`,
`--purge-cmd` (how to invoke the management command), `--no-live`, `--request-timeout`.

## Live dashboard (during run)

Refreshes ~2×/s (TTY: ANSI in place; non-TTY: periodic snapshots). Shows: users
created / completed / failed vs target; match (LLM) ops in-flight + completed;
embedding ops (profile writes + match filters) completed; loop/iteration count;
running error count; elapsed / remaining in window; avg + p95 latency per stage;
aggregate LLM vs fallback scores; throughput (users/min, ops/s).

## Analytics (after run)

- Printed **summary table**: totals, success/error counts, error breakdown by
  endpoint+status, per-stage timing (count/mean/p50/p95/max), match totals
  (matched/llm/fallback), wall-clock, throughput.
- `operations.csv` — one row per HTTP request (run_id, user_idx, username, stage,
  area, method, url, status_code, ok, latency_ms, started_at, error).
- `summary.csv` — one row per aggregate metric.

## Time distribution

Each user gets a uniform-random start offset in `[0, window)` (allows natural
bursts — not evenly spaced). Coroutines sleep-until their offset, gated by a
concurrency semaphore. The run ends only when **every** user coroutine has
finished (may extend past the window if late starters are still processing),
then cleanup runs.

## Validation / acceptance

- `uv run --project web/backend python web/backend/manage.py check` passes (command registers).
- Smoke: local backend up (Postgres :11450, high register throttle), `uv run loadtest.py --users 2 --window 20 --base-url http://127.0.0.1:8000/api`:
  full sequence 201/200s, live table renders, `operations.csv`/`summary.csv` written,
  summary prints, and `loadtest_purge` deletes exactly the 2 users (verified via `/api/auth/me` 401 + DB count).
- No large stress run performed here (operator does that).

## Exclusions

- No new HTTP delete-user endpoint (cleanup is ORM via the management command).
- No changes to product onboarding endpoints/UI.
- Does not seed the corpus (papers/grants/etc.) — that is a separate scan/ingest concern.

## Commit / merge

Working tree already carries unrelated in-progress `onboarding-live-match` edits.
Stage and commit **only** the new load-test files (script, package, command, docs,
changelog, repo-map). No push. Not using a separate worktree (the harness depends on
the `/api/onboarding/match` endpoint that lives on this branch and is not yet on
`main`), so the "merge to main" step does not apply.

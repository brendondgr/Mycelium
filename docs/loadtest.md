# Onboarding load test

`ops/loadtest/loadtest.py` (repo root) stress-tests Mycelium's **server-side compute** by
simulating many users onboarding concurrently over a time window. It replays the
exact API the browser uses, so the load lands on the real hot paths:

- **Embedding generation** — each profile write rebuilds the interest embedding.
- **Embedding filtering / search** — each per-area match retrieves over pgvector.
- **LLM recommendation generation** — the match step scores candidates with the model.

Fake users are built **deterministically** from a static interest catalog
(`ops/loadtest/loadtest_interests.py`, ~144 interests across 24 fields) — the LLM is exercised
by the *recommendation* step, not by user generation. The harness is a pure HTTP
client; cleanup is a Django management command (`loadtest_purge`).

## What each simulated user does

Mirrors `web/app/src/components/onboarding/onboarding-flow.tsx`:

| # | Call | Server effect |
|---|------|---------------|
| 1 | `GET /auth/csrf/` | obtain the CSRF cookie |
| 2 | `POST /auth/register/` | create a **personal** account + workspace, log in |
| 3 | `PATCH /auth/profile/me/` | role + institution → Profile save → embedding hook |
| 4 | `POST /auth/intake/synthesize/` | *optional* (`--synthesize`): LLM drafts interests from a résumé |
| 5 | `POST /auth/intake/confirm/` | save deterministic interests → embedding generation |
| 6 | `PATCH /auth/watch/me/` | topics + **variable** categories + cadence |
| 7 | `POST /onboarding/match/` ×N | one per opted-in area (papers/grants/fellowships/conferences): retrieve → fuse → LLM score |

Users start at **random offsets** across the window (bursts allowed — not evenly
spaced). The run ends only when **every** user has fully finished (it may run past
the window if a late starter is still processing), then all fake users are deleted.

## Prerequisites

1. The backend + Postgres (pgvector) + Redis running. With the compose stack the
   API is at `http://localhost:11350/api` (backend direct) or `http://localhost:11050/api`
   (nginx). Hit the backend **directly** to stress its compute.
2. **Raise the registration throttle.** `DEFAULT_THROTTLE_RATES["register"]`
   defaults to `20/hour` per anonymous IP — a bulk run will be throttled (HTTP 429).
   Set a high value in your local `.env` (the compose backend reads it) and
   recreate the backend so it takes effect:

   ```
   # .env
   DJANGO_REGISTER_THROTTLE_RATE=1000000/hour
   ```
   ```bash
   docker compose up -d --force-recreate --no-deps backend
   ```

   The throttle counter lives in the backend's in-process cache, so recreating (or
   restarting) the backend also **clears an existing block** immediately — deleting
   the fake users does not (wrong storage). A 1–2 user smoke test stays under the
   default and needs no change.

3. **Warm the embedding model (first run only).** The match step embeds text with
   FastEmbed/ONNX. The model persists in `data/models/fastembed/` (bind-mounted, set via
   `FASTEMBED_CACHE_PATH` in `compose.yaml`) so it downloads once. If it is missing
   (e.g. right after a container recreate wiped an old `/tmp` cache), a burst of
   concurrent first-requests can race the download and return `HTTP 500`. Warm it
   once before a big concurrent run:

   ```bash
   docker compose exec -T backend uv run --project web/backend \
     python web/backend/manage.py shell -c \
     "from apps.scraper.embedding import get_default_embedder; get_default_embedder()(['warm up'])"
   ```

## Running

`uv run` installs `httpx` from the script's inline metadata automatically:

The default `--base-url` already points at the compose backend (`http://localhost:11350/api`),
so most runs need no URL flag:

```bash
# default: 500 users over 30 minutes
uv run ops/loadtest/loadtest.py --users 500 --window 30m

# quick smoke test (2 users, 20s window)
uv run ops/loadtest/loadtest.py --users 2 --window 20

# also exercise the LLM profile-fill (résumé synthesis)
uv run ops/loadtest/loadtest.py --users 200 --window 15m --synthesize

# override the target only when it differs (e.g. bare dev server / nginx)
uv run ops/loadtest/loadtest.py --users 500 --window 30m --base-url http://127.0.0.1:8000/api
```

### Key flags

| Flag | Default | Meaning |
|---|---|---|
| `--users` | 500 | number of fake users |
| `--window` | `30m` | onboarding window (`30m`, `90s`, `1h`, or bare seconds) |
| `--base-url` | `http://localhost:11350/api` | API base — the compose backend on host `:11350` (→ container `:8000`), hit directly |
| `--max-concurrency` | 50 | max simultaneous in-flight users |
| `--seed` | 1337 | RNG seed — reproducible user mix and schedule |
| `--all-categories-fraction` | 0.8 | fraction of users who enable all four match areas |
| `--synthesize` | off | also POST a résumé to `/intake/synthesize` (extra LLM load) |
| `--out-dir` | `data/loadtest/` | where CSV reports are written |
| `--run-id` | auto | tag for usernames + filenames (`lt_<run-id>_NNNNN`) |
| `--no-cleanup` | off | keep the fake users (purge manually) |
| `--purge-cmd` | host `manage.py loadtest_purge` | how cleanup deletes the users |
| `--no-live` | off | print periodic snapshots instead of the in-place table |
| `--log-file` | `<out-dir>/loadtest_<run-id>.log` | full run log path |
| `--log-level` | `INFO` | file log verbosity (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `--log-requests` | off | log *every* request, not just failures |

## Live monitoring

While running, a status table refreshes ~2×/s (in place on a TTY; periodic
snapshots otherwise): users started/done/failed vs target, requests in-flight and
done, match (LLM) calls in-flight and done with LLM-vs-fallback counts, embedding
generation and filter/search counts, elapsed vs window-remaining, per-stage
mean/p95 latency, error count and breakdown, and throughput.

## Output

- Printed **summary table** — totals, per-stage count/mean/p95/max, match totals
  (matched / genuine-LLM / deterministic-fallback), **user failures by stage**, an
  **error breakdown** (stage + status), and **likely-cause hints**, plus wall-clock
  and throughput.
- `data/loadtest/loadtest_<run-id>.log` — **the full run log**: the start config,
  every failed request with its **full response body** (or the exception), each
  user's failure stage, the mirrored summary, and cleanup. This is the file to read
  when the "failed" count is high. Pass `--log-requests` to also log every successful
  request.
- `data/loadtest/operations_<run-id>.csv` — **one row per HTTP request**
  (run_id, user_idx, username, stage, area, method, status_code, ok, latency_ms,
  started_at, error).
- `data/loadtest/summary_<run-id>.csv` — one row per aggregate metric.

`data/loadtest/` is git-ignored.

### Diagnosing failures

The summary and log call out *why* users failed. The most common cause is the
registration throttle: a run that wasn't given a raised `DJANGO_REGISTER_THROTTLE_RATE`
hits `HTTP 429 {"detail":"Request was throttled…"}` at the `register` stage — the log
shows the throttle body and the summary prints a hint to raise the rate (see
Prerequisites). Note the throttle counts by IP over a rolling hour and is **not**
reset by deleting the fake users, so after a throttled run you may keep seeing 429s
until the window clears (or you restart the backend / clear its cache). Other
diagnosed cases: connection/timeout saturation (lower `--max-concurrency`), HTTP 403
(CSRF / untrusted origin), and 400 duplicate accounts from a prior run (purge or use
a fresh `--run-id`).

## Cleanup

Fake users carry two markers: the email domain `@loadtest.mycelium.test` and the
username prefix `lt_`. Deleting a personal-account `User` cascades its whole
footprint (Profile, Subscription, Seat, RelevanceScore, SavedOpportunity, audit
rows), so cleanup is just a delete:

```bash
# runs automatically at the end of a run, or by hand:
uv run --project web/backend python web/backend/manage.py loadtest_purge            # all
uv run --project web/backend python web/backend/manage.py loadtest_purge --dry-run  # preview
uv run --project web/backend python web/backend/manage.py loadtest_purge --run-id 7f3a1c
```

The email-domain marker is always required, so the command can never match a real
account; staff/superusers are refused as a second guard. If the backend runs only
inside Docker, point `--purge-cmd` at the container, e.g.
`--purge-cmd "docker compose exec -T backend python manage.py loadtest_purge"`.

## Design notes / limitations

- The corpus (papers/grants/fellowships/conferences) is **not** seeded here — on an
  empty store the match returns `matched=0` without error. Seed via the normal scan/
  ingest jobs for a realistic recommendation load.
- Cleanup needs DB access (no HTTP delete-user endpoint exists); it runs on the host
  by default. For a remote target, run `loadtest_purge` where the DB is reachable.

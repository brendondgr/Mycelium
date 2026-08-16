# ISSUES — EXP-2026-08-006

## 1. The prose-overlap floor is probably mis-set for conferences (blocks a clean re-run)

`ungrounded_prose` is the dominant failure in every arm. The 0.45 floor came
from the collector, where it validated summaries against **full fetched web
pages**. Here, conference source text is title + acronym + series name + CCF
area codes — roughly twenty content words. A faithful 2–3 sentence summary
cannot score 0.45 against that denominator.

**Fix before re-running:** make the floor domain-aware, or normalise by source
length, or gate conferences on fetched-page text rather than the stub record.
Until then every coverage number here is a lower bound.

## 2. The harness did not record failures per domain

`failure_reasons` is tallied across all 32 records with no grant/conference
split — which is precisely the breakdown issue 1 needs. Add a `kind` dimension
to `CallRecord` aggregation before the next run.

## 3. Stage B cells 4 and 8 are contaminated by endpoint congestion

They ran directly after the thinking-heavy Stage A arms and caught the proxy
still draining. p95 ~61 s against ~9.4 s for the later cells, with identical
verification outcomes. **Do not cite 4- or 8-worker numbers from this run.**

Fix: randomise cell order, or insert an idle-until-quiet gate between cells, and
replicate each cell.

## 4. `code.dirty: true` — what was uncommitted

The worktree had substantial uncommitted work when this ran: the vendored
collector at `web/backend/apps/scraper/collect/` (Phase 1) and the code lifted
out of `apps/scraper/pivot/` (Phase 2). **Neither is on this experiment's code
path.** The harness at `code/run.py` imports only `apps.core.llm` and reads the
two upstream SQLite stores directly; it does not import `apps.scraper.collect`.
The dirty flag is accurate but the uncommitted code is not a confound.

## 5. `LLM_BASE_URL` was overridden for the run

`.env` sets `http://host.docker.internal:4000/v1`, which resolves only inside a
container. The run overrode it to `http://localhost:4000/v1` — the same proxy,
reached by its host-side name. No other setting was changed.

## 6. Two harness bugs found and fixed before the recorded run

- `LLMResponse` has no `.text`; the field is `.content`.
- `apps.core.llm` exposes `LLMConfigurationError`, not `LLMError`. Transport and
  API errors propagate straight from the OpenAI SDK, so the retry now catches
  broadly and counts every failure as a retryable `model_failed` — never as a
  settled answer. The collector once wrote 321 `model_failed` rows in one
  over-concurrent run; treating those as answers would have excluded 321 records
  from enrichment permanently.

## 7. An earlier aborted run

A first run at `n = 30` with a `{1, 12, 24}` sweep was killed mid-Stage-A and
replaced by this `n = 32`, `{4, 8, 12, 16}` design. Nothing from it is recorded
and no numbers from it appear anywhere. Recorded here rather than deleted.

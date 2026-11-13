# EXP-2026-11-010 — Issues

- 2026-11-09, attempt 1: `InternalServerError 502 — upstream error: ConnectError:
  All connection attempts failed` from the relay at `localhost:4000` (model
  `skynet`, relay health `failed`). Nothing was measured; `logs/attempt.json`
  records the error. Status set to `failed` for this attempt.
- The manifest records `code.dirty: true` because the experiment was
  scaffolded while the Mylo agent change (branch `mylo-agent`) was
  uncommitted; the harness and the agent code it measures were committed
  together in the same change.
- 2026-11-12, attempt 2. A1 first launch (23:14) failed to write its output:
  the backend container mounts the repository read-only, and the runner
  crashed writing `logs/attempt.json`. Rerun at 23:16 with the research folder
  mounted writable (`docker compose run … -v docs/research:/app/docs/research`,
  run as the host user); that run is A1 `r1`. Nothing measured was lost.
- 2026-11-12, A2 smoke test (one question, `logs/a2_smoke.jsonl`) to check the
  harness before the pre-registration commit; excluded from every number.
- **2026-11-12, A2 run `a2` (23:19–23:31) was NOT on an idle model server.**
  The nightly run (`mylo-daily.service`) had been started by hand at 22:58 and
  was in its stage 2/14 (searching and ranking papers for every target: model
  write-ups and decision-server reranking) for the whole of A2. The protocol
  asked for an otherwise idle server; this run does not meet it. It is kept and
  reported as "under the nightly's load", and A2 is rerun after the nightly
  finishes (run `a2idle`).
- A1 `r1` (23:16–23:17) also overlapped the nightly (stage 2/14); A1 is rerun
  after the nightly finishes (run `r2idle`).
- The relay does not expose vLLM's queue metrics, so idleness can only be
  asserted from what this host runs, not observed on the A100.
- 2026-11-13 00:32–00:42: A1 `r2idle` and A2 `a2idle` ran after the nightly
  had finished (00:31) and with no other experiment of this session using the
  model. A second idle A2 run (`a2idle2`) follows the decision-server load
  test, which uses a different GPU.
- 2026-11-12, harness bug fixed before the idle runs: the per-call
  `function_calls` field read `reply.calls` (the raw reply calls them
  `tool_calls`), so it is 0 in run `a2`'s `calls[]`. Turn-level function counts
  come from the event log and are correct in every run; no reported number
  uses the per-call field.

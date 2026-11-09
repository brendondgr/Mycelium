# EXP-2026-11-007 — Protocol

Written before the run, on 2026-11-09.

## Question

Can a small decision model served on this host (`d3-lite`, 0.85B, on the local
"Decisions" server at `127.0.0.1:5107`) answer the exact questions the
`RERANK_METHOD=typesafe` stage asks TypeSafe's hosted Jev, fast enough and with
enough discrimination to be a candidate local replacement?

This is a **feasibility smoke test**, not a relevance measurement. There are no
human judgements in it.

## Hypothesis

Exploratory — no prior hypothesis about agreement. We expect the server to work
(every call answered) and latency to be well under the hosted API's per-call
cost; whether a 0.85B model discriminates at all is the open part.

## Setup

- **System under test:** `d3-lite` revision
  `03560c26f5199c3c04129a2ccb38960c913635e0` (`vllm-sr/d3-lite`), loaded by the
  Decisions server on CUDA in bfloat16, via `POST /v1/decide`.
- **States:** built by the production functions in
  `tools/recommendation/typesafe_rerank.py` (`profile_block`, `candidate_block`,
  `build_state`, question version `2026-09-17.1`) — byte-for-byte what the
  nightly stage would send Jev.
- **Questions:** the production `questions_for(content_type)` translated to the
  server's schema: a Noul with true/false criteria becomes a `yesno` whose
  question text carries both criteria; the four-level `fit` Score becomes a
  `score` with the same four level descriptions; grants add `eligible`,
  conferences add `venue_fit`. One call per pair, all questions in it.

## Data

One reader (`brendondgr`, 5 themes) from the local production store on
2026-11-09: the top 8 of each theme's current per-theme slate for papers,
grants and conferences (120 pairs), plus an **off-theme control** (45 pairs):
each theme's top-3 items paired with a different theme whose slate does not
hold them. The reader's profile text is sent to the local server only and
never written into this folder (SHA-256 and length only).

The comparator `stored_verdict` is **a system output** — the prose model's
per-theme verdict (skip/file/skim/read) — not a human assessment.

## Metrics

1. **Availability:** answered / asked (primary gate: must be 100 %).
2. **Latency:** server-reported `ms` per call, p50 and p95.
3. **Discrimination (primary):** ROC AUC of `P(worth = yes)` separating
   on-theme pairs (each theme's top 3) from their off-theme controls (the same
   items). Same items on both sides, so only the strand differs.
4. **Agreement with the prose verdict:** argmax `fit` level equal to the stored
   verdict (exact) and within one level; Spearman between `fit` expected value
   and verdict index. Jev scored 56.1 % exact in `EXP-2026-09-003` on a
   different day's grant/conference slates — a reference point, not a paired
   baseline.
5. **Saturation:** share of on-theme `worth` probabilities above 0.95 or below
   0.05 (a sort key that saturates collapses to fused order on ties).
6. **Reorder movement:** mean Kendall τ between fused rank and the `worth`
   order within each theme's head (descriptive).
7. **Determinism:** 5 pairs asked 3 times; max absolute difference in `worth`.

## Baselines

- Fused order (what `RERANK_METHOD=local` ships) for metric 6.
- The prose model's stored verdict for metric 4.
- No paired Jev baseline: this store holds no `signals["typesafe"]` rows, and
  re-billing Jev is out of scope for a smoke test.

## Procedure

```bash
S=<scratch dir outside the repo>
docker compose exec -T backend sh -c 'cd web/backend && uv run --no-sync python \
  /app/docs/research/experiments/EXP-2026-11-007-d3-lite-local-decision-smoke/code/extract.py \
  --user brendondgr --per-theme 8' > $S/states.json
python3 docs/research/experiments/EXP-2026-11-007-d3-lite-local-decision-smoke/code/decide.py \
  --states $S/states.json --url http://127.0.0.1:5107
python3 docs/research/experiments/EXP-2026-11-007-d3-lite-local-decision-smoke/code/analyse.py
```

## What would falsify this

- Any unanswered call, or p95 latency above 1 s per call → not viable as a
  nightly sidecar on this host.
- Discrimination AUC below 0.75 → the model is not reading the strand; a local
  replacement needs a larger model (e.g. the pplx-decider candidate) before
  anything else is built.
- Exact verdict agreement far below Jev's 56 % (under 40 %) → flagged as a
  quality gap to measure properly with judgements before switching.

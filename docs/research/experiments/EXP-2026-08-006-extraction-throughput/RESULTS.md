# RESULTS — EXP-2026-08-006

Run 2026-08-16. `n = 32` records (16 grants, 16 conferences) per cell, 8 cells.
Endpoint: LiteLLM proxy at `localhost:4000`, model `skynet`, temperature 0.0,
`MAX_ATTEMPTS = 3`, prose-overlap floor 0.45.

Raw numbers: `data/metrics.json`, `data/metrics.csv`. Sample: `data/sample.json`.

## Headline

**The 5–6 hour estimate in the plan was wrong, and it was wrong in both
directions depending on the reasoning arm.** It was extrapolated from the
standalone collector's table, which measured a different server. The hypothesis
that 25–49 s median latency is a property of that endpoint rather than a floor
is **confirmed**: with thinking off, median latency here is **2.96 s**.

But the fast arm is not free, and the raw latency number hides why.

## Stage A — reasoning arms at 12 workers

| Arm | rec/s | median | 1st-attempt valid | **refusal** | verified | projected backfill |
|---|---|---|---|---|---|---|
| `thinking-none` | **0.722** | **2.96 s** | 0.500 | **34.4 %** | 21/32 | **1.70 h** |
| `thinking-medium` | 0.099 | 31.16 s | 0.438 | **6.2 %** | **30/32** | 12.39 h |
| `effort-low` | 0.110 | 31.75 s | 0.531 | 15.6 % | 27/32 | 11.17 h |
| `effort-medium` | 0.082 | 44.37 s | 0.469 | 28.1 % | 23/32 | 15.03 h |

**Thinking off is ~7× faster and refuses ~5× more records.** Speed and coverage
trade directly, and `first_attempt_valid_rate` — which is nearly flat at
0.44–0.53 across every arm — completely hides it. Refusal rate is the number
that matters, because a refused record falls back to raw-text embedding and
shows no summary.

Two secondary findings:

- **The proxy does honour `reasoning_effort`.** `effort-low` (31.75 s) and
  `effort-medium` (44.37 s) differ materially, so the level is not being
  discarded. This was an open question in the protocol.
- **`effort-medium` is dominated.** It is slower than `thinking-medium`
  (44.37 s vs 31.16 s) *and* refuses far more (28.1 % vs 6.2 %). Nothing
  recommends it.

## Stage B — concurrency sweep, `thinking-none`

| Workers | rec/s | median | p95 | verified | projected |
|---|---|---|---|---|---|
| 4 | 0.038 | 30.91 s | 61.54 s | 21/32 | 32.39 h |
| 8 | 0.258 | 2.34 s | 61.40 s | 21/32 | 4.76 h |
| 12 | 0.905 | 2.88 s | 9.40 s | 21/32 | 1.36 h |
| 16 | **1.125** | 3.35 s | 9.83 s | 22/32 | **1.09 h** |

**The 4- and 8-worker cells are contaminated and must not be read as a
concurrency effect.** Lower concurrency cannot cause 10× higher per-call
latency. Those cells ran immediately after the thinking-heavy Stage A arms, and
they caught the endpoint still draining that queue — visible in their p95 of
~61 s against ~9.4 s for the later cells.

The evidence that this is timing and not behaviour is strong: **all four Stage B
cells verified 21–22 of 32 records with near-identical failure tallies**
(`ungrounded_prose` 36–38, `ungrounded_topic` 13, `out_of_bounds` 12–13). At
temperature 0 the model's output is highly reproducible; only wall-clock moved.

Taking only the two clean cells: **16 workers beats 12 (1.125 vs 0.905 rec/s).
There is no plateau at 12**, which is where the collector's own table plateaued.
That table does not describe this endpoint.

## The finding that matters most

**`ungrounded_prose` is the dominant failure in every single arm** — 36–38 of
~63 failures for `thinking-none`, 16 of 34 even for the best arm. This is the
0.45 prose-overlap floor rejecting the model's summary.

That is very likely a **validator design fault, not a model fault**. Conference
source text is deliberately thin — `cfp_text` is `""` on all 2,234 rows, so the
prompt carries title, acronym, series name and CCF area codes, roughly twenty
content words. Any fluent 2–3 sentence summary of twenty words will contain
words that are not among those twenty, and will score below 0.45 no matter how
faithful it is. The floor was inherited from the collector, where it guarded
summaries of **full fetched web pages** — a completely different denominator.

**Until that is fixed, every throughput number here understates achievable
coverage, and the arm comparison is partly a measurement of which arm best games
a mis-set threshold.**

## Answering the original question

The backfill is **~1–1.4 hours at 12–16 workers with thinking off**, not 5–6.
With thinking on it is ~12 h, and buys refusal down from 34 % to 6 %.

Neither is the right answer yet, because both are measured against a threshold
that is probably wrong for one of the two domains.

## AMENDMENTS

None yet.

## What this does not show

- **No per-domain breakdown.** The harness did not record failures by
  grant-vs-conference, which is exactly the split the `ungrounded_prose`
  hypothesis needs. Recorded in `ISSUES.md` as the first fix for any follow-up.
- **Nothing about retrieval quality.** Whether extracted text embeds *better*
  than raw text is a separate question and a separate experiment.
- **Single run, no seed replication.** Provider-side nondeterminism remains at
  temperature 0; no confidence intervals are claimed. The near-identical Stage B
  tallies suggest run-to-run variance in *verification outcome* is small, but
  that is an observation, not a measurement.
- **A shared endpoint.** Not isolated, and Stage B proves that matters.

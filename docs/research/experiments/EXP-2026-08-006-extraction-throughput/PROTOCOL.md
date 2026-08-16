# PROTOCOL — EXP-2026-08-006

Written **before** the run.

## Question

How long does the one-time structured-extraction backfill (~4,400 opportunity
records, plan D9/D10) actually take against **Mycelium's own LLM endpoint**, and
how does that change with reasoning effort and worker concurrency?

## Why this experiment exists

The plan currently carries an estimate of **5–6 hours**, extrapolated from a
throughput table in the standalone collector
(`/home/bdgr/Tools/Grant/pipeline.py:51-63`):

```
workers  1 → 0.05 rec/s   median latency 25s
workers  4 → 0.16 rec/s   median latency 24s
workers  8 → 0.21 rec/s   median latency 33s
workers 12 → 0.24 rec/s   median latency 49s   (flat)
```

That table is **not evidence about this system**. It was measured against a
different server (`http://localhost:9090/v1`, the collector's own
`MYCELIUM_LLM_*` config) with 13,000-character prompts and an unrecorded
reasoning setting. Mycelium's endpoint is a LiteLLM proxy on `localhost:4000`
(`host.docker.internal:4000` from inside a container) serving `skynet`, and
`.env` already sets `LLM_REASONING=none`.

Carrying a 5–6 hour figure into a plan on the strength of someone else's
hardware is exactly the "number that does not trace to an experiment" this
record exists to prevent.

## Hypothesis

Stated before the run: **the 25–49 s median latency is a property of the
collector's endpoint, not a floor.** Against this endpoint with reasoning off,
median latency will be substantially lower, and the 4,400-record backfill will
complete well inside an hour at 12 workers.

Directional expectations, recorded so they can be wrong:

1. Latency rises monotonically with reasoning effort (`none < low < medium`).
2. Throughput rises sub-linearly with concurrency and plateaus, because the
   endpoint — not the client — is the bottleneck.
3. **Higher reasoning may still win on wall-clock** if it produces schema-valid
   output on the first attempt more often. A cheap call that fails validation
   and triggers two repair attempts costs more than one good expensive call.

Point 3 is why the primary metric is *verified records per second*, not calls
per second.

## Design

**Corrected before running, after reading `apps/core/llm.py:211-222`.** Reasoning
is transmitted two different ways and the naïve `none/low/medium` factor is not
well defined:

```python
if style == ReasoningStyle.THINKING:
    return {"chat_template_kwargs": {"enable_thinking": enabled}}
return {"reasoning_effort": level.value}
```

Under `THINKING` — which is what `.env` sets (`LLM_REASONING_STYLE=thinking`) —
`low`, `medium` and `high` are **indistinguishable**: all three collapse to
`enable_thinking=True`. Only `EFFORT` style sends a graded level. So the factor
is the **(style, level) pair**, not the level alone.

**Stage A — arm comparison, concurrency fixed at 12** (the plan's number):

| Arm | style | level | Transmitted as |
|---|---|---|---|
| `thinking-off` | thinking | none | `enable_thinking: false` |
| `thinking-on` | thinking | medium | `enable_thinking: true` |
| `effort-low` | effort | low | `reasoning_effort: "low"` |
| `effort-medium` | effort | medium | `reasoning_effort: "medium"` |

**Stage B — concurrency sweep on Stage A's winner**: concurrency ∈ {4, 8, 12, 16}.
This is the range the plan actually has to choose from, and it is directly
comparable with the collector's own published table (which measured 1/4/8/12 and
found a plateau at 12 with p95 latency degrading past 8). 12 is **re-measured**
here rather than carried over from Stage A: the proxy is warm by then, so a
Stage-A number would not be comparable with its neighbours.

`n = 32` records per cell (16 grants + 16 conferences), the same 32 in every cell
so cells are paired. 32 divides evenly by 4, 8 and 16, so no cell is decided by a
ragged final batch. Eight cells, **256 records** plus repair attempts.

A further honesty note: whether the proxy's backend honours `reasoning_effort`
at all is unknown. If `effort-low` and `effort-medium` come back
indistinguishable, that is a finding about the endpoint, and is recorded as one
rather than smoothed over.

## Materials

Real records, not synthetic prompts — prompt length drives latency and the
synthetic version would understate it.

- **15 grants** sampled from `/home/bdgr/Tools/Grant/data/collect/opportunities.db`,
  stratified across the four sources that have rows (`grants_gov`, `nih_guide`,
  `nsf`, `eu_portal`) so the description-length spread is represented
  (measured means: nsf 11,411 chars, eu_portal 4,975, grants_gov 1,648,
  nih_guide 894).
- **15 conferences** sampled from
  `/home/bdgr/Tools/Grant/data/collect/conferences.db`. These are the thin case:
  `cfp_text` is `""` on all 2,234 rows, so the prompt carries title, acronym,
  series name and CCF area codes only.

The sample is drawn with a fixed seed and its `stable_key` / `instance_key` list
is written to `data/sample.json` so the run is reproducible.

## Procedure

1. Draw the sample (fixed seed), record the keys.
2. For each of the 9 cells, run the extraction against every sampled record
   through `apps.core.llm.build_llm_client`, using the Phase 8 structured-output
   contract and the same deterministic validators.
3. Record per call: wall-clock latency, attempt index, whether the reply parsed,
   whether it passed each validator, input/output token counts.
4. Between cells, no warm-up is discarded — the endpoint is shared and a warm
   cache is the realistic condition. Note it as a limitation.

## Metrics

**Primary:** `verified_records_per_second` — verified records ÷ wall-clock for
the cell. This is the only number that projects honestly to the backfill.

Secondary:
- `median_latency_s`, `p95_latency_s` per call
- `first_attempt_valid_rate` — fraction schema-valid without repair
- `mean_attempts_per_verified_record`
- `refusal_rate` — records exhausting all 3 attempts
- `input_tokens`, `output_tokens` totals
- `projected_backfill_hours` = 4,400 ÷ `verified_records_per_second` ÷ 3600

## What would refute the hypothesis

- Median latency at `reasoning=none`, concurrency 12 above ~15 s.
- Throughput at 24 workers no better than at 12 **and** projected backfill above
  2 hours.
- `first_attempt_valid_rate` below ~0.7 at `none`, which would mean the cheap
  setting is paid for in repair attempts.

Any of these and the 5–6 hour figure stands, or a middle reasoning level wins.

## Threats to validity

- **A shared endpoint.** Other work may hit `localhost:4000` concurrently;
  latency is not isolated. Recorded, not controlled for.
- **`n = 32` per cell** bounds precision. This sizes a plan, it does not
  establish a tight throughput law.
- **Single run**, no seed replication — provider-side nondeterminism remains at
  temperature 0. Reported as such; no confidence intervals claimed.
- **Warm proxy cache** may flatter later cells. Cell order is recorded.
- The result sizes *this* backfill on *this* endpoint. It does not transfer to a
  different model or a loaded server.

## Exclusions

Retrieval quality is **not** measured here. Whether extracted text embeds better
than raw text is a separate experiment; this one measures cost only.

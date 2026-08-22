# EXP-2026-08-012 — Protocol

**Pre-registered.** Written before any arm on `sci-2025-01` was scored. The only
prior evidence is `EXP-2026-08-011`, on a different snapshot.

## Question

`Q-024`. `EXP-2026-08-011` established the ladder's only surviving positive
findings — but all three rest on **one snapshot with click-derived judgments**:

- **C-008** — the union pool recovers recall the dense-restricted pool costs.
  (+0.0523 R@100 `[+0.0235, +0.0858]`, 28W/10L)
- **C-014** — SPLADE as a third RRF channel raises recall over two-channel fusion.
  (+0.0630 `[+0.0396, +0.0923]`, 39W/3L)
- **C-018** — two-channel fusion retrieves *less* than BM25 alone.
  (−0.0392 `[−0.0711, −0.0100]`, 14W/32L; exploratory, never pre-registered)

**Do all three replicate on `sci-2025-01` — 492 queries and human-assessed qrels?**

This matters more than a routine replication because `EXP-2026-08-009` already
watched an effect **flip sign** between these two snapshots: the cross-encoder was
null on 2026 and significantly harmful on 2025-01. That is precisely the failure
mode a single-snapshot result is exposed to, and these three are the only positive
results the whole programme has.

## Hypothesis

**Primary.** All three replicate: same sign, intervals excluding zero, per-query
records favouring the same side.

**Secondary, and this one I expect to be different in magnitude.** C-008's effect
should be **larger** here than on 2026, because it is a claim about what the
dense-restricted pool costs *when the dense channel is weak* — and the dense
channel is far weaker on this snapshot (`dense_only` 0.0931 nDCG@10 against
`bm25_only` 0.2486, where on 2026 the gap is 0.2401 against 0.3212).
`EXP-2026-08-002` already reported the un-intervalled recall gap as 8.7% on 2026
against 75–80% on the 2025 pair, so the direction of this prediction is not new —
what is new is putting an interval on it.

**Correspondingly, C-018 may be larger too**: if the dense channel is weak enough
to displace BM25's own findings on 2026, it should displace more of them here.

**Falsifier, stated now.** Any of the three showing an interval that includes
zero, or a reversed sign. If **C-008 or C-014** fails, the ladder's central
recommendation — widen the retrieval pool, add SPLADE — loses its evidential basis
and must be withdrawn exactly as the cross-encoder recommendation was. If
**C-018** fails, it was an artefact of one snapshot and should be cut rather than
carried as exploratory.

## Setup

No new ranking logic and no new arms. The same production code, the same frozen
`sci-2025-01` subset built in `EXP-2026-08-009` (261,294 ids, committed), the same
`harness.stats` bootstrap that produced every interval since `EXP-2026-08-009`.

Two one-time encodes are required and are the entire cost: this snapshot has no
cached bge-small matrix to row-slice from and no SPLADE matrix at all. They are
run **one at a time** — `EXP-2026-08-008` ISSUES §5 measured that two concurrent
ONNX sessions are catastrophically slower than serial.

`bm25_only` on this snapshot is already measured (`EXP-2026-08-009`, nDCG@10
0.2486, R@100 0.5972) and reproduced its recorded value at the time.

## Data

**LongEval-Sci**, `longeval-sci/2025-01`, **`test` qrels — released CLEF-2025
human assessments, not click-derived**. 492 queries. Pooled scope at depth 1000,
261,294 documents.

The judgment difference from `EXP-2026-08-011` is a feature here, not a
confound to apologise for: if these claims hold under both click-derived and
assessed judgments, they are considerably more robust than either alone. But it
does mean a *failure* to replicate is ambiguous between snapshot and judgment
provenance, and must be reported that way.

## Metrics

- **R@100 — primary.** The quantity all three claims are about.
- **nDCG@100** secondary — recall that never surfaces is worth little.
- **nDCG@10** reported, expected null throughout; `EXP-2026-08-009` found nothing
  beats BM25 there.
- **Paired bootstrap 95% CI**, 10,000 resamples, fixed seed, plus win/loss/tie and
  a two-sided sign test.

**Scope, restated:** `pooled` is a re-ranking evaluation. R@100 is recall *within
the pooled subset* and supports a claim about the relative ordering of pool
constructions, never about a production corpus. `Q-001` is untouched.

## Baselines

`fusion_dense_pool` (production behaviour) for C-008; `fusion_union_pool` for
C-014; `bm25_only` for C-018. All re-scored here rather than quoted.

## Procedure

```bash
# Phase 1 — dense encode (~2 h) then the two-channel arms. Answers C-008 and C-018.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2025-01 \
    --config eval/configs/dense_only.toml eval/configs/fusion_dense_pool.toml \
             eval/configs/fusion_union_pool.toml

# Phase 2 — SPLADE encode (~3 h) then the three-channel arm. Answers C-014.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/encode_ladder.py --model splade --collection sci-2025-01
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2025-01 \
    --config eval/configs/fusion_bm25_dense_splade.toml

# Phase 3 — intervals.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python docs/research/experiments/EXP-2026-08-012-*/code/replicate.py
```

No LLM is called anywhere in this experiment.

## What would falsify this

- **C-008 fails** if `fusion_union_pool` − `fusion_dense_pool` on R@100 includes
  zero or reverses.
- **C-014 fails** if `fusion_bm25_dense_splade` − `fusion_union_pool` on R@100
  includes zero or reverses.
- **C-018 fails** if `fusion_union_pool` − `bm25_only` on R@100 includes zero or
  reverses.
- **`bm25_only` failing to reproduce 0.5972** invalidates the experiment rather
  than any claim.

**Decision rule, fixed now.** A claim is upgraded from "supported on one snapshot"
to "supported on two" only if the interval excludes zero **and** the per-query
record favours the treatment on *this* snapshot too — the same rule applied in
`EXP-2026-08-011`, and the same rule that refuted C-013 and C-017. A replication
that holds on the mean but loses the per-query record is a weaker result and will
be reported as one, not rounded up.

**What this still cannot settle.** LongEval is `query → documents`; Mycelium is
`declared-interest profile → feed`. Two snapshots of the wrong task are still the
wrong task. `Q-001` remains the gate on any production change.

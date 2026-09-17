# EXP-2026-09-004 — Protocol

**Written before any arm ran.** At the time of writing the corpus was still
downloading, the two arms existed and passed their offline plumbing tests, and
no TypeSafe call had been made against LongEval-Sci from this repository.

## Question

Does a calibrated pointwise relevance probability from a non-generative decision
model (TypeSafe Jev), reranking BM25's top 20, order a scholarly feed better than
BM25 alone — with a paired confidence interval — and does it escape the specific
failure that refuted pointwise LLM scoring (C-016)?

## Hypothesis

**Primary `[PRE]`.** `typesafe_noul` over `bm25_only` (window 20) beats
`bm25_only` on nDCG@10 on `sci-2026-train` (100 queries, `dctr` qrels) with a
95 % paired bootstrap interval excluding zero. **Falsifier:** the interval
includes zero, or the point estimate is negative. Prior: honestly uncertain.
Every reranker tried on this collection has lost or tied (C-013 refuted, C-015
and C-016 against the LLM), and the losses concentrate on one- and two-word
queries where a model has almost nothing to read. Jev is not MS MARCO-trained,
which is the one untested explanation the record has left standing (Q-021,
Q-023), so this is the experiment that either settles or removes it.

**Secondary `[PRE]`.** On the same 20-candidate windows, `typesafe_score`
yields **more than 5 distinct values per query on average** (the LLM rubric:
1.99) **and** its mean value is **monotonic in judged grade** (the LLM rubric
ordered grade 2 below grade 1). Falsifier: either fails. This is the C-016
mechanism re-tested like for like: same base, same window, same four rubric
descriptions, a continuous value instead of an emitted integer.

**Tertiary `[PRE]`.** `typesafe_noul` and `typesafe_score` produce the same
top-10 for a query at least 80 % of the time (Jaccard ≥ 0.8 on average). Two
framings of one question should agree; if they do not, the answer depends on the
question's wording, and that is a finding about the model.

**Determinism, before anything else.** 20 pairs asked three times; report the
maximum absolute difference in `noul`. Bar 0.01, falsifier 0.05 (as in
`EXP-2026-09-003`, which measured 0.03). Above 0.05 every metric is reported as
mean ± std over three arm runs and the manifest says so.

**Replication rule.** Only if the primary holds does `sci-2025-01` (492
queries, human-assessed qrels, a second ~1.2 M-document download) run. The
record has twice been burned by n = 100 margins (Q-011, Q-013, C-013).

## Setup

- Model `jev-1.13.0`, pinned; the arm refuses an alias.
- Arms: `typesafe_noul` and `typesafe_score` in `eval/harness/typesafe_rerank.py`,
  pointwise, one call per (query, document) pair, concurrency 12. State is the
  query and the candidate's title plus 600 characters of abstract, the same
  truncation `llm_rubric` used. No listwise arm (C-015).
- Base `bm25_only`, pooled scope at pool depth 1000, the frozen id list
  `eval/subsets/sci-2026-train__pooled_d1000.txt`. Stacking on BM25 follows
  `EXP-2026-08-009`: rerank the strongest first stage, not the fusion pool.
  Needs no vectors, which is why it is first on this host.
- Optional contrast, if the pooled dense matrix is encoded on this host:
  `typesafe_noul` over `fusion_union_pool`, the same base `llm_rubric` used.
- Failures keep the pair at the bottom of the window and are counted; a run
  with more than 10 % failed pairs is recorded as failed, not analysed.

## Data

LongEval-Sci (CLEF), `longeval-sci-2026/snapshot-1/train`, 869,902 documents,
100 queries, pooled scope (84,489 documents on the recorded rows). Qrels `dctr`:
click-model-derived pseudo-relevance, **not human assessment**, and every number
says so. Public data; nothing from any Mycelium account is sent.

## Metrics

- nDCG@10 per query via `ir_measures`, paired mean difference with a 95 %
  percentile bootstrap over query ids (10,000 resamples, seed 20260821, the
  `harness.stats` implementation every prior experiment used), win/loss/tie
  counts and a two-sided sign test. **Primary contrast:** `typesafe_noul over
  bm25` − `bm25_only`.
- Also nDCG@100, AP, R@100, P@10 as the harness records them, and the
  query-length stratification from `EXP-2026-08-009`.
- Discrimination: distinct values per query in the 20-window, mean value by
  judged grade, share of within-window ordering decided by the model versus the
  base tiebreak — the `llm_diagnosis.py` measurements, read from the arms' dump
  files.
- Agreement between the two arms: mean top-10 Jaccard.
- Determinism as above. Cost and latency from the dump files' token totals at
  the list price on the run date and the harness's wall clock.

## Baselines

`bm25_only` (pooled) on this host — re-run here rather than read from the
committed results, because this is a different machine and the paired analysis
needs both arms' per-query scores from the same corpus build. The committed
`llm_rubric` and `xenc_rerank` numbers from `EXP-2026-08-008/009` are quoted for
context only, not paired against.

## Procedure

```bash
export IR_DATASETS_HOME=$PWD/data/eval-cache/ir_datasets MYCELIUM_EVAL_CACHE=$PWD/data/eval-cache/embeddings
# 1. Corpus + BM25 baseline (no vectors)
uv run --project eval eval/run.py --config eval/configs/bm25_only_pooled.toml --collection sci-2026-train
# 2. Determinism check, 20 pairs x 3
uv run --project eval python docs/research/experiments/EXP-2026-09-004-typesafe-pointwise-rerank-longeval/code/determinism.py
# 3. The two arms
uv run --project eval eval/run.py --config eval/configs/typesafe_noul_bm25.toml eval/configs/typesafe_score_bm25.toml --collection sci-2026-train
# 4. Paired intervals + discrimination, from run files and dumps only
uv run --project eval python docs/research/experiments/EXP-2026-09-004-typesafe-pointwise-rerank-longeval/code/paired.py
uv run --project eval python docs/research/experiments/EXP-2026-09-004-typesafe-pointwise-rerank-longeval/code/discrimination.py
```

## What would falsify this

Primary: the interval spans zero or the mean is negative. Secondary: five or
fewer distinct values per query, or a non-monotonic mean by grade. Tertiary:
mean top-10 Jaccard below 0.8. Determinism: any repeated pair moving more than
0.05. A failed-pair rate above 10 % voids the run.

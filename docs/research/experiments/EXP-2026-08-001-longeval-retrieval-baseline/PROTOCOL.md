# EXP-2026-08-001 — Protocol

> **Back-filled.** This protocol was reconstructed on 2026-08-06 from
> `eval/README.md`, `eval/collections.toml`, the harness source, and the
> committed run files. The experiment itself was designed and run on 2026-08-04
> to 2026-08-05, before this record existed. It was *not* pre-registered in this
> form. The question, hypothesis, and falsification criterion below are recovered
> from the research audit's W2 description, which predates the runs — so they are
> genuinely prior, but the wording is not.

## Question

Run unchanged production retrieval, lexical, and fusion code against an external
scholarly collection with judgments: does hybrid RRF fusion order results better
than dense retrieval alone, and does it beat a strong BM25 baseline?

## Hypothesis

RRF fusion over a dense-retrieved pool beats dense retrieval alone and is
competitive with BM25. **Falsifier, stated in advance:** BM25 alone outranking
every fusion arm on nDCG@10.

## Setup

The arms call production code directly. `eval/harness/arms.py` contains no
ranking logic of its own — it imports `apps.content.lexical`,
`apps.content.fusion`, `apps.content.ranking`, and `apps.content.pipeline._build_pool`.
The seam is `apps.content.protocols.VectorIndex`: production passes
`PgVectorIndex`, the harness passes `NumpyIndex`.

This substitution is exact, not an approximation, because production has **no ANN
index** — every pgvector query is an exact sequential scan — so the in-memory
index computes an identical ranking. (See `DECISIONS.md` D-005: if an approximate
index is ever enabled in production, this protocol breaks.)

Embedder: `BAAI/bge-small-en-v1.5`, 384 dimensions, the production model. Fusion:
RRF with k=60, plus the softened CombMNZ the production stack layers on top.

### Arms

| Arm | What it measures |
|---|---|
| `bm25_only` | The lexical channel alone — the baseline that matters |
| `dense_only` | The vector channel alone |
| `fusion_dense_pool` | **The deployed configuration.** RRF over a pool built by dense retrieval, with BM25 rescoring only what dense already found |
| `fusion_full` | `fusion_dense_pool` plus the production CombMNZ layer |
| `fusion_union_pool` | RRF over the union of dense and lexical pools — what the stack would do if the lexical channel could contribute documents |

### Corpus scopes

`full` ranks the entire snapshot. `pooled` ranks the union of judged documents
with a deep corpus-wide BM25 pool — a standard reduction, but a **re-ranking**
evaluation. The two are never compared: see `DECISIONS.md` D-003.

## Data

LongEval-Sci (CLEF), three snapshots. Card:
[`../../datasets/cards/longeval-sci.md`](../../datasets/cards/longeval-sci.md).

| Snapshot | Documents | Queries | Judgments |
|---|---:|---:|---|
| `longeval-sci-2026/snapshot-1/train` | 869,902 | 100 | `dctr` — 8,772 |
| `longeval-sci/2024-11` | 2,014,265 | 99 | `test` |
| `longeval-sci/2025-01` | 1,213,728 | 492 | `test` |

**The judgments are click-model-derived pseudo-relevance, not human assessment.**
The qrels variant is recorded on every row and must appear next to every number
(D-002). Confidence is sized to this, not to the sample count.

The 2025 pair is included because it is the only temporal pair with released
judgments — the persistence question is why LongEval was chosen at all (D-001).

## Metrics

Computed by `ir_measures`, never hand-rolled.

| Metric | Definition | Role |
|---|---|---|
| **nDCG@10** | Normalized discounted cumulative gain at rank 10 | **Primary.** The product shows a short daily feed, so top-of-ranking quality is what a user experiences |
| R@100 | Recall at 100 | **Primary recall metric.** The stack's sharpest suspected weakness is a recall failure, invisible to any @10 measure (D-004) |
| nDCG@100, AP, RR, P@10 | Standard | Reported for comparability; not used to decide anything |

Metric choice was fixed before the runs and is recorded in D-004. A metric chosen
after seeing results does not survive review.

## Baselines

1. **`bm25_only`** — the internal lexical arm. The comparison that decides
   whether fusion earns its cost.
2. **BM25 (PyTerrier, LongEval'26 organizers)** — the organizers' own published
   run, **re-scored by this harness with the same `ir_measures` call**, not a
   number quoted from a paper. This is what makes the comparison a check on our
   implementation rather than an appeal to authority.
3. **Qwen3-Embedding-4B (organizers)** — a 4B-parameter dense retriever, so the
   dense channel's performance can be read as a property of the task rather than
   only of a 384-dimension model.

## Procedure

```bash
# Every arm on the 2026 training snapshot
uv run --project eval eval/run.py --all --collection sci-2026-train

# The 2025 persistence pair
uv run --project eval eval/run.py --all --collection sci-2025-11
uv run --project eval eval/run.py --all --collection sci-2025-01

# Score the organizers' published runs with the same scoring call
uv run --project eval eval/score_run.py

# Regenerate this record from the run files
python data/build_metrics.py && python figures/make_figures.py
```

## What would falsify this

BM25 alone outranking every fusion arm on nDCG@10 across snapshots. That result
would mean the retrieval layer has no defensible claim as built, and the project
should reallocate to the funding and routing halves.

**This is what happened.** See `RESULTS.md`.

# EXP-2026-08-002 — Protocol

> **Back-filled**, and honestly: this ablation was not designed in advance. The
> arms existed because `fusion_union_pool` was built as a comparison arm for
> `EXP-2026-08-001`, and the recall gap was noticed in those results. The
> question below is therefore **post-hoc** — see "Threats to validity" in
> `RESULTS.md`. It is recorded as its own experiment because it answers a
> different question from EXP-001 and supports a different claim (C-008), not
> because it was separately run.

## Question

The deployed pipeline builds its candidate pool with dense retrieval and then
runs BM25 over that pool. What does that construction cost in recall, compared
with pooling dense and lexical retrieval together?

## Hypothesis

A union pool retrieves documents the dense channel misses, so R@100 rises, and
the gain is larger where the dense channel is weaker on that corpus.

## Setup

Identical to [`EXP-2026-08-001`](../EXP-2026-08-001-longeval-retrieval-baseline/PROTOCOL.md).
Same production code, same embedder, same fusion, same collections. The only
variable is pool construction:

| Arm | Pool |
|---|---|
| `fusion_dense_pool` | **Deployed.** Dense retrieval builds the pool; BM25 rescores it. The lexical channel can reorder a document but can never add one. |
| `fusion_union_pool` | Dense and lexical retrieval each contribute to the pool; fusion runs over the union. |

Both are run at pool width 100 (the deployed width) and 1000, so the comparison
separates *widening* the pool from *deepening* it.

## Data

The same three LongEval-Sci snapshots, **pooled corpus scope only**. Card:
[`../../datasets/cards/longeval-sci.md`](../../datasets/cards/longeval-sci.md).

Pooled scope is used because it is the only scope with both arms at both pool
widths across all three snapshots. Nothing here is compared against a
full-corpus number (D-003).

## Metrics

| Metric | Role |
|---|---|
| **R@100 relative gain, union over dense** | **Primary.** The question is a recall question; a top-10 metric cannot see it |
| nDCG@100, AP | Secondary — does the extra recall land usefully, or just deeper |
| nDCG@10 | Reported to confirm the change is not bought at the top of the ranking |

The comparison is **paired**: same snapshot, same pool width, same corpus scope,
same queries. Only pool construction differs.

## Baseline

`fusion_dense_pool` — the deployed configuration. This is an ablation against
what production actually does, not against an external system.

## Procedure

```bash
# The runs (shared with EXP-2026-08-001)
uv run --project eval eval/run.py --all --collection sci-2026-train
uv run --project eval eval/run.py --all --collection sci-2025-11
uv run --project eval eval/run.py --all --collection sci-2025-01

# This folder
python data/build_metrics.py && python figures/make_figures.py
```

## What would falsify this

A union pool showing no R@100 gain, or a gain bought at a material nDCG@10 cost.
Either would mean the dense-pool restriction is not the recall bottleneck and the
architectural criticism is wrong.

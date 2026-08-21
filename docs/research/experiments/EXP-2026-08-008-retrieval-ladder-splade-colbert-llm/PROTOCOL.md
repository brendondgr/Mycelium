# EXP-2026-08-008 — Protocol

**Pre-registration status, stated honestly up front.** This protocol was written
part-way through the run, not before it. At the moment of writing, the baseline
reproduction, the three LLM arms, and the cross-encoder arms at depths 50 and 100
had already been scored; the SPLADE arms, the ColBERT arms, the cascade, and the
cross-encoder at depths 250 and 1000 had **not**. Predictions below are marked
`[POST]` where the number was already visible and `[PRE]` where it was not. See
ISSUES.md §1. A protocol written after a result is not a protocol, and labelling
which half is which is the only thing that keeps the rest of it worth reading.

## Question

Does adding a learned-sparse retrieval channel (SPLADE), a late-interaction
reranker (ColBERT), a cross-encoder reranker, or an LLM reranker to the deployed
BM25 + dense + RRF stack improve ranking quality on LongEval-Sci — and does any
of them beat BM25 alone, which `EXP-2026-08-001` established that nothing in the
deployed stack does?

## Hypothesis

`[PRE]` **SPLADE.** Learned sparse retrieval beats BM25 on nDCG@10, because it
performs automatic corpus-aware query expansion — the job the hand-authored
keyword clusters do manually in production. Stated falsifier: SPLADE loses to
BM25. There is a specific reason to expect it might, and it is written down
before the run: SPLADE++ is trained on MS MARCO web queries, this collection is
scientific titles and abstracts, and `EXP-2026-08-001` already showed a
4B-parameter dense model losing to BM25 here. Sparse neural retrievers are known
to generalize worse than BM25 off their training distribution.

`[PRE]` **ColBERT.** Late-interaction reranking beats the fusion base it reranks,
because MaxSim aligns query tokens to document tokens and can therefore reward a
document that matches in meaning without sharing vocabulary — the failure mode a
single averaged vector cannot see. No prior on whether it beats BM25.

`[PRE]` **Rerank depth.** Effectiveness rises with rerank depth and saturates;
the interesting output is where. No prior on the location.

`[POST]` **Cross-encoder.** Expected to be the strongest reranker per unit of
compute, since it reads query and document jointly.

`[POST]` **LLM listwise.** Expected to inherit the input ordering as a prior it
cannot escape, so that reversing the candidate order degrades the result. The
pointwise rubric, having no order to be biased by, was expected to be more stable
but not necessarily better.

## Setup

Every arm runs over one **frozen document set** and differs from its baseline by
exactly one stage. The system under test is `apps.content`'s retrieval, lexical,
and fusion code at the recorded commit for the baseline arms; the ladder arms
(`eval/harness/ladder.py`, `eval/harness/llm_rerank.py`) are **candidate code that
is not in production** and are labelled as such — see `eval/harness/ladder.py`'s
module docstring.

Held fixed across every arm: the document set (84,489 ids, frozen to
`eval/subsets/sci-2026-train__pooled_d1000.txt`), the dense embedder
(`BAAI/bge-small-en-v1.5`, 384-dim), RRF `k = 60`, `pool_per_interest = 100`, and
the query set. LLM arms pin `temperature = 0`.

Hardware: 32 CPU cores, 121 GB RAM, **no CUDA device**. Every neural model runs
as ONNX on CPU. This is a constraint on model choice, not a preference:
ColBERT-small (33M) is used rather than ColBERTv2 (110M) for that reason.

## Data

**LongEval-Sci (CLEF)**, snapshot `longeval-sci-2026/snapshot-1/train`,
`train` split, 869,902 documents and 100 queries.

**Corpus scope is `pooled`**, not `full`: the 84,489-document union of every
judged document with a corpus-wide BM25 pool at depth 1000. This is a
**re-ranking evaluation**. Reordering metrics are broadly comparable to
full-corpus; **recall metrics are not and must never be reported as such.** The
subset is byte-identical to the one the existing leaderboard rows were scored on,
which is verified rather than assumed — see Procedure step 2.

**Judgments are `dctr`: click-model–derived pseudo-relevance, not human
assessment.** 8,630 distinct judged documents. This must be restated next to
every number this experiment produces.

## Metrics

- **nDCG@10 — primary.** Normalized discounted cumulative gain at rank 10:
  relevance summed with a logarithmic rank discount, divided by the best possible
  ordering's score. It is primary because every arm on this ladder is a
  *reordering* intervention evaluated at the depth a reader actually sees.
- **nDCG@100, AP, RR, P@10** — secondary, reported for every arm.
- **R@100** — recall of judged documents at rank 100. Reported, but **only** as a
  within-scope diagnostic: it separates "the right document never entered the
  pool" from "the pool was fine and the ordering was wrong". It cannot be quoted
  as a recall claim about the production corpus.

A rerank arm cannot change R@100 when its depth is at or below 100; an unchanged
R@100 across such arms is a correctness check, not a finding.

## Baselines

Three, deliberately:

1. **`bm25_only`** — the arm that beat everything in `EXP-2026-08-001`. The bar.
2. **`fusion_union_pool`** — the strongest deployed-shape fusion arm, and the base
   ranking every rerank arm consumes. Isolates what the added stage contributes.
3. **`fusion_dense_pool`** — production behaviour, carried so the ladder is always
   readable against what actually ships.

All three are re-scored on the frozen subset in this experiment rather than
quoted from the leaderboard.

## Procedure

```bash
# 1. Freeze the document set and slice its embedding matrix out of the cached
#    full-corpus one. ~6 min, once, ever. No re-embedding at any later step.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/freeze_subset.py --collection sci-2026-train --depth 1000

# 2. Reproduce the recorded baselines on the frozen subset. This is the gate:
#    if these do not match the leaderboard exactly, the subset or the matrix
#    slice is wrong and nothing below is trustworthy.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2026-train \
    --config eval/configs/bm25_only_pooled.toml eval/configs/dense_only.toml \
             eval/configs/fusion_dense_pool.toml eval/configs/fusion_union_pool.toml \
             eval/configs/fusion_full.toml

# 3. Encode the ladder models. One at a time — two concurrent ONNX sessions
#    oversubscribe the host badly (measured: 20 min for a shard projected at 3).
#    Resumable by shard; cached content-addressed; never repeated.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/encode_ladder.py --model splade
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/encode_ladder.py --model colbert

# 4. The retrieval and rerank rungs.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2026-train \
    --config eval/configs/splade_only.toml eval/configs/fusion_bm25_dense_splade.toml \
             eval/configs/colbert_rerank_d*.toml eval/configs/xenc_rerank_d*.toml \
             eval/configs/cascade_colbert_xenc.toml eval/configs/xenc_rerank_splade_base.toml

# 5. The LLM rung. Needs a reachable OpenAI-compatible endpoint.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
LLM_BASE_URL=http://localhost:4000/v1 LLM_MODEL=skynet \
  uv run --project eval python eval/run.py --collection sci-2026-train \
    --config eval/configs/llm_rerank.toml eval/configs/llm_rerank_reversed.toml \
             eval/configs/llm_rubric.toml
```

## What would falsify this

Written so it cannot be renegotiated once the numbers are in.

- **SPLADE's hypothesis is falsified** if `splade_only` scores below `bm25_only`
  on nDCG@10. If that happens, the finding is that learned sparse retrieval does
  not transfer to this collection, and no amount of fusing it in rescues the
  claim that it is the automated replacement for keyword clusters.
- **ColBERT's hypothesis is falsified** if `colbert_rerank` at its best depth does
  not exceed `fusion_union_pool` on nDCG@10.
- **The depth hypothesis is falsified** if effectiveness is flat in depth, or
  decreases — either would mean reranking deeper buys nothing and the deployed
  surfacing cut is not the constraint it is assumed to be.
- **A rerank arm whose R@100 differs from its base at depth ≤ 100 is a bug**, not
  a result, and invalidates that arm until explained.

**Decision rule, and its known weakness.** No arm is proposed for production on
this evidence alone. The collection is `query → documents`; Mycelium is
`declared-interest profile → feed`, and `docs/evaluation.md`'s claims boundary
applies unchanged. Separately, n = 100 queries is low power: `Q-011` and `Q-013`
both exist because this record has twice failed to distinguish "no effect" from
"an effect too small to resolve". Any difference below roughly 0.01 nDCG@10 here
should be read as unresolved unless a paired interval says otherwise.

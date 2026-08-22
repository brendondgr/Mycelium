# EXP-2026-08-010 — Protocol

**Pre-registered.** Written after the query expansions were generated and
inspected, and **before any rerank arm was run**. No arm's score has been seen.

## Question

`EXP-2026-08-009` refuted C-013 and located the damage precisely: the
cross-encoder's harm concentrates on short keyword queries (1 word −0.053,
2 words −0.051, 3–4 words −0.108) and **vanishes at five words or more**
(+0.0009). Two explanations fit that: the reranker genuinely needs more text to
read, or short queries simply co-occur with something else that breaks it.

If the first is right, the fix is cheap and does not require giving up BM25:
retrieve with the short query, then hand the *reranker* a natural-prose
description of what that query is looking for. So:

**Does giving the cross-encoder an LLM-written prose form of the query — while
BM25 still retrieves with the original short string — recover the loss, and does
recovery scale with the length of that prose?**

## Hypothesis

**Primary.** Effectiveness rises monotonically with expansion length. At ~8 words
the arm is still below `bm25_only`; by ~20–40 words the deficit closes to within
noise or turns positive. Concretely: Δ nDCG@10 against `bm25_only` improves as
target length grows, and the ~40-word arm's 95% paired interval either excludes
zero on the positive side or includes zero (i.e. the harm is gone).

**Falsifier, stated now.** The ~40-word arm remains significantly *below*
`bm25_only`, or the trend across lengths is flat or non-monotonic. Either result
says query length was **not** the mechanism, and the short-query stratification in
`EXP-2026-08-009` was a correlate rather than a cause.

**Secondary, and I am genuinely unsure.** Expansion may help the queries that
were hurt (1–4 words) while *harming* the ones that were fine (5+ words), because
those already give the reranker enough to read and prose can only add drift. The
per-length-bucket breakdown is therefore part of the primary output, not a
footnote.

**A specific worry recorded in advance.** Ambiguous one-word queries cannot be
expanded faithfully. The generated prose for `operation` hedges across
"mathematical function, surgical procedure, functional process" — three unrelated
fields. If expansion helps overall but hurts the 1-word bucket, that is the likely
reason, and it would mean the technique needs an ambiguity guard rather than more
words.

## Setup

One change per arm. Every arm:

- retrieves with `bm25_only` over the **original short query** — unchanged, so
  BM25 keeps the rare-term exact match `EXP-2026-08-009` showed it is best at;
- reranks the top 50 with `Xenova/ms-marco-MiniLM-L-6-v2`;
- differs **only** in the text handed to the cross-encoder.

Arms: original query (already run, `EXP-2026-08-009`), then ~8, ~16, ~20, ~40
words of prose.

**The expansion sees the query string and nothing else** — no documents, no
candidates, no judgments — so relevance cannot leak into the arm. Generated once
at temperature 0 and cached in full at
`data/eval-cache/expansions/`, so what the model wrote can be read rather than
assumed. All 492 queries expanded cleanly at every length (0 failures; medians 8,
15, 19, 38 words against targets 8, 16, 20, 40).

## Data

**LongEval-Sci**, `longeval-sci/2025-01`, `test` qrels, **492 queries**, pooled
scope at depth 1000 (261,294 documents, the frozen id list from
`EXP-2026-08-009`). This snapshot is chosen because it is where the harm was
measured and where the query set is large enough to resolve it.

Judgments are the released CLEF-2025 `test` qrels — human-assessed, not the
click-derived `dctr` used on the 2026 snapshot.

## Metrics

- **nDCG@10 — primary.**
- **Paired bootstrap 95% CI** on the per-query difference against `bm25_only`,
  10,000 resamples, fixed seed — the same machinery as `EXP-2026-08-009`.
- **Win/loss/tie and a two-sided sign test**, because a mean can be carried by a
  few queries.
- **Δ split by original query length** (1, 2, 3–4, 5+ words), which is the
  breakdown the hypothesis is actually about.
- R@100 is reported but is **necessarily unchanged** — reranking the top 50 of a
  fixed retrieval cannot alter what was retrieved. A change there is a bug.

## Baselines

- `bm25_only` on this snapshot: nDCG@10 0.2486 — the bar.
- `xenc over bm25 d50` with the raw query: 0.2047 — the damage to be recovered.

Both already measured in `EXP-2026-08-009` on the identical frozen subset.

## Procedure

```bash
LLM_BASE_URL=http://localhost:4000/v1 LLM_MODEL=skynet \
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/expand_queries.py \
    --collection sci-2025-01 --words 8 16 20 40

IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2025-01 \
    --config eval/configs/xenc_bm25base_expand{8,16,20,40}w_d50.toml

IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python \
    docs/research/experiments/EXP-2026-08-010-*/code/analyse.py
```

## What would falsify this

- **The primary hypothesis is falsified** if the ~40-word arm's interval still
  excludes zero on the negative side, or if Δ does not improve with length.
- **A trend that improves but never reaches parity** falsifies the *practical*
  claim while supporting the mechanism: it would mean length is real but
  insufficient, and the recommendation stays "do not adopt".
- **R@100 differing from `bm25_only`** in any arm is a bug and invalidates it.

**Decision rule, fixed now.** This technique is worth pursuing only if some
expansion length reaches Δ ≥ 0 against `bm25_only` with an interval that does not
exclude zero on the negative side — i.e. at minimum, the harm is gone. Recovering
from −0.044 to −0.020 is a real finding about the mechanism and still not a reason
to ship anything.

**What this cannot settle.** One reranker, one snapshot, one expansion prompt, one
LLM. And LongEval is `query → documents` while Mycelium is
`declared-interest profile → feed`; `Q-001` is untouched. If this works, the
natural follow-up is whether the same trick helps a *declared interest*, which is
the two-word case this product actually has.

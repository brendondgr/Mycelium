# Evaluation

Mycelium's ranking stack measured against an external collection with published
baselines. The harness lives in [`eval/`](../eval/README.md); re-running is one
command:

```bash
uv run --project eval eval/run.py --config eval/configs/fusion_dense_pool.toml --collection sci-2026-train
```

The table below is **generated** from `eval/results/*.json` by
`uv run --project eval eval/report.py`. Never edit it by hand — a number that has
drifted from the run that produced it is worse than no number.

## Results

<!-- BEGIN GENERATED LEADERBOARD -->

_No runs recorded yet._

<!-- END GENERATED LEADERBOARD -->

## How to read these numbers

**The collection.** LongEval-Sci (CLEF). Documents are paper titles + abstracts;
queries are short keyword topics. `sci-2026-train` is the 2026 training snapshot
(869,902 documents, 100 queries); `sci-2025-11` and `sci-2025-01` are the released
2025 test snapshots and form the temporal-persistence pair.

**The qrels.** Recorded on every row, and it matters: LongEval-Sci ships
click-model–derived pseudo-relevance judgments (`dctr`), not TREC-grade human
assessment. Report the qrel provenance next to every number, and size your
confidence to it.

**Corpus scope.** `full` ranks the entire snapshot. `pooled` ranks the union of
the judged documents with a deep corpus-wide BM25 pool — a standard, defensible
reduction, but a **re-ranking** evaluation. Recall numbers from a pooled run do
not transfer to the full corpus, and the two scopes must never be compared.

**Dirty runs.** A ⚠️ means the working tree had uncommitted changes, so the
number is not reproducible from the recorded SHA. Treat it as indicative only.

## Temporal persistence, and what is currently blocked

Persistence — whether effectiveness decays as a corpus grows — is the reason for
choosing LongEval over a static collection, and it is the question most specific
to Mycelium: the production corpus grows daily and nobody has ever checked
whether relevance degrades as it does.

The 2025 pair (`sci-2025-11` → `sci-2025-01`) answers it today. The three 2026
*test* snapshots cannot: CLEF 2026 is an active shared task and the organizers
withhold those qrels until it closes. This is a **temporary data-availability
block, not a design limitation** — `eval/collections.toml` already declares the
snapshots, and enabling them is a config edit (flip `scoreable`, name the qrels
variants), never a code change. Run files for them can already be produced for a
TIRA submission; only scoring is unavailable.

## What this does and does not license you to claim

Keep this section next to the numbers. The temptation to overclaim from a first
number is exactly how the "multi-agent" overstatement happened in the first
place (see the `CORRECTED` entry `20260804-briefing-framing`).

**You may claim:**

- Whether this repository's BM25 implementation is correct, by comparison with a
  published BM25 baseline on the same snapshot and qrels.
- Whether RRF fusion over a dense-retrieved pool beats BM25 alone, and by how
  much, on an external collection.
- What the dense-pool restriction costs relative to a true union pool — the
  `fusion_dense_pool` vs `fusion_union_pool` gap. This is the audit's sharpest
  structural criticism turned into a measured number: today BM25 indexes only
  what dense retrieval already found, so the lexical channel can never *add* a
  document, only reorder one.
- Whether effectiveness persists across the 2025 snapshot pair.

**You may not claim:**

- That this validates Mycelium's actual task. LongEval evaluates
  **query → documents**. Mycelium does **declared-interest profile → feed**. The
  granularity mismatch between a three-word interest and a 200-word abstract —
  one of the core difficulties of the real problem — is *not* tested here.
- Anything about cluster max-pooling, the LLM percent-match, fellowship
  eligibility, or member routing (audit claims C3–C6). None are exercised.
- Anything about grants, fellowships, or conferences. LongEval is papers only.
- Certainty proportional to the qrels. These are click-derived pseudo-relevance
  judgments, not human assessment.

The honest framing: **this measures whether the foundation is sound, not whether
the idea is right.** That is worth the effort, because everything downstream
silently inherits whatever is wrong at this layer.

## The re-run rule

Any change to `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, or
`pipeline.py`'s pool construction must be accompanied by a fresh evaluation run,
with the before/after numbers in the changelog entry. The harness exists so that
this costs one command; see `docs/skills/global.md`.

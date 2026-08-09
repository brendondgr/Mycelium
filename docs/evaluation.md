# Evaluation

How to run the harness, how to read what it produces, and what the numbers do and
do not license you to claim. The harness lives in [`eval/`](../eval/README.md);
re-running is one command:

```bash
uv run --project eval eval/run.py --config eval/configs/fusion_dense_pool.toml --collection sci-2026-train
```

> **The findings live in the research record.** These runs are recorded as
> [`EXP-2026-08-001`](research/experiments/EXP-2026-08-001-longeval-retrieval-baseline/RESULTS.md)
> (does the stack beat BM25?) and
> [`EXP-2026-08-002`](research/experiments/EXP-2026-08-002-dense-pool-vs-union-pool/RESULTS.md)
> (what does the dense-pool restriction cost?). Read those for the hypothesis,
> the interpretation, the threats to validity, and the figures. A new evaluation
> run needs a new experiment folder — see
> [`research/AGENT_INSTRUCTIONS.md`](research/AGENT_INSTRUCTIONS.md).

The leaderboard below is **generated** from `eval/results/*.json` by
`uv run --project eval eval/report.py`. It is the operator's view of every run on
record. Never edit it by hand — a number that has drifted from the run that
produced it is worse than no number.

## Leaderboard

<!-- BEGIN GENERATED LEADERBOARD -->

### `longeval-sci-2026/snapshot-1/train` — qrels `dctr`

| Arm | Corpus | Docs | Queries | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `bm25_only` | full | 869,902 | 100 | 0.3282 | 0.4340 | 0.2796 | 0.6854 | 0.4843 | 0.2110 | `de31887` |
| `dense_only` | full | 869,902 | 100 | 0.2234 | 0.3162 | 0.1754 | 0.5456 | 0.3846 | 0.1590 | `5b66bc2` |
| `fusion_dense_pool` (pool 100) | full | 869,902 | 100 | 0.2852 | 0.3549 | 0.2190 | 0.5419 | 0.4505 | 0.1980 | `5b66bc2` |
| `fusion_full` (pool 100) | full | 869,902 | 100 | 0.2849 | 0.3563 | 0.2233 | 0.5419 | 0.4545 | 0.1960 | `5b66bc2` |
| `fusion_union_pool` (pool 100) | full | 869,902 | 100 | 0.2993 | 0.4031 | 0.2519 | 0.6299 | 0.4734 | 0.1960 | `5b66bc2` |
| `bm25_only` | pooled | 84,489 | 100 | 0.3212 | 0.4314 | 0.2760 | 0.6903 | 0.4788 | 0.2100 | `de31887` |
| `dense_only` | pooled | 84,489 | 100 | 0.2401 | 0.3498 | 0.1965 | 0.6120 | 0.4067 | 0.1700 | `de31887` |
| `fusion_dense_pool` (pool 100) | pooled | 84,489 | 100 | 0.2937 | 0.3829 | 0.2360 | 0.5988 | 0.4589 | 0.2010 | `de31887` |
| `fusion_dense_pool` (pool 1000) | pooled | 84,489 | 100 | 0.2915 | 0.4191 | 0.2577 | 0.7021 | 0.4607 | 0.1910 | `de31887` |
| `fusion_full` (pool 100) | pooled | 84,489 | 100 | 0.2963 | 0.3859 | 0.2415 | 0.5988 | 0.4684 | 0.2020 | `de31887` |
| `fusion_full` (pool 1000) | pooled | 84,489 | 100 | 0.2968 | 0.4221 | 0.2614 | 0.6996 | 0.4753 | 0.1930 | `de31887` |
| `fusion_union_pool` (pool 1000) | pooled | 84,489 | 100 | 0.3001 | 0.4292 | 0.2665 | 0.7065 | 0.4645 | 0.2000 | `de31887` |
| `fusion_union_pool` (pool 100) | pooled | 84,489 | 100 | 0.3056 | 0.4129 | 0.2562 | 0.6511 | 0.4686 | 0.2020 | `de31887` |

### `longeval-sci/2024-11` — qrels `test`

| Arm | Corpus | Docs | Queries | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `bm25_only` | full | 2,014,265 | 99 | 0.1841 | 0.3319 | 0.1949 | 0.6332 | 0.3239 | 0.1596 | `de31887` |
| `bm25_only` | pooled | 69,141 | 99 | 0.1869 | 0.3337 | 0.1985 | 0.6322 | 0.3277 | 0.1636 | `de31887` |
| `dense_only` | pooled | 69,141 | 99 | 0.0804 | 0.1675 | 0.0772 | 0.3518 | 0.2424 | 0.0717 | `de31887` |
| `fusion_dense_pool` (pool 100) | pooled | 69,141 | 99 | 0.1062 | 0.1842 | 0.0881 | 0.3449 | 0.2552 | 0.1020 | `de31887` |
| `fusion_dense_pool` (pool 1000) | pooled | 69,141 | 99 | 0.1298 | 0.2748 | 0.1273 | 0.5709 | 0.3017 | 0.1172 | `de31887` |
| `fusion_full` (pool 100) | pooled | 69,141 | 99 | 0.1098 | 0.1867 | 0.0903 | 0.3449 | 0.2617 | 0.1030 | `de31887` |
| `fusion_full` (pool 1000) | pooled | 69,141 | 99 | 0.1384 | 0.2828 | 0.1341 | 0.5680 | 0.3177 | 0.1192 | `de31887` |
| `fusion_union_pool` (pool 1000) | pooled | 69,141 | 99 | 0.1410 | 0.3032 | 0.1413 | 0.6403 | 0.3169 | 0.1253 | `de31887` |
| `fusion_union_pool` (pool 100) | pooled | 69,141 | 99 | 0.1350 | 0.2927 | 0.1315 | 0.6196 | 0.3121 | 0.1253 | `de31887` |

### `longeval-sci/2025-01` — qrels `test`

| Arm | Corpus | Docs | Queries | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `bm25_only` | full | 1,213,728 | 492 | 0.2362 | 0.3426 | 0.2181 | 0.5989 | 0.4054 | 0.1846 | `de31887` |
| `bm25_only` | pooled | 261,294 | 492 | 0.2486 | 0.3498 | 0.2280 | 0.5972 | 0.4199 | 0.1941 | `de31887` |
| `dense_only` | pooled | 261,294 | 492 | 0.0931 | 0.1660 | 0.0786 | 0.3348 | 0.1996 | 0.0736 | `de31887` |
| `fusion_dense_pool` (pool 100) | pooled | 261,294 | 492 | 0.1451 | 0.2010 | 0.1156 | 0.3294 | 0.2903 | 0.1118 | `de31887` |
| `fusion_dense_pool` (pool 1000) | pooled | 261,294 | 492 | 0.1656 | 0.2628 | 0.1463 | 0.4869 | 0.3221 | 0.1272 | `de31887` |
| `fusion_full` (pool 100) | pooled | 261,294 | 492 | 0.1506 | 0.2046 | 0.1187 | 0.3294 | 0.3002 | 0.1157 | `de31887` |
| `fusion_full` (pool 1000) | pooled | 261,294 | 492 | 0.1710 | 0.2678 | 0.1501 | 0.4915 | 0.3286 | 0.1315 | `de31887` |
| `fusion_union_pool` (pool 1000) | pooled | 261,294 | 492 | 0.1840 | 0.3074 | 0.1695 | 0.5946 | 0.3424 | 0.1459 | `de31887` |
| `fusion_union_pool` (pool 100) | pooled | 261,294 | 492 | 0.1819 | 0.3000 | 0.1635 | 0.5753 | 0.3442 | 0.1435 | `de31887` |

### Published baselines (external, for comparison)

Scored by this harness with the same `ir_measures` call used above, from the LongEval'26 organizers' own published runs — not numbers quoted from a paper.

| System | Snapshot | qrels | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| BM25 (PyTerrier, organizers) | `longeval-sci-2026/snapshot-1/train` | dctr | 0.2922 | 0.4123 | 0.2573 | 0.6836 | 0.4717 | 0.1950 |
| Qwen3-Embedding-4B (organizers) | `longeval-sci-2026/snapshot-1/train` | dctr | 0.2820 | 0.3919 | 0.2378 | 0.6390 | 0.4389 | 0.1880 |

> **Do not compare across corpus scopes.** A `pooled` row is a re-ranking result over the judged set plus a lexical pool; a `full` row ranks the entire snapshot. Reordering metrics (nDCG@10) are broadly comparable, recall metrics are not.

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

**What the 2025 pair shows.** Across `2024-11` → `2025-01`, full-corpus BM25 goes
from nDCG@10 0.1841 to 0.2362 and R@100 0.6332 to 0.5989: effectiveness did not
decay. Read that cautiously — the two snapshots use *different topic sets* (99 vs
492 queries) over differently sized corpora, so the comparison confounds elapsed
time with topic difficulty. It is evidence against catastrophic decay, not a
controlled measurement of persistence. A clean persistence result needs the same
topics re-judged on a later corpus, which is exactly what the withheld 2026 test
snapshots provide.

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
  document, only reorder one. Measured at matched pool width, the union pool
  raises R@100 by **8.7%** on the 2026 snapshot and by **75-80%** on the two 2025
  snapshots. The cost scales with how weak the dense channel is on that corpus,
  which makes it a risk that grows silently as a corpus drifts away from what the
  embedding model handles well.
- That on this collection **BM25 alone outranks every fusion arm** on nDCG@10,
  and that the organizers' 4B-parameter dense baseline also loses to BM25. That
  is a property of short keyword queries over titles+abstracts, not solely of the
  384-dimension model in use — so it is evidence about the task shape, not just a
  reason to swap embedders.
- Whether effectiveness persists across the 2025 snapshot pair.
- That **cluster-scoped max-pooling does not do what it was built to do** — on
  synthetic multi-cluster profiles over this collection. `EXP-2026-08-003`
  refuted C-003: in the condition the claim names (one theme's vocabulary far
  closer to the corpus than the others'), cluster-scoping *lowers* the
  worst-served theme's recall, and the per-cluster evenness measure worsens in
  every cell. Scope it precisely — the profiles are synthesised from LongEval
  queries, so this refutes the **mechanism** under controlled conditions and
  says nothing about whether real declared clusters behave the same way (Q-009).
- That whatever retrieval gain cluster-scoping produces belongs to the **max
  operator, not to cluster semantics**: the `random`-grouping negative control
  showed the largest clustered gains of any mode. That is a statement about the
  aggregation operator, and it is the only positive reading the control permits.

**You may not claim:**

- That this validates Mycelium's actual task. LongEval evaluates
  **query → documents**. Mycelium does **declared-interest profile → feed**. The
  granularity mismatch between a three-word interest and a 200-word abstract —
  one of the core difficulties of the real problem — is *not* tested here.
- Anything about the LLM percent-match, fellowship eligibility, or member
  routing (audit claims C4–C6). None are exercised.
- That the cluster result transfers to the product. `EXP-2026-08-003` measures
  synthetic profiles built from keyword queries. A researcher's declared clusters
  are neither keyword queries nor greedy embedding pairs, and the union-of-qrels
  construction is blind to a document relevant only to a *combination* of
  interests — which is the case multi-interest scoring exists to reward.
- Anything about grants, fellowships, or conferences. LongEval is papers only.
- Certainty proportional to the qrels. These are click-derived pseudo-relevance
  judgments, not human assessment.

The honest framing: **this measures whether the foundation is sound, not whether
the idea is right.** That is worth the effort, because everything downstream
silently inherits whatever is wrong at this layer.

## The re-run rule

Any change to `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, or
`pipeline.py`'s pool construction must be accompanied by a fresh evaluation run,
with the before/after numbers in the changelog entry **and an experiment folder
recording them**:

```bash
make new-experiment SLUG=<what-changed>
```

The harness exists so that the run costs one command and the record costs one
more; see `docs/skills/global.md` and
[`research/AGENT_INSTRUCTIONS.md`](research/AGENT_INSTRUCTIONS.md).

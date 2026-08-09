# `eval/` — the retrieval evaluation harness

Re-measuring the ranking stack is one command:

```bash
uv run --project eval eval/run.py --config eval/configs/fusion_dense_pool.toml --collection sci-2026-train
```

Run every query arm on one collection with `--all`. List what can currently be
scored with `--list-collections`. Results append to `eval/results/*.json`
(committed); TREC run files land in `eval/runs/` (gitignored, regenerable).

`--config` takes several files, and they run in one process so the corpus and its
embedding matrix load once for a whole grid:

```bash
uv run --project eval eval/run.py --collection sci-2026-train \
  --config eval/configs/flat_profile_*.toml eval/configs/clustered_profile_*.toml
```

## The one rule

**The arms call production code.** `harness/arms.py` contains no ranking logic of
its own — it imports `apps.content.lexical`, `apps.content.fusion`,
`apps.content.ranking`, and `apps.content.pipeline._build_pool` directly. When the
ranking stack changes, the next run measures the change and nothing in `eval/`
needs editing. If you find yourself reimplementing scoring here, stop: the number
you get will be about the harness, not about Mycelium.

### Two families of arm

**Query arms** (`bm25_only`, `dense_only`, `fusion_*`) score one query at a time
and are what `--all` runs. **Profile arms** (`flat_profile`, `clustered_profile`,
`slate_profile`, and the `spread_*` family) score a whole *synthetic
multi-cluster profile* — six of the collection's queries treated as six declared
interests, partitioned into three clusters (`harness/profiles.py`) — because a
LongEval query is a single keyword string and the cluster machinery never fires on
one. They exist to make C-003 measurable; see `EXP-2026-08-003`, which refuted it,
and `EXP-2026-08-004`, which tested the lab slate.

The `spread_*` arms (`EXP-2026-08-005`) each forward one
`apps.content.fusion.SpreadPolicy` to `fuse_clusters_pool` and change nothing
else, so an arm differs from the `clustered_profile` baseline by exactly one
production argument. `spread_identity` carries the null policy and must reproduce
the baseline ordering exactly; it is the falsifier that says whether the plumbing
is inert.

Every profile arm reports **positional** run scores (`1/(1+i)`) rather than the
production score. That is not cosmetic: `ir_measures` re-sorts a run by score and
breaks ties its own way, so an arm whose scores tie would be silently re-ordered
inside the metric while an arm whose scores are distinct would not. See
`_profile_ranking` in `harness/arms.py`.

Profile arms are the reason `harness/cluster_metrics.py` exists and is the one
place this harness hand-rolls a metric. No IR toolkit implements per-cluster
coverage, because a cluster is a property of the profile, not of the collection.
That module's docstring states the exception and the obligations it carries; the
relevance family still goes through `ir_measures` untouched.

The seam that makes this possible is `apps.content.protocols.VectorIndex`.
`_build_pool` takes an optional `index`; production passes `PgVectorIndex`, the
harness passes `NumpyIndex`. Because production has **no ANN index** — every
pgvector query is an exact sequential scan — the in-memory index is not an
approximation. It computes the identical ranking.

## Reconnaissance record (2026-08-04)

Measured on this host, not estimated:

| Fact | Value |
|---|---|
| Corpus (`longeval-sci-2026/snapshot-1/train`) | **869,902 documents**, mean 1,610 chars |
| Queries / judgments | 100 queries, 8,772 qrels (`dctr`) |
| Download | ~2.8 GB compressed → ~11 GB extracted (registration pulls all three 2026 snapshots) |
| Hardware | 32 CPU cores, 130 GB RAM, **no CUDA device** |
| Embedding throughput | bge-small on CPU; see `docs/evaluation.md` for the measured rate |

### Which qrels

LongEval-Sci ships **two** judgment sets for the training snapshot and they are
not interchangeable:

- `dctr` — click-model (Dynamic Bayesian / DCTR) derived pseudo-relevance. 8,772
  judgments. This is the default.
- `raw` — raw click-derived judgments, a much smaller set.

Neither is TREC-grade human assessment. The qrels variant is recorded in every
result row and must appear next to every number you ever report.

### Which snapshots can be scored

`--list-collections` is the authority, and `collections.toml` is the only place
that knows. As of 2026-08-04:

| Collection | State |
|---|---|
| `sci-2026-train` | Scoreable (`dctr`, `raw`) |
| `sci-2025-11`, `sci-2025-01` | Scoreable — released CLEF-2025 test qrels; the temporal-persistence pair |
| `sci-2026-s1/s2/s3` | **Blocked**: CLEF 2026 is an active task and the test qrels are unreleased |

The blocked state is *temporary*, not permanent — the organizers release qrels
after the task closes. Adding them is a `collections.toml` edit (flip `scoreable`,
name the variants), never a code change. Run files for the blocked snapshots can
already be produced for a TIRA submission; only scoring is unavailable.

## Where the caches live (and why not under `eval/`)

Both heavy caches sit under `data/eval-cache/`, outside `eval/`:

- **Corpora** — set `IR_DATASETS_HOME=data/eval-cache/ir_datasets` when running.
- **Embedding matrices** — `data/eval-cache/embeddings/`, overridable with
  `MYCELIUM_EVAL_CACHE`.

This is not tidiness. `eval/cache/` is gitignored, so `git worktree remove`
deletes it without warning — and an embedding cache is hours of compute. Putting
both under `data/eval-cache/` (also gitignored, but never inside a worktree)
means a torn-down worktree costs nothing. Learned the hard way.

## Corpus scope: `full` vs `pooled`

Every result row carries `corpus_scope`, and **the two are not comparable**:

- `full` — every document in the snapshot. Supports recall claims.
- `pooled` — the union of every judged document with a deep corpus-wide BM25
  pool. A standard, defensible reduction, but it is a **re-ranking** evaluation:
  reordering metrics (nDCG@10) stay close to full-corpus, recall metrics do not.
  A pooled run cannot support a recall claim, which is exactly the limitation
  `docs/research-audit.md` identifies in C1.

`bm25_only` needs no embeddings at all, so it always runs at `full` scope.

## Layout

```
eval/
  run.py              the single entry point
  collections.toml    which snapshots exist and which can be scored
  configs/            one TOML per arm
  harness/
    datasets.py       ir_datasets -> Retrievable adapters
    index.py          NumpyIndex + the embedding cache
    profiles.py       synthetic multi-cluster profiles + union qrels
    arms.py           each arm as a thin call into apps.content.*
    cluster_metrics.py  per-cluster coverage — the one hand-rolled metric
    scoring.py        ir_measures wrapper + the results contract
    metadata.py       ir_metadata emission (LongEval tracks this)
  cache/              gitignored, and NOT where the caches actually live
  results/            COMMITTED — one small JSON per run, the score history
  runs/               gitignored — TREC run files
```

## What these numbers do and do not license you to claim

See `docs/evaluation.md`. Read it before writing any of these numbers into a
paper. The short version: this measures whether the retrieval foundation is
sound, **not** whether the product idea is right. LongEval evaluates
`query → documents`; Mycelium does `declared-interest profile → feed`.

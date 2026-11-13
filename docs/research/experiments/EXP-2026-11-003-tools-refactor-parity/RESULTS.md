# EXP-2026-11-003 — Results

## 1. Headline

Moving the ranking stack into `tools/` changed nothing the harness can see. After
each of the three code moves (retrieval, then recommendation, then delivery),
both run files were byte-identical to the before run (n=1 per phase,
decompressed sha256). The hypothesis survived.

## 2. Results table

Values from `data/metrics.json`; one run per phase (n=1).

| Phase (tree on top of) | Arm | Run file sha256 (decompressed) | R@100 | nDCG@10 |
|---|---|---|---|---|
| before (`47a8565`) | fusion_dense_pool | `c897ed5e…5786c` | 0.5988 | 0.2937 |
| before (`47a8565`) | bm25_only | `2966316d…98f3a` | 0.6854 | 0.3282 |
| retrieval (`9980298`) | fusion_dense_pool | `c897ed5e…5786c` | 0.5988 | 0.2937 |
| retrieval (`9980298`) | bm25_only | `2966316d…98f3a` | 0.6854 | 0.3282 |
| recommendation (`111634f`) | fusion_dense_pool | `c897ed5e…5786c` | 0.5988 | 0.2937 |
| recommendation (`111634f`) | bm25_only | `2966316d…98f3a` | 0.6854 | 0.3282 |
| delivery (`199b680`) | fusion_dense_pool | `c897ed5e…5786c` | 0.5988 | 0.2937 |
| delivery (`199b680`) | bm25_only | `2966316d…98f3a` | 0.6854 | 0.3282 |

## 3. Figures

None. A table of equal hashes says it.

## 4. Interpretation

The refactor is a pure move as far as ranking is concerned. The deployed pool
construction (`tools/recommendation/pipeline.py`'s `_build_pool`), the BM25 path
(`tools/retrieval/lexical.py`) and the vector index (`tools/retrieval/index.py`)
compute exactly what `apps/content` did. No claim in `CLAIMS.md` changes; every
earlier ranking result still describes the code as it now stands.

## 5. Threats to validity

- Two arms exercise the ranking path the harness reaches: the production pool
  and BM25. They do not cover the per-theme slate selection, the model
  write-ups, or the opportunity scorer. Those are covered by the backend suite,
  which ran green at every phase apart from two collector tests that fail on
  clean main too.
- The before run and the after runs share the embedding cache. A change that
  only altered how documents are embedded would not show here. The refactor
  did not touch the embedder's code, and the cache was not rebuilt.

## 6. What surprised us

Nothing in the ranking. The code move surfaced two latent bugs elsewhere, both
caught by the containerised smoke test and the delete/break matrix rather than
by this experiment. The collector's data root was found by counting parent
directories, and would have silently pointed outside the checkout. And Django
picked the wrong app label for a tool whose `apps.py` imported its base class.

## 7. Follow-ups

None for ranking.

## 8. Reproduction

On each phase's tree, with the caches in the main checkout:

```bash
MAIN=<the main checkout>   # the caches live outside any worktree
export IR_DATASETS_HOME=$MAIN/data/eval-cache/ir_datasets \
       MYCELIUM_EVAL_CACHE=$MAIN/data/eval-cache/embeddings \
       FASTEMBED_CACHE_PATH=$MAIN/data/eval-cache/fastembed \
       HF_HUB_OFFLINE=1
uv run --project eval eval/run.py \
  --config eval/configs/fusion_dense_pool.toml eval/configs/bm25_only.toml \
  --collection sci-2026-train
for f in eval/runs/*__<sha>.txt.gz; do zcat "$f" | sha256sum; done
```

## AMENDMENTS

A completed experiment is immutable. Corrections are appended here, dated, never
edited into the sections above.

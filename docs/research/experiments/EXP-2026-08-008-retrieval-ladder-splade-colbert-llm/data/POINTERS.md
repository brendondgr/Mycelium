# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Frozen document set | `eval/subsets/sci-2026-train__pooled_d1000.txt` | sha256:b83d8d715fbfef8b5b6171b15026288d68428da3969e75f1f0375b68cca9892d | **Committed, and the single most important artifact here.** 84,489 ids in corpus order. Every arm in this experiment scored exactly this set, which is what makes rung-to-rung differences attributable to the stage that was added. Reproduces the corpus the existing leaderboard rows were scored on — verified by five baselines matching to four decimals (ISSUES.md §3). |
| Harness run records | `eval/results/*__pooled__dctr__*.json` for the 24 arms in `tables/ladder.md` | not-hashed: enumerated by `code/collect.py` | Committed to git. `code/collect.py` resolves each row by `(arm, config_hash)` and refuses to emit a table if a label matches more than one config, so the mapping from row to run is checked rather than assumed. |
| TREC run files | `eval/runs/*__pooled__*.txt.gz` | not-hashed: regenerable | Gitignored. Also the source of the candidate-depth measurement in RESULTS §3. |
| Arm configs | `eval/configs/{splade_only,fusion_bm25_dense_splade,colbert_rerank_*,xenc_rerank_*,cascade_colbert_xenc,fusion_union_pool_p500,llm_*}.toml` | not-hashed: committed | 20 files. |
| Pinned environment | `eval/uv.lock` | sha256:e908a7668e231278a8df8463c2ed2b0e797b6c7d8b135188ca6e62efa7a68063 | Committed. |
| Dense embedding matrix (subset) | `data/eval-cache/embeddings/e321abad6f4e3fbcc00850f5dce6b773.npy` | not-hashed: content-addressed filename | 130 MB, gitignored. **Not encoded — row-sliced** out of the cached 869,902-row full-corpus matrix `d07a947b982c94c15b4803266429e04d.npy` by `eval/freeze_subset.py`, which is why the dense channel cost zero encoding. Alignment spot-checked over 64 sampled rows at build time. |
| SPLADE document matrix | `data/eval-cache/embeddings/1d10eb8d247648225455ef8c26296b8e.splade.npz` | not-hashed: content-addressed filename | Gitignored. 84,489 × 30,522 sparse, 12,800,920 non-zeros, mean 151.5 terms/doc. 3,451 s to build. |
| ColBERT token store | `data/eval-cache/embeddings/035e5bf44aa6d18af7aa4d50d7520780.colbert.flat.npy` + `.offsets.npy` | not-hashed: content-addressed filename | Gitignored. 22,373,175 token vectors, dim 96, float16, mean 264.8 tokens/doc. 3,640 s to build. |
| LongEval-Sci corpora | `data/eval-cache/ir_datasets/` | not-hashed: pinned-by-package-version | ~19 GB, re-downloadable. See `EXP-2026-08-001`'s POINTERS.md. |

Nothing above 10 MB enters this folder. `tables/ladder.md` and `data/ladder.json`
are derived from the run records by `code/collect.py` and are regenerable at any
time; neither was ever edited by hand.

Every model artifact above is content-addressed on `(model, snapshot, scope, doc
count, id digest)`, so a corpus that changed underneath cannot silently reuse
stale vectors — and re-running the whole ladder re-encodes nothing.

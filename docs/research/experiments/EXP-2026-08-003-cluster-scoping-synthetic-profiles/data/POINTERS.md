# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Harness run records | `eval/results/*__{flat,clustered}_profile__full__dctr-union-profiles__*.json` | sha256:da44f92fea30496a79f11c39028cff57c55d1fcd1eba4b251227ded2425012cc | Committed to git. 18 files, one per grid cell; each carries the per-profile metrics the bootstrap resamples. Hash is over the concatenation in sorted filename order. |
| TREC run files | `eval/runs/*__{flat,clustered}_profile__*__beta*__full__*.txt.gz` | not-hashed: regenerable | Gzipped rankings plus `ir-metadata.yml` sidecars. `build_metrics.py` reads them only to compute the identical-top-10 share (falsifier 4). |
| Arm configs | `eval/configs/{flat,clustered}_profile_*.toml` | sha256:c9fb684eaa309b6a6ca5c10e86e7ac15ff7319ca459300b0b0f7c02991cd4e90 | Committed. 18 files = 2 arms × 3 groupings × 3 β. |
| Pinned environment | `eval/uv.lock` | sha256:e908a7668e231278a8df8463c2ed2b0e797b6c7d8b135188ca6e62efa7a68063 | Committed. |
| Corpus embedding matrix | `data/eval-cache/embeddings/d07a947b982c94c15b4803266429e04d.npy` | not-hashed: content-addressed filename | 1.3 GB, gitignored, deliberately outside any worktree. The filename *is* a hash of `(model, snapshot, scope, doc count, id digest)`, so a corpus that changed underneath cannot reuse it. Shared with `EXP-2026-08-001`. |
| LongEval-Sci corpora | `~/.ir_datasets/` | not-hashed: pinned-by-package-version | ~11 GB, re-downloaded by `ir-datasets-longeval` on demand. See `EXP-2026-08-001`'s POINTERS.md. |
| Run logs | `data/eval-cache/exp003-gate.log`, `data/eval-cache/exp003-grid.log` | not-hashed: regenerable | Gitignored. The gate run (4 cells) and the full grid (18 cells). Every metric they printed is in `metrics.csv`. |

Nothing above 10 MB enters this folder; the validator enforces it. The run
records are the record — `metrics.csv` and `metrics.json` are derived from them
by `build_metrics.py` and are regenerable at any time.

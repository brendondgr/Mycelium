# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Harness run records | `eval/results/*_profile__full__dctr-union-profiles__*.json` (the subset whose `params` carry `surface_limit`) | sha256:4ce7a7864b4efab7605fa9bd980684eb547b6f935eeb44429b28ef52ba790355 | Committed to git. 24 files: 18 for the `prod`/`cut30` grid and 6 for the size-matched `cut34` condition. Each carries the per-profile metrics the bootstrap resamples and the surfacing diagnostic. Hash is over the concatenation in sorted filename order. |
| TREC run files | `eval/runs/*__{flat,clustered,slate}_profile__*__s{30,34,250}__*.txt.gz` | not-hashed: regenerable | Gzipped surfaced sets plus `ir-metadata.yml` sidecars. `build_metrics.py` reads them only to compute the identical-surfaced-set share (falsifier 4). |
| Arm configs | `eval/configs/slateexp_*.toml` | sha256:8a88d092d5cc87e5fc6c8a95b36e07d8a4bf6da60ca52c356d55f484153dbe6b | Committed. 24 files = 3 arms × 2 conditions × 3 groupings, plus 2 arms × 3 groupings for `cut34`. |
| Pinned environment | `eval/uv.lock` | sha256:e908a7668e231278a8df8463c2ed2b0e797b6c7d8b135188ca6e62efa7a68063 | Committed. |
| Corpus embedding matrix | `data/eval-cache/embeddings/d07a947b982c94c15b4803266429e04d.npy` | not-hashed: content-addressed filename | 1.3 GB, gitignored, outside any worktree. The filename is a hash of `(model, snapshot, scope, doc count, id digest)`. Shared with `EXP-2026-08-001` and `EXP-2026-08-003`. |
| LongEval-Sci corpora | `~/.ir_datasets/` | not-hashed: pinned-by-package-version | ~11 GB, re-downloadable. See `EXP-2026-08-001`'s POINTERS.md. |
| Run logs | `data/eval-cache/exp004-grid.log`, `exp004-cut30-wholeset.log`, `exp004-cut34.log` | not-hashed: regenerable | Gitignored. The first grid, the whole-set-cut-off re-run, and the size-matched condition. Every metric they printed is in `metrics.csv`. |

Nothing above 10 MB enters this folder. The run records are the record;
`metrics.csv`, `surfacing.csv` and `metrics.json` are derived from them by
`build_metrics.py` and are regenerable at any time.

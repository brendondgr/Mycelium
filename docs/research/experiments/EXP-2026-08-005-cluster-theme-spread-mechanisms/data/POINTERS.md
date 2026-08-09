# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Harness run records | `eval/results/*__{clustered,flat,spread_*}_profile*__full__dctr-union-profiles__*.json` (the subset whose `params` carry `surface_limit = 250` and `match_threshold = 0.5`) | sha256:10914d26dd959fd40875ad26f29058222801b166e6d53a24fe1ecf75b7ee82a0 | Committed to git. 45 files = 15 arms × 3 groupings. Each carries the per-profile metrics the bootstrap resamples and the surfacing diagnostic. Hash is over the concatenation in sorted filename order. |
| TREC run files | `eval/runs/*__{clustered,flat,spread_*}*__s250__*.txt.gz` | not-hashed: regenerable | Gzipped surfaced sets plus `ir-metadata.yml` sidecars. `build_metrics.py` does not read them; they exist so a ranking can be re-scored without re-running an arm. |
| Arm configs | `eval/configs/spreadexp_*.toml` | sha256:365413263e9759df57343100ca84c2e2338ffad7990e552488eedc430412ba00 | Committed. 45 files = 15 arms × 3 groupings, all at the deployed `prod` surfacing condition. |
| Pinned environment | `eval/uv.lock` | sha256:e908a7668e231278a8df8463c2ed2b0e797b6c7d8b135188ca6e62efa7a68063 | Committed. |
| Corpus embedding matrix | `data/eval-cache/embeddings/d07a947b982c94c15b4803266429e04d.npy` | not-hashed: content-addressed filename | 1.3 GB, gitignored, outside any worktree. The filename is a hash of `(model, snapshot, scope, doc count, id digest)`. Shared with `EXP-2026-08-001/003/004`. |
| LongEval-Sci corpora | `~/.ir_datasets/` | not-hashed: pinned-by-package-version | ~11 GB, re-downloadable. See `EXP-2026-08-001`'s POINTERS.md. |
| Run logs | `data/eval-cache/exp005-smoke.log`, `exp005-grid.log` | not-hashed: regenerable | Gitignored. The three-cell plumbing smoke (see `ISSUES.md`) and the 45-cell grid. Every metric the grid printed is in `metrics.csv`. |

Nothing above 10 MB enters this folder. The run records are the record;
`metrics.csv`, `surfacing.csv`, `verdicts.csv` and `metrics.json` are derived from
them by `build_metrics.py` and are regenerable at any time.

# Pointers — artifacts stored outside this folder

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Source metrics | `docs/research/experiments/EXP-2026-08-001-longeval-retrieval-baseline/data/metrics.csv` | sha256:a365cf3cd6329dc63a50aff51df91d7c0150d04831a6c8d61aadf76f0133332b | Hash is of the underlying `eval/results/*.json` set that metrics.csv is derived from — the CSV is regenerable, the runs are the record. |
| Harness run records | `eval/results/*.json` | sha256:a365cf3cd6329dc63a50aff51df91d7c0150d04831a6c8d61aadf76f0133332b | Committed to git. Shared with `EXP-2026-08-001`. |
| Pinned environment | `eval/uv.lock` | sha256:e908a7668e231278a8df8463c2ed2b0e797b6c7d8b135188ca6e62efa7a68063 | Committed. |
| LongEval-Sci corpora | outside the worktree | not-hashed: pinned-by-package-version | See `EXP-2026-08-001`'s POINTERS.md. |

This experiment executed nothing of its own; every artifact it rests on belongs
to `EXP-2026-08-001`.

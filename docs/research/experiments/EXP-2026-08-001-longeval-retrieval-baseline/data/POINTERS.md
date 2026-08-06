# Pointers — artifacts stored outside this folder

`docs/research/` stays cloneable in seconds, so run files, corpora, and TREC run
output live where they were produced. Each row carries a hash: a pointer without
one points at whatever is there today.

| Artifact | Path | Hash | Notes |
|---|---|---|---|
| Harness run records (31 files) | `eval/results/*.json` | sha256:a365cf3cd6329dc63a50aff51df91d7c0150d04831a6c8d61aadf76f0133332b | The primary record. Committed to git. Hash is over the sorted concatenation of filename + bytes. `data/metrics.csv` is derived from these and nothing else. |
| Published baseline scores | `eval/baselines.json` | sha256:a1681697263dfbf4b98416676f74da72de8932eecdddb41375bf72317ce0e586 | The organizers' runs, scored by this harness. Committed. |
| Collection declarations | `eval/collections.toml` | sha256:73920eb40ca57cf58d9a7f1b66c9f64890cbcfec402353a8fc995f6af317ac00 | The only file that knows which snapshots are scoreable. Committed. |
| Pinned environment | `eval/uv.lock` | sha256:e908a7668e231278a8df8463c2ed2b0e797b6c7d8b135188ca6e62efa7a68063 | Pins `ir-datasets-longeval` and `fastembed`, which together pin the corpus and the embedder. Committed. |
| TREC run files | `eval/runs/*.txt.gz` | not-hashed: gitignored-and-regenerable | **Not committed.** Regenerable from the entrypoint; no hash was taken before they were regenerated. |
| LongEval-Sci corpora | outside the worktree, via `ir-datasets-longeval` cache | not-hashed: pinned-by-package-version | ~2.8 GB compressed / ~11 GB extracted. Deliberately outside the git worktree: a gitignored directory inside one is deleted by `git worktree remove`, and re-downloading costs hours. Pinned by `ir-datasets-longeval` in `eval/uv.lock`, not by checksum. |
| Embedding cache | outside the worktree | not-hashed: derived-and-regenerable | Same reasoning. Regenerable at ~33–39 docs/s on this host; the full 2026 corpus is ~6 h. |

## `not-hashed:`

The last three rows admit that no checksum was taken, with a reason, rather than
carrying a value that looks like a hash. The validator accepts the marker and
emits a warning; it is only defensible for a *regenerable* artifact in a
back-filled experiment. Any future experiment must hash at write time — the
field is only worth requiring if it is true.

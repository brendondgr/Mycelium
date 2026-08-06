# EXP-2026-08-002 — Issues

## 2026-08-06 — The analysis is post-hoc, and the record should say so

**Impact:** The question was written after seeing the results. `PROTOCOL.md` was
not pre-registered.

**Cause:** `fusion_union_pool` was built as a comparison arm for
`EXP-2026-08-001`. Its recall advantage was noticed in those results and split
out into this experiment because it answers a different question and supports a
different claim (C-008).

**Resolution:** recorded as post-hoc in `PROTOCOL.md` and in the threats section
of `RESULTS.md`, rather than presented as a designed ablation. The follow-up
(Q-001) is deliberately framed as a confirmation on a different corpus.

**Paper implication:** if this appears in a paper, it must be described as an
exploratory analysis of an existing ablation arm, not as a pre-registered
experiment. The confirmation on the production corpus is what would make it a
result.

## 2026-08-06 — Shares runs with EXP-2026-08-001

**Impact:** This folder holds no run records of its own. `compute.wall_clock_hours`
is 0 because nothing was executed for it.

**Cause:** the arms were run once and answer two questions.

**Resolution:** `data/build_metrics.py` reads `EXP-2026-08-001`'s `metrics.csv`
rather than duplicating run files. Both manifests list the other under `related`.

**Paper implication:** the two results are not independent evidence. They come
from the same runs on the same collection, and a reviewer counting experiments
should count one execution, not two.

## 2026-08-06 — No full-corpus comparison for the 2025 pair

**Impact:** The headline comparison is pooled-scope only. The strongest cells
(+79.7%, +74.6%) cannot be confirmed at full corpus scope.

**Cause:** the 2025 snapshots were never run with full-corpus dense or fusion
arms — that would require embedding 2.0M and 1.2M documents on CPU, roughly a day
and a half at the measured throughput.

**Resolution:** the 2026 full-corpus pair does exist and points the same way
(`fusion_dense_pool` R@100 0.5419 vs `fusion_union_pool` 0.6299, +16.2%).
Recorded in the threats section.

**Paper implication:** state the scope on every cell. A pooled recall gain is not
a full-corpus recall gain.

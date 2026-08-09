# EXP-2026-08-004 — Issues, anomalies, and gotchas

## Protocol amendment: the pre-registered co-primary metric was structurally blind

**What was pre-registered.** `PROTOCOL.md` names `min_cluster_recall@10` as
primary (for continuity with `EXP-2026-08-003`) and `cluster_coverage@30` as
co-primary, on the reasoning that a slate allocating `3 clusters × 10 = 30` slots
must show its effect at a depth comparable to that allocation.

**Why that was wrong.** `fuse_clusters_pool` folds slate members into the
surfaced set and then re-sorts the union by `final_score`. A slate member is by
definition a candidate the *global* cut discarded — so its `final_score` is below
the cut, and after re-sorting it lands at rank 31 or later. **No top-k at or
below the global cut can observe the mechanism.** Every `@10` and `@30` delta in
this experiment is exactly 0.0, and that is arithmetic, not evidence.

**What was changed, and when.** Cut-offs `40` and `1000` were added to the
`cut30` configs and those nine cells re-run, so whole-set coverage
(`cluster_coverage@1000`, above any surfaced size here) could be measured. The
`prod` cells were not re-run: their surfacing diagnostic already showed identical
sets, so no depth could have separated the arms there.

**When the flaw was found: before any outcome.** It was caught from the surfacing
diagnostic (`mean_surfaced` 33.8 vs 30, with the additions necessarily last), not
from an unwelcome result. The pre-registered `@10` and `@30` rows are still
computed and still in `data/metrics.csv` and the results table — all zeros —
rather than dropped. Nothing was substituted for a metric that gave an
inconvenient answer; a metric was *added* because the original could not answer
at all.

The general lesson is recorded as Q-008's neighbour in `OPEN_QUESTIONS.md`: when
a mechanism changes a *set* rather than an *ordering*, a fixed-depth ranking
metric is the wrong instrument, and that has to be checked at design time.

## The size-matched condition was added after the first grid

`cut34` (slate-free arms at a 34-item cut) is not in the original 18-cell grid.
It was added to answer pre-registered falsifier 3 — "the gain is bought, not
earned" — which cannot be evaluated without it, since the slate surfaces 33.5–33.8
items against the other arms' 30. The falsifier was written before the runs; only
the condition that tests it was built afterwards, once the surfacing numbers said
what "matched size" should be. It fires.

## The production condition cannot discriminate, and that is the finding

In `prod` (`match_threshold = 0.5`, `surface_limit = 250`) every arm surfaces
exactly 250 items from a ~575-candidate pool, and `slate_profile` and
`clustered_profile` produce **identical surfaced sets for 100% of profiles**.
Pre-registered falsifier 2 anticipated this ("the slate is inert in production").

Two consequences worth separating:

- For the **mechanism** question, `prod` is uninformative and `cut30` carries the
  answer.
- For the **product** question, `prod` *is* the answer: at this pool size the
  deployed configuration never exercises `top_per_cluster`.

Note also what the 250 implies about the threshold: the 0.5 cosine floor admits
more than 250 of ~575 candidates for every synthetic profile tested, so the
*backstop* binds and the *threshold* does not. Logged as Q-012.

## Hand-rolled metrics, again

The three coverage metrics come from `eval/harness/cluster_metrics.py` and break
the harness's "never hand-roll a metric" rule for the reason given in that
module's docstring and in `EXP-2026-08-003`'s `ISSUES.md`. Unchanged here; the
same unit-test fixtures pin them, and the relevance guardrail still goes through
`ir_measures`. These numbers are comparable within and between these two
experiments, and to nothing published.

## An arm that could have silently compared itself

`slate_profile` differs from `clustered_profile` by exactly one production
argument (`cluster_top_n`). If that argument had failed to arrive — a plausible
plumbing slip — the experiment would have compared an arm against itself and
reported a null that looked exactly like a real negative result.
`eval/tests/test_profile_arms.py::test_slate_arm_is_otherwise_identical_to_the_clustered_arm`
asserts the two calls differ in that key and no other, and the identical-set
share is computed and reported for the same reason (falsifier 4). In `cut30` it
is 0–3.3%, so the argument demonstrably arrived.

## The tree was dirty when the runs executed

`manifest.yaml` records `code.dirty: true`. The uncommitted changes were this
experiment's own harness additions — the `slate_profile` arm, the surfacing
diagnostic, the surface-limit/threshold/cut-off parameters, and the configs —
committed in the same change as this folder. No production code under
`web/backend` was modified; `git diff` against the pre-change commit is empty for
that tree, and the backend suite was run to confirm it (1,409 passed, 1
pre-existing failure unrelated to this work).

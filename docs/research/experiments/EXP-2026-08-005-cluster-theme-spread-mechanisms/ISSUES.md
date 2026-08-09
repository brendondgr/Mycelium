# EXP-2026-08-005 — Issues, anomalies, and gotchas

## A three-cell plumbing smoke ran before `PROTOCOL.md` was committed

Order of events, stated plainly because the record's rule is that the protocol is
written first:

1. The mechanisms and the harness arms were implemented.
2. A three-cell smoke — `clustered_profile`, `spread_identity`, `spread_interleave`
   on `imbalanced` — was launched to check the plumbing end to end before
   committing to a 45-cell grid.
3. `PROTOCOL.md` was written while that smoke ran, and before the full grid.

What the smoke was for, and what it was not: it existed to answer "does an arm
run at all, and does the null policy reproduce the baseline". Its `spread_interleave`
cell did print metrics, so a result was visible before the protocol file existed.
That cell was re-run as part of the full grid under an amended scoring convention
(below), so no number in `RESULTS.md` comes from it — but the protocol's
hypotheses were written by someone who had seen one arm's numbers, and that is
recorded here rather than glossed. The hypotheses that section states are about
*which family of mechanism* moves the metric, which the smoke did not address, and
about M6's inertness, which no arm in the smoke tested.

## The scoring convention changed after the smoke, and every arm changed with it

The smoke exposed a real measurement asymmetry. `spread_identity` produced a
**byte-identical run file** to `clustered_profile` for all 30 profiles — verified
by diffing the gzipped runs, not inferred — and its set-based metrics agreed
exactly. But `nDCG@10` read 0.1901 against the baseline's 0.1896, and `nDCG@100`
0.1969 against 0.1985.

The cause is not the ranking. `ir_measures` re-sorts a run by score and breaks
ties by its own convention. The baseline's `final_score` ties frequently, so its
ordering was being silently rearranged *inside the metric*; the spread arm's
positional scores are all distinct, so its ordering was not. `AP`, `P@10`, `R@100`
and `RR` were unaffected because they binarize relevance and the reordered
documents were tied in the binary sense — only the graded metric could see it.

The fix is in `eval/harness/arms.py::_profile_ranking`: **every** profile arm now
reports positional scores `1/(1+i)`, after a deterministic `(-score, id)` sort for
the arms whose score is the ranking. What the arm ordered is what gets scored, for
all arms alike.

Two consequences a reader needs:

- Everything in this experiment ran under the new convention, so the comparisons
  here are internally consistent.
- The baseline's `nDCG` numbers here are **not** directly comparable to
  `EXP-2026-08-004`'s `prod` rows, which ran under the old convention. Those runs
  are unchanged and remain the record of what was measured then; this is a
  convention difference, not a correction to them.

## Hand-rolled metrics, again

The three coverage metrics come from `eval/harness/cluster_metrics.py` and break
the harness's "never hand-roll a metric" rule, for the reason given in that
module's docstring and in `EXP-2026-08-003`'s `ISSUES.md`: a cluster is a property
of the synthetic profile, not of the collection, so no IR toolkit can implement
them. Unchanged here; the same unit-test fixtures pin them, and the relevance
guardrail still goes through `ir_measures`. These numbers are comparable within
and between `EXP-2026-08-003/004/005`, and to nothing published.

## The judgments are still click-derived

LongEval-Sci `dctr` qrels are click-model pseudo-relevance, not human assessment,
and the profile qrels are a *union* over each profile's constituent queries, which
no assessor ever judged as a unit. This is repeated next to every number for the
third experiment running because it is the largest standing limitation of the
whole cluster line of work, not a footnote.

## Falsifier 1 has no formal test, by construction

The `imbalanced` and `random` groupings are built from the same interest sets but
they are **different profiles**, so their deltas cannot be paired and there is no
valid confidence interval on the difference between them. `build_metrics.py`
therefore reports both deltas side by side and flags whether the control's
interval also excludes zero; it does not compute a significance test on the gap.
Manufacturing one would have been worse than saying this.

## Parameters were fixed before the runs and not tuned

`alpha = 0.5` (cap), `lam = 0.5` (MMR), `admit_frac = 0.5` (relative floor) are
midpoints of their meaningful ranges, chosen before any cell ran and not adjusted
afterwards. Tuning a knob on the same 30 profiles used to measure it is the most
direct route from a null result to a positive one, and there is no held-out set
here to tune against. A consequence worth stating: **no mechanism here has been
shown at its best**, only at an arbitrary point. A mechanism that failed the
decision rule at these values has not been shown to be useless.

## The tree was dirty when the runs executed

`manifest.yaml` records `code.dirty: true`. The uncommitted changes were this
experiment's own additions — the `SpreadPolicy` machinery in
`apps/content/fusion.py`, the `spread` keyword on `fuse_clusters_pool`, the harness
arms and configs, and this folder — committed in the same change.

Unlike `EXP-2026-08-003` and `-004`, this experiment **does** modify production
code under `web/backend`. Every addition is opt-in: `spread=None` is the default
and short-circuits before any new code runs, `SpreadPolicy()` with no arguments is
a no-op, and no deployed caller passes the keyword. The backend suite was run to
confirm nothing else moved.

# EXP-2026-08-005 — Results

> Every number below rests on LongEval-Sci `dctr` qrels: **click-model-derived
> pseudo-relevance, not human assessment**, unioned across each synthetic
> profile's six constituent queries. The three coverage metrics are hand-rolled
> and comparable to nothing published.

## 1. Headline

**The mechanisms work, and it does not matter, because they only climb back to
where the ranking already was before it was clustered.**

Four findings, in the order they should be read.

1. **Theme-aware selection genuinely moves the worst-served theme.** Against the
   deployed cluster-scoped baseline on `imbalanced` profiles, four mechanisms
   raise `min_cluster_recall@10` with intervals excluding zero — `spread_rankmerge`
   +0.0047 `[+0.0010, +0.0089]`, `spread_mmr` +0.0043 `[+0.0014, +0.0078]`,
   `spread_interleave` and `spread_quota` +0.0035 `[+0.0007, +0.0064]` each.
   (Those last two agree on every reported metric while producing **different
   rankings** — 0/30 profiles identical. Equal and proportional allocation move
   different papers; at this depth the coverage metrics cannot tell them apart,
   which is Q-008 showing up again.) `spread_mmr`
   and `spread_rankmerge` also raise `cluster_coverage@10` by +0.0778 with
   intervals excluding zero. The concentration `EXP-2026-08-003` measured is
   addressable.

2. **And the gain is real theme structure, not the operator.** On the `random`
   control — the same interests in a meaningless partition — every mechanism's
   primary delta sits between −0.0010 and +0.0019 and **none** has an interval
   excluding zero. Pre-registered falsifier 1 does **not** fire. This is the
   opposite of `EXP-2026-08-003`, where the `random` control showed the *largest*
   clustered gains and forced the conclusion that the max operator, not the
   themes, was doing the work.

3. **But no mechanism beats simply not clustering.** Measured against the
   `flat_profile` arm on the same profiles, the best mechanism is +0.0015
   `[−0.0011, +0.0043]` on the primary — an interval comfortably spanning zero —
   and every coverage comparison against `flat` spans zero for every mechanism.
   `spread_interleave` is significantly **worse** than flat on `nDCG@10`
   (−0.0196, `[−0.0378, −0.0007]`). The flat arm itself clears the decision rule
   (+0.0032 `[+0.0007, +0.0066]`, ΔnDCG@10 +0.0128) while needing no clusters and
   no mechanism at all.

4. **On the realistic grouping, nothing helps.** Under `coherent` — clusters
   agglomerated by embedding similarity, the case a real profile resembles — not
   one arm has an interval excluding zero on the primary, and most point estimates
   are *negative* (`spread_interleave` −0.0015, `spread_rankmerge` −0.0004,
   `flat_profile` −0.0010). The mechanisms only do anything in the pathological
   condition they were designed for.

So **C-011 is refuted as stated.** A theme-aware selection rule does raise the
worst-served theme's representation — over the *cluster* path. It does not raise
it over the simpler thing the cluster path replaced. The correct reading is not
"these mechanisms fail" but "these mechanisms repair a problem that clustering the
ranking created", and `EXP-2026-08-003`'s conclusion stands unchanged: on this
evidence the cluster-scoped *ranking* is the thing to reconsider, not the absence
of a diversifier on top of it.

Three secondary results worth their own lines:

- **Pre-registered hypothesis 2 was exactly right.** `spread_floor` (M6, the
  per-theme admission floor) produces deltas of **precisely 0.0000** on every
  measure in every grouping. The 250-item backstop binds before admission does, so
  anything the relative floor newly admits is discarded by the same arithmetic
  that made the slate inert in `EXP-2026-08-004`.
- **Falsifier 3 fires: there is no synergy at all.** Every combination collapses
  onto one of its parts. Checked against the gzipped run files rather than
  inferred from matching metrics: `spread_rankmerge_interleave`,
  `spread_rankmerge_quota`, `spread_floor_interleave` and `spread_all` are
  **identical for 30/30 profiles** to their selection component;
  `spread_rankmerge_cap` is identical for 30/30 to `spread_rankmerge`, and
  `spread_rankmerge_mmr` for 27/30. This is structural, not coincidental — see §6.
- **Falsifier 4 passes cleanly.** The null policy's largest absolute per-profile
  difference from the untouched baseline is **0.0** in all three groupings, across
  all thirteen measures. The spread code path contributes nothing of its own.

## 2. Decision rule, applied

The pre-registered rule: a mechanism **helps** iff, on the `imbalanced` grouping
against the `clustered_profile` baseline, Δ`min_cluster_recall@10` > 0 with a 95%
CI excluding zero, **and** Δ`nDCG@10`'s CI lower bound is above −0.01. It is
evaluated in `build_metrics.py`, not by eye.

Two columns carry the checks that matter more than the verdict.

**Δ primary on `random`** is falsifier 1: the same delta on a grouping holding the
same interests in a meaningless partition. A mechanism that moves the metric just
as much there is exploiting the shape of the operator, not the semantics of a
theme. None does.

**Δ primary vs `flat`** is the second bar `PROTOCOL.md` §Baselines names: the same
mechanism measured against no clusters at all. A mechanism that beats the cluster
path but not the flat path has repaired damage rather than created value. **No
entry in that column is bold**, meaning not one mechanism's advantage over `flat`
has an interval excluding zero.

<!-- BEGIN GENERATED VERDICTS -->

| Arm | Δ`min_cluster_recall@10` | 95% CI | Δ`nDCG@10` | 95% CI | Δ primary on `random` | Δ primary vs `flat` | Helps? |
|---|---:|---|---:|---|---:|---:|---|
| `flat_profile` | +0.0032 | [+0.0007, +0.0066] | +0.0128 | [-0.0031, +0.0274] | -0.0008 | — | **yes** |
| `spread_identity` | +0.0000 | [+0.0000, +0.0000] | +0.0000 | [+0.0000, +0.0000] | +0.0000 | -0.0032 | no (primary) |
| `spread_interleave` | +0.0035 | [+0.0007, +0.0064] | -0.0067 | [-0.0256, +0.0123] | -0.0010 | +0.0003 | no (guardrail) |
| `spread_quota` | +0.0035 | [+0.0007, +0.0064] | -0.0067 | [-0.0256, +0.0123] | -0.0010 | +0.0003 | no (guardrail) |
| `spread_cap` | +0.0007 | [+0.0000, +0.0021] | +0.0086 | [+0.0002, +0.0187] | +0.0019 | -0.0025 | no (primary) |
| `spread_mmr` | +0.0043 | [+0.0014, +0.0078] | +0.0055 | [-0.0085, +0.0187] | +0.0008 | +0.0010 | **yes** |
| `spread_rankmerge` | +0.0047 | [+0.0010, +0.0089] | +0.0039 | [-0.0104, +0.0186] | -0.0010 | +0.0015 | no (guardrail) |
| `spread_floor` | +0.0000 | [+0.0000, +0.0000] | +0.0000 | [+0.0000, +0.0000] | +0.0000 | -0.0032 | no (primary) |
| `spread_rankmerge_interleave` | +0.0035 | [+0.0007, +0.0064] | -0.0067 | [-0.0256, +0.0123] | -0.0010 | +0.0003 | no (guardrail) |
| `spread_rankmerge_quota` | +0.0035 | [+0.0007, +0.0064] | -0.0067 | [-0.0256, +0.0123] | -0.0010 | +0.0003 | no (guardrail) |
| `spread_rankmerge_cap` | +0.0047 | [+0.0010, +0.0089] | +0.0039 | [-0.0104, +0.0186] | -0.0010 | +0.0015 | no (guardrail) |
| `spread_rankmerge_mmr` | +0.0047 | [+0.0010, +0.0089] | +0.0039 | [-0.0104, +0.0186] | -0.0010 | +0.0015 | no (guardrail) |
| `spread_floor_interleave` | +0.0035 | [+0.0007, +0.0064] | -0.0067 | [-0.0256, +0.0123] | -0.0010 | +0.0003 | no (guardrail) |
| `spread_all` | +0.0035 | [+0.0007, +0.0064] | -0.0067 | [-0.0256, +0.0123] | -0.0010 | +0.0003 | no (guardrail) |

<!-- END GENERATED VERDICTS -->

## 3. The full coverage picture on the target condition

n = 30 paired profiles; 10,000-resample paired bootstrap, seed 20260809. **Bold**
marks an interval excluding zero.

<!-- BEGIN GENERATED COVERAGE -->

| Arm | Measure | baseline | treatment | Δ | 95% CI |
|---|---|---:|---:|---:|---|
| `flat_profile` | `min_cluster_recall@10` | 0.0049 | 0.0081 | **+0.0032** | [+0.0007, +0.0066] |
| `flat_profile` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [+0.0000, +0.1000] — spans 0 |
| `flat_profile` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3452 | -0.0056 | [-0.0656, +0.0589] — spans 0 |
| `spread_identity` | `min_cluster_recall@10` | 0.0049 | 0.0049 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_identity` | `cluster_coverage@10` | 0.5667 | 0.5667 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_identity` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3507 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_interleave` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_interleave` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_interleave` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_quota` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_quota` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_quota` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_cap` | `min_cluster_recall@10` | 0.0049 | 0.0056 | +0.0007 | [+0.0000, +0.0021] — spans 0 |
| `spread_cap` | `cluster_coverage@10` | 0.5667 | 0.5889 | +0.0222 | [+0.0000, +0.0556] — spans 0 |
| `spread_cap` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3648 | +0.0141 | [-0.0256, +0.0678] — spans 0 |
| `spread_mmr` | `min_cluster_recall@10` | 0.0049 | 0.0092 | **+0.0043** | [+0.0014, +0.0078] |
| `spread_mmr` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0333, +0.1333] |
| `spread_mmr` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3099 | -0.0408 | [-0.1050, +0.0289] — spans 0 |
| `spread_rankmerge` | `min_cluster_recall@10` | 0.0049 | 0.0096 | **+0.0047** | [+0.0010, +0.0089] |
| `spread_rankmerge` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0111, +0.1444] |
| `spread_rankmerge` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3093 | -0.0415 | [-0.1178, +0.0400] — spans 0 |
| `spread_floor` | `min_cluster_recall@10` | 0.0049 | 0.0049 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_floor` | `cluster_coverage@10` | 0.5667 | 0.5667 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_floor` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3507 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_rankmerge_interleave` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_rankmerge_interleave` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_rankmerge_interleave` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_rankmerge_quota` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_rankmerge_quota` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_rankmerge_quota` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_rankmerge_cap` | `min_cluster_recall@10` | 0.0049 | 0.0096 | **+0.0047** | [+0.0010, +0.0089] |
| `spread_rankmerge_cap` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0111, +0.1444] |
| `spread_rankmerge_cap` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3093 | -0.0415 | [-0.1178, +0.0400] — spans 0 |
| `spread_rankmerge_mmr` | `min_cluster_recall@10` | 0.0049 | 0.0096 | **+0.0047** | [+0.0010, +0.0089] |
| `spread_rankmerge_mmr` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0111, +0.1444] |
| `spread_rankmerge_mmr` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3093 | -0.0415 | [-0.1178, +0.0400] — spans 0 |
| `spread_floor_interleave` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_floor_interleave` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_floor_interleave` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_all` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_all` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_all` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |

<!-- END GENERATED COVERAGE -->

## 4. What each arm surfaced (falsifier 2)

A coverage gain bought by surfacing more items is a different thing from one that
comes free. Under a spread policy the surfaced size is `min(admitted, 250)` by
construction, so this table is mainly a check that the admission mechanism (M6)
did what it claimed and that nothing else drifted.

<!-- BEGIN GENERATED SURFACING -->

| Arm | Grouping | mean surfaced | max surfaced | mean pool |
|---|---|---:|---:|---:|
| `clustered_profile` | `coherent` | 250.00 | 250 | 574.5 |
| `clustered_profile` | `imbalanced` | 250.00 | 250 | 579.5 |
| `clustered_profile` | `random` | 250.00 | 250 | 574.5 |
| `flat_profile` | `coherent` | 250.00 | 250 | 574.5 |
| `flat_profile` | `imbalanced` | 250.00 | 250 | 579.5 |
| `flat_profile` | `random` | 250.00 | 250 | 574.5 |
| `spread_all` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_all` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_all` | `random` | 250.00 | 250 | 574.5 |
| `spread_cap` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_cap` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_cap` | `random` | 250.00 | 250 | 574.5 |
| `spread_floor` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_floor` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_floor` | `random` | 250.00 | 250 | 574.5 |
| `spread_floor_interleave` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_floor_interleave` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_floor_interleave` | `random` | 250.00 | 250 | 574.5 |
| `spread_identity` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_identity` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_identity` | `random` | 250.00 | 250 | 574.5 |
| `spread_interleave` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_interleave` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_interleave` | `random` | 250.00 | 250 | 574.5 |
| `spread_mmr` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_mmr` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_mmr` | `random` | 250.00 | 250 | 574.5 |
| `spread_quota` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_quota` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_quota` | `random` | 250.00 | 250 | 574.5 |
| `spread_rankmerge` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_rankmerge` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_rankmerge` | `random` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_cap` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_cap` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_rankmerge_cap` | `random` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_interleave` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_interleave` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_rankmerge_interleave` | `random` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_mmr` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_mmr` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_rankmerge_mmr` | `random` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_quota` | `coherent` | 250.00 | 250 | 574.5 |
| `spread_rankmerge_quota` | `imbalanced` | 250.00 | 250 | 579.5 |
| `spread_rankmerge_quota` | `random` | 250.00 | 250 | 574.5 |

<!-- END GENERATED SURFACING -->

## 5. Figures

| Figure | What it shows |
|---|---|
| `fig-mechanism-primary` | Each mechanism's primary-metric delta and its confidence interval, on the target grouping. A forest plot, because the interval is the finding. |
| `fig-spread-vs-relevance` | The trade-off plane: change in per-theme inequality against change in `nDCG@10`. |
| `fig-target-vs-control` | Falsifier 1 — the target condition beside the meaningless-partition control. |

## 6. Reading

### Why the combinations collapsed onto their parts

This looked at first like a plumbing bug and is not; the arms are pinned to differ
by exactly one production argument, and `spread_identity`'s zero drift proves the
path is otherwise inert. The cause is that the two families of mechanism operate
on **disjoint inputs**.

- `quota_clusters` (M1/M3) selects entirely from `per_cluster` scores — each
  theme's own ranking — and never consults `final_score` except to fill leftover
  slots. `merge="rank"` (M2) changes only `final_score`. So under a quota, the
  merge is unobservable, and `spread_rankmerge_interleave` *must* equal
  `spread_interleave`.
- In the other direction, `merge="rank"` already interleaves the themes: a
  candidate's key becomes its best within-cluster reciprocal rank, so each theme's
  rank-1 paper ties at the top. A downstream balancing rule then finds almost
  nothing left to balance — the cap never binds at all (`spread_rankmerge_cap`
  matches `spread_rankmerge` on 30/30 profiles) and MMR's saturation term rarely
  dominates (27/30).

That is a real finding about the design space rather than a null: **the score fix
and the selection fix are substitutes, not complements.** Stacking them cannot
help, and a future attempt should pick one layer and tune it rather than compose
across layers.

### What separates the mechanisms

`fig-spread-vs-relevance` shows the trade-off cleanly. `spread_interleave` and
`spread_quota` buy their coverage with relevance (ΔnDCG@10 −0.0067 against the
cluster baseline, −0.0196 against flat) because equal allocation is forced to
promote a weak theme's mediocre paper over a strong theme's good one. `spread_mmr`
and `spread_rankmerge` are soft — a genuinely stronger theme keeps winning slots,
it just has to keep earning them — and both come out with *positive* nDCG point
estimates. Softness is what distinguishes the mechanisms that pass from those that
do not, and it is the one design lesson here that would transfer.

`spread_cap` at α = 0.5 is too weak to matter: with three themes, "no more than
half of any prefix" almost never binds. It failed the primary gate, which says
nothing about the mechanism at a tighter α — see §7.

### The one uncomfortable number

`spread_rankmerge` has the **largest** primary gain in the grid and a positive
nDCG@10 point estimate (+0.0039), and it fails the decision rule because its
guardrail interval's lower bound is −0.0104 against a pre-registered floor of
−0.0100. It misses by 0.0004.

The rule was fixed before the runs and is not being renegotiated now: by the
stated criterion, `spread_rankmerge` does not pass. But a reader should not take
"fails the guardrail" to mean "costs relevance" — the point estimate says it gains
relevance, and the interval is wide because n = 30. Whether that floor was set at
a sensible place is a fair question about the protocol, and the honest answer is
that it was chosen without any prior sense of the CI widths this design produces.

### What this does not say

It does not say max-pooling is fine. `EXP-2026-08-003`'s refutation of C-003 is
untouched, and finding 3 above sharpens it: the flat arm still beats the cluster
path, and now we know that is not for want of a diversifier.

## 7. Limits

- **Synthetic profiles.** A result here licenses "the mechanism does/doesn't work
  under controlled conditions", never a product decision. Q-009 stands.
- **Click-derived judgments,** unioned across queries no assessor judged as a
  unit. Third experiment running; see `ISSUES.md`.
- **No mechanism was tuned.** α, λ and the admission fraction were fixed at
  midpoints before the runs and never adjusted, because there is no held-out set
  here to tune against. Every mechanism is therefore measured at an arbitrary
  point in its parameter space, and a failure is a failure *at that point*.
  `spread_cap` in particular is close to a no-op at α = 0.5.
- **n = 30, and it shows.** Several intervals sit just across a threshold —
  `spread_rankmerge`'s guardrail by 0.0004, `spread_mmr`'s coverage gain against
  flat at `[−0.0111, +0.0778]`. This experiment cannot distinguish "no advantage
  over flat" from "an advantage too small to resolve at this n". Same limitation
  as Q-011, now with a second instance.
- **One condition.** Everything is at deployed surfacing. A mechanism inert here
  (M6) might not be at a binding cut, exactly as the slate was in
  `EXP-2026-08-004`.
- **`min_cluster_recall@10` remains a weak instrument** — Q-008, unresolved, and
  it applies to every number above.

## 8. Follow-ups

Recorded as Q-013 … Q-015 in `OPEN_QUESTIONS.md`:

- **Q-013** — does any mechanism beat `flat` at a larger n, or is the flat arm
  genuinely the ceiling? This is the question the experiment could not answer and
  the only one that would change the conclusion.
- **Q-014** — the mechanisms only act on `imbalanced` profiles. How common is that
  condition among *real* declared cluster sets? If it is rare, none of this
  matters even if Q-013 comes back positive.
- **Q-015** — is the −0.01 nDCG guardrail the right budget, and should a decision
  rule's threshold be calibrated against the CI widths a design actually produces
  before it is pre-registered?

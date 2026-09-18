# EXP-2026-09-006 — Results

**System:** `apps/collab` (collaboration-network CN-03) on the knowledge core,
at the commits in `manifest.yaml`. **Data:** 150 fictional funding calls
written by the local model from planted slots, added to EXP-2026-09-005's
world of 240 fictional researchers and 48 labs. **Judgements:** planted ground
truth, not human assessment. **Runs:** three arms (prompt `s1`, `s2`, `s3`),
each after a pre-registered amendment, and a coverage-threshold sweep on arm
C's stored slots. Every number is in `data/metrics.json`, written by
`code/analyse.py` from the harness outputs in `data/`.

## 1. Headline

The shipped version (arm C, `s3`) passed every pre-registered bar: slot recall
**0.876** and precision **0.824** over problem, method and data slots, partner
roles found every time, the "required" flag right **97.8%** of the time, and
the lab team-fit line marking every canonical-name method slot correctly
(**1.0** over 6,624 lab–slot pairs). Nothing that must be zero was non-zero in
any arm. It took two amendments to get there: arm A missed recall, arm B marked
the funded problem as required.

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
See [`tables/summary.md`](tables/summary.md) (all three arms, every metric and
invariant) and [`tables/coverage_sweep.md`](tables/coverage_sweep.md) (coverage
agreement and near-miss false covers at four thresholds). Both are regenerated
by `code/analyse.py`; neither is typed.
<!-- END GENERATED TABLE -->

| Metric | Arm A (`s1`) | Arm B (`s2`) | Arm C (`s3`, shipped) | Bar |
|---|---:|---:|---:|---|
| slot recall (problem, method, data) | 0.739 | 0.878 | 0.876 | ≥ 0.85 |
| slot precision | 0.789 | 0.823 | 0.824 | ≥ 0.80 |
| role recall | 1.0 | 1.0 | 1.0 | ≥ 0.80 |
| required-flag agreement | 0.932 | 0.789 | 0.978 | ≥ 0.85 |
| lab coverage agreement, canonical names (primary) | 0.998 | 1.0 | 1.0 | ≥ 0.95 |
| lab coverage agreement, variant names | 0.873 | 0.908 | 0.908 | exploratory |
| person coverage agreement, canonical / variant | 0.990 / 0.961 | 0.991 / 0.974 | 0.990 / 0.974 | — |
| near-miss false covers | 2 | 11 | 48 | exploratory |
| every invariant | 0 | 0 | 0 | 0 |
| team-fit phase, 48 labs / 240 people × 150 calls | 33 s / 159 s | 33 s / 160 s | 33 s / 160 s | completes |

## 3. Figures

None.

## 4. Interpretation

- **The coverage logic is right; the reading of calls was the work.** Lab
  coverage on canonical names was ≥ 0.998 in every arm — the part that names
  people was never the problem. The misses were in turning prose into slots.
- **Arm A** asked what a call wants a team to *bring*, so the model often left
  out what the call *funds* (problem recall 0.51) and wrapped methods in
  "expertise in …". **Arm B** fixed both and then marked the funded problem as
  required in 87 of 112 slots — which the team-gap alert would have read as
  "your team lacks the topic this call funds". **Arm C** makes a problem never
  required, deterministically; required agreement is 0.978.
- **Variant names are the weak spot**, as EXP-2026-09-005 predicted (Q-043):
  0.908 lab agreement when a call names a method by a variant ("kriging") and
  the lab declares its canonical name.
- **Cleaner slots, more near misses.** Unwrapped slot names sit closer to
  neighbouring methods, and 48 slot–holder pairs were marked covered by a near
  miss at the shipped 0.80 cosine. At 0.85 there were none, but agreement on
  variant names and on problem and data slots fell slightly, which the
  pre-registered rule did not allow; the default stays at 0.80 (Q-044).
- **Scale is not a concern.** 43,200 (target, call) pairs marked in about 3
  minutes with no model call; a second pass changed nothing.

## 5. Threats to validity

- **Generator disobedience counts against the extractor** (ISSUES.md 2): 97 of
  98 unplanted slots are verbatim asks in the generated text.
- **Circularity** (the model read what it wrote) and **lexical problem
  matching** (ISSUES.md 3, 4) — problem recall is a floor.
- **Expected coverage by exact name** makes the variant buckets partly a test
  of the scorer (ISSUES.md 5).
- **A small real-data look, not a measurement:** 40 real calls from the
  development database (mostly Horizon Europe) were read with `s3` outside this
  experiment's protocol: 34 yielded slots, 6 were too thin, and partner
  requirements came back as roles. Some choices were debatable ("pollen" as a
  method, "SSH experts" as a partner rather than expertise). No numbers are
  claimed from it.

## 6. What surprised us

That the required flag got worse when everything else got better: asking for
"exactly one problem slot, what the call funds" made the model treat it as the
thing the call most requires. The fix was a rule, not a prompt.

## AMENDMENTS

None after the run. The three protocol amendments (PROTOCOL.md) were each
written before the arm they introduced.

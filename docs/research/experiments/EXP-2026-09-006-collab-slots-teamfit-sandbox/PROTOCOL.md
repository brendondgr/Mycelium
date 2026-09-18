# EXP-2026-09-006 — Protocol

Written 2026-09-18, before the planted-calls harness was built or run.

## Question

When funding calls are read by plan CN-03's slot extractor, do they become the
requirement slots that were planted in them — with the right facet and the
right "required" flag — and does the team-fit line then mark each slot covered
by the reader, covered by their lab, or a gap, the way the planted profiles
say it should?

## Hypothesis

- **H1 (invariants).** Zero: role slots marked covered; lab-mates named for a
  slot on anything but a declared edge; slots with a vector on a role; a second
  slot pass reading any call or calling the model.
- **H2 (slot extraction).** Over the planted method, problem and data slots:
  recall ≥ 0.85 and precision ≥ 0.80. Role slots: recall ≥ 0.80. Of matched
  slots, the `required` flag agrees with the plant ≥ 0.85.
- **H3 (coverage, the plan's bar).** For every (lab, call) pair, the covered /
  gap marking of each matched planted **method** slot agrees with the planted
  lab's declared methods ≥ 0.95 when the call names the method by its
  canonical name. Agreement on variant names is reported separately and is
  exploratory (EXP-2026-09-005's synonym splits, Q-043, predict it is lower).
- **H4 (near misses).** Exploratory: how often a slot for one planted method is
  marked covered by a person or lab holding only its near miss (Kalman filter /
  particle filter, random forest / gradient boosting) at the shipped
  `COLLAB_COVERAGE_COSINE` 0.80.
- **H5 (scale).** The team-fit phase for every lab (48) and every person (240)
  against every call (150) completes, and its wall clock is recorded.

## Setup

- System: `apps/collab` at the commit in `manifest.yaml` — `slots.py` (prompt
  `s1`), `coverage.py`, `team_fit.py`; the knowledge core as shipped by CN-01
  and CN-02 (merge threshold 0.92, prompt `w2`).
- World: EXP-2026-09-005's world (seed 20260918, 240 people) already seeded and
  read in `mycelium_sandbox` (re-linked at 0.92), so a person's papers count on
  their own card. The calls are added on top; nothing is re-seeded.
- Model and embedder: as EXP-2026-09-005 (`default-model`, relay upstream
  `gemma4-26B-mtp`; `BAAI/bge-small-en-v1.5` on CPU), for both writing the
  calls and reading them.

## Data

Synthetic. 150 planted calls (seed 20260918): each funds one problem from a
field's list, requires or welcomes one or two methods (70% by their canonical
name, 30% by a variant name), sometimes names data or a setting, and sometimes
requires a partner role. The local model writes each call's text from the
plan and is checked for naming every planted item; calls that fail are counted
and excluded from the extraction metrics. **Judgments are planted ground
truth, not human assessment.**

Expected coverage is computed from the planted world by exact name: a lab
covers a method slot if any member declares that method (their keywords and
skills are canonical method names); a person covers a method slot if they
declare it or published with it, and a problem or data slot if one of their
papers was planted with it.

## Metrics

Primary: **`coverage_agreement_lab_canonical`** — H3's number.

Also: slot recall and precision by facet (a planted slot is matched by an
extracted slot of the same facet whose text is the planted text after
normalising, or — for methods — names the same planted method by signature);
required-flag agreement; `coverage_agreement_lab_variant`;
`coverage_agreement_person` (canonical and variant); `near_miss_false_cover`
(count and rate); invariant counters; model calls; wall clock of slot reading
and of the team-fit phase.

## Baselines

None: the question is agreement with planted truth. The pre-registered bars
above are the comparison.

## Procedure

Inside the backend container, from `/app/web/backend`:

```bash
uv run --project . python -m sandbox.collab calls --people 240 --calls 150 \
  --out /app/data/sandbox/exp006.json
python3 docs/research/experiments/EXP-2026-09-006-collab-slots-teamfit-sandbox/code/analyse.py
```

## What would falsify this

- H1: any invariant counter non-zero.
- H2: method/problem/data recall < 0.85 or precision < 0.80; role recall <
  0.80; required agreement < 0.85.
- H3: `coverage_agreement_lab_canonical` < 0.95.
- H5: the phase does not finish.

## Amendment 1 — arm B (added after arm A, before arm B ran)

Arm A (prompt `s1`) ran as registered and **failed H2**: non-role slot recall
0.739 and precision 0.789 (bars 0.85 and 0.80); problem-slot recall 0.507. It
passed H1, H3 (0.998), H4 and H5. Reading its extractions showed three causes,
which arm B targets; arm A's numbers stay as recorded.

1. The prompt asked what a call wants a team to *bring*, so the funded problem
   was often left out or paraphrased.
2. Method slots came back wrapped ("expertise in finite element analysis").
3. Descriptions of activities were listed as methods ("rigorous data analysis
   with qualitative insights").

Arm B (prompt `s2`) asks for exactly one problem slot for what the call funds,
in its words; asks for methods by standard name; states that "welcome",
"encouraged" and "may" mean not required; strips a leading "expertise in" /
"experience in" / "knowledge of" deterministically; and refuses a method slot
made only of generic words. Same world, same generated calls (cached), same
bars. Also recorded for arm B: whether each extra (unplanted) slot names
something the generated call text itself asks for — the generator was told to
name nothing else, but a precision figure that counts the generator's own
additions against the extractor would be pessimistic.

```bash
uv run --project . python -m sandbox.collab calls --people 240 --calls 150 \
  --out /app/data/sandbox/exp006-arm-b.json
```

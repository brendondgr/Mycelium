# EXP-2026-09-019 — Protocol

Written 2026-09-19, before any run.

## Question

Ambient Plan 05 lets a confirmed exploration join a person's paper search as
an extra theme, down-weighted by `AMBIENT_DRIFT_WEIGHT` (default 0.15), behind
`AMBIENT_DRIFT_ENABLED` (off). Plan 10's experiment 8 asks for the ablation
before the switch is turned on. At which weights do the declared themes'
slates stay as they were, and does the exploration still bring its own papers
up?

## Why not the LongEval harness

The repository's rule is that ranking changes go through the eval harness
(`eval/`). That harness ranks **queries** against documents. It has no people,
so no confirmed explorations. With no exploration, the Plan 05 hook is
byte-for-byte inert, which the unit test
`test_without_exploration_weights_the_merge_is_byte_identical` pins. A harness
run "with drift on" would therefore be the same run twice and measure nothing.

The instrument that can see the effect is persona-level: the same person
ranked from the same corpus with and without their confirmed explorations, as
in EXP-2026-09-014. This protocol extends that to the weight sweep the plan
asks for. The owner may still want the harness run as a formality; it is
recorded as not run, with this reason.

## Hypotheses (pre-registered)

- **H1 (declared slates hold).** At the default 0.15, the mean Jaccard of each
  declared theme's slate with and without explorations is ≥ 0.95. The mean
  number of declared papers displaced from the top 25 is ≤ 1. (EXP-2026-09-014
  measured 0.98 and 0.14–0.17.)
- **H2 (monotone).** Declared-slate Jaccard does not rise, and displacement
  does not fall, as the weight rises through 0.05, 0.15, 0.30 and 1.0.
- **H3 (the exploration still works).** At every weight, the exploration's own
  papers lead its own slate (mean own-papers-at-top ≥ 0.75).
- **Decision rule, fixed now.** The recommended default is the largest weight
  that meets both H1 bars. If none does, drift stays off and the plan's
  proposal is revisited.

## Setup

- Database: `mycelium_sandbox_ambdrift`, a copy of `mycelium_sandbox_ambrep`
  (EXP-2026-09-017's end state). Six people there have a confirmed
  exploration, confirmed by EXP-2026-09-015's simulated answers.
- Corpus: the templated paper corpus from EXP-2026-09-014,
  `sandbox.ambient.nights.seed_corpus(world.POOL)`: 158 topics × 4 papers,
  embedded on the CPU.
- Measurement: `sandbox.ambient.nights.drift(world, weights=(0.05, 0.15, 0.30,
  1.0))`, unchanged from EXP-2026-09-014.

## Procedure

```bash
docker compose exec -T backend sh -c 'cd /app && export DATABASE_URL=${DATABASE_URL%/*}/mycelium_sandbox_ambdrift && \
  uv run --project web/backend python web/backend/manage.py shell < docs/research/experiments/EXP-2026-09-019-ambient-drift-weight-ablation/code/run.py'
```

Budget: under 30 minutes.

## What would falsify this

H1 failing at 0.15 means the default is too heavy. H2 failing means the weight
is not the lever it is assumed to be.

# EXP-2026-11-002 — Protocol

Written 2026-11-05, after one exploratory run of the metrics command to check it
works (ISSUES.md) and before any number below was read for a decision or any
lab-fit label was assigned.

## Question

Before any announcement threshold is tuned (plan Phase 8), what do the measures
read on the only data with announcement activity, and does the department path's
lab-fit floor separate labs that suit a call from labs that do not?

## Hypothesis

Exploratory for the engagement measures (Interested, Remind me, Not for us, link
clicks, route health): there are no real users yet, so this is a baseline and a
test of the instrument, not a finding about people.

One stated expectation for the department path: bge-small cosines between a lab
profile and a call are compressed into a narrow band, so the lab-fit floor (0.45,
`LAB_FIT_COSINE_FLOOR`) admits every department-level call for every lab and does
not discriminate.

## Setup

- System: the announcement path on branch `mylo-announcements` (Phases 1–7), the
  department detector `dept_level.py` v2, lab-fit `lab_fit.py` (stored lab vector
  if any, else the lab's canonical profile text embedded by the item model
  `BAAI/bge-small-en-v1.5`), and the new read-only `announce_metrics.compute`.
- Held fixed: every threshold at its committed default.

## Data

- Database copy `mycelium_ann` (a `pg_dump` of the dev database taken 2026-11-05;
  opportunity corpus collected 2026-08/09), after the Phase 4–7 smoke runs in the
  Discord **test** server. Its reactions were made by the implementer while
  testing, not by researchers. Every engagement number is labelled so.
- Department: Department of Scientific Computing (simulated FSU roster, one lab
  with a profile: PULSE Lab), scored against the full opportunity corpus on
  2026-11-05.
- Lab-fit judgments: for each department-level call among the department's
  scored rows, whether it suits PULSE Lab (scientific machine learning, ocean
  forecasting, deep-learning surrogates), labelled by the implementing agent
  (Claude), **not a person**, from the call's title and description.

## Metrics

- Engagement, per target (window 2026-11-05): `interested_rate` = posts with at
  least one Interested / posts; `remind_rate` = posts with at least one Remind me
  / posts; `not_for_us_rate` and its reasons; web `link_clicks` by surface; route
  health = announcement routes ok / failing / unchecked across active bindings;
  held-back reasons grouped by check.
- Department yield: `slate_dept_level_rate` = department-level rows / rows on the
  department's live slate; the same over all scored rows.
- **Primary (department):** lab-fit precision at the committed floor = calls
  labelled as suiting the lab / calls the floor admits for it. Secondary: the
  lowest "suits" score against the highest "does not suit" score (whether any
  floor separates them).

## Baselines

None exist: this is the first measurement. The committed floor is the reference.

## Procedure

```bash
# 1. The measures, as JSON
DATABASE_URL=postgres://mycelium:mycelium@localhost:11450/mycelium_ann \
  uv run --no-sync --directory web/backend python manage.py announcement_metrics \
  --since 2026-11-05 --until 2026-11-05 \
  --json ../../docs/research/experiments/EXP-2026-11-002-announcement-baseline/data/metrics.json
# 2. Label data/labfit_labels.csv (suits: yes | no), one row per department-level
#    call, scores from lab_fit.rank(floor=-1)
# 3. Tables and derived numbers from the two files above
uv run --no-sync --project web/backend python \
  docs/research/experiments/EXP-2026-11-002-announcement-baseline/summarize.py
```

## Decision rule

- No engagement threshold (strong-match fit, nudge defaults, caps) changes on
  this data: none of its reactions came from real users.
- Lab-fit floor: changed only if the labelled scores show a floor that separates
  "suits" from "does not suit" **and** the labels cover more than one lab.
  Otherwise the floor stays and the gap is recorded as an open question.
- Department yield below 0.25 of the slate is reported to the product owner as a
  plan-level question (it would change which items a department considers), not
  tuned here.

## What would falsify this

Any labelled "does not suit" call scoring below the floor, or a clean gap between
the two groups, would refute "the floor does not discriminate".

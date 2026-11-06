# EXP-2026-11-001 — Protocol

Written before any label was assigned (2026-11-05).

## Question

When `apps/content/dept_level.py` says an opportunity is a call only a department
can take on, how often is it right — precision per reason, over every record it
fires on in the corpus snapshot?

## Hypothesis

Exploratory, with one stated expectation: the activity-code rule for
department-scale programmes (NIH T32/T35/T34/R25/P30/P50/U54/S10) is near-exact,
while the free-text institutional-selection patterns misfire on per-investigator
or per-project limits, which also say "no more than N".

## Setup

- System under test: `apps/content/dept_level.py` as committed with this
  experiment (detector **v1**), function `reasons(metadata)`.
- Reasons: `institutional_selection`, `department_applicant`,
  `department_programme`, as defined in the module docstring and in the plan
  (`docs/plans/20261105-mylo-opportunity-announcements.md`, "What a department
  sees"). Fit to two or more labs is not a reason.
- Nothing else is held fixed: the detector is pure over a record's metadata.

## Data

- Collection: every grant, fellowship and conference `ContentItem` in the dev
  database copy `mycelium_ann` (a `pg_dump` of the dev database taken
  2026-11-05; the opportunity corpus was last collected 2026-08/09). 3,901 records.
- Sample: **every** record the detector fires on (not a random subset), so
  precision is measured on the full positive set of this snapshot.
- Judgments: assigned by the implementing agent (Claude), **not a human**, by
  reading the matched sentence and, where it is ambiguous, the record's
  eligibility text. This is stated next to every number in RESULTS.md. A human
  relabel is an open item in ISSUES.md.

### Labelling rubric

A row is **correct** when the record itself shows the reason:

- `institutional_selection`: the funder limits how many applications or
  nominations one **institution / organisation / campus** may make, or requires
  an institutional nomination. A limit per PI, per project, per company or per
  technology is **not** institutional selection.
- `department_applicant`: the applicant or award holder must be a department,
  school or academic unit (or the department head as PI), not an individual
  investigator's group.
- `department_programme`: an institutional training programme, a centre with a
  lead institution, or a shared instrument or facility run for the unit.

Anything else is **incorrect**. A row whose evidence is too thin to decide is
**unclear** and counts as incorrect for precision.

## Metrics

- **Primary:** precision per reason = correct / fired. A record firing two
  reasons contributes one row per reason.
- Secondary: overall precision over all rows; number fired per reason.
- Recall is not measured (no labelled negatives); this is stated as a limit.

## Baselines

None: there is no prior detector. The decision threshold below is the bar.

## Procedure

```bash
# 1. Dump every firing (reason, evidence, eligibility excerpt) to data/labels.csv
DATABASE_URL=postgres://mycelium:mycelium@localhost:11450/mycelium_ann \
  uv run --project web/backend python \
  docs/research/experiments/EXP-2026-11-001-dept-level-precision/score.py dump
# 2. Label each row in data/labels.csv (label: correct | incorrect | unclear)
# 3. Compute metrics into data/metrics.json and data/metrics.csv
uv run --project web/backend python \
  docs/research/experiments/EXP-2026-11-001-dept-level-precision/score.py score
```

## Decision rule

- A pattern that produces an incorrect row is **removed** from the detector, not
  tuned to pass (plan rule). The removal is recorded in RESULTS.md and the
  detector version bumped to v2; v2's precision on the same sample is reported
  separately and marked as measured on the sample that motivated the removals.
- Departments switch on only if every reason's v2 precision is **≥ 0.90** with at
  least one correct row; a reason below that is disabled.

## What would falsify this

Activity-code precision below 0.90 would refute the expectation that the code
rule is near-exact; institutional-selection precision of 1.0 on v1 would refute
the expectation that free text misfires.

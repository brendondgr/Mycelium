# EXP-2026-09-020 — Protocol (pre-registered; not yet run)

Written 2026-09-19, before any pilot exists. This is ambient Plan 10's go/no-go
(its step 13) and its three pilot experiments (steps 6, 7 and 10). Every bar
below is fixed now, so the pilot cannot tune it.

The thresholds were set by the implementing agent overnight, on the owner's
instruction to make these calls. **The owner confirms or changes them before
the pilot starts.** A change after the pilot starts is an amendment and
voids the go/no-go.

## Pilot (OD-10a, adopted as recommended)

One lab, four weeks, every member consenting individually. Stage A only:
DMs to Mylo and messages that mention it, with server listening off. Paid
tier, linked accounts. The product runs as shipped: `AMBIENT_ENABLED` on,
`AMBIENT_DELIBERATE_ENABLED` on, `AMBIENT_DRIFT_ENABLED` off (see experiment 7
for how drift is compared).

## Prerequisites (before day 1)

- Q-049: reader r5 re-measured on a fresh sandbox seed, registered, with a
  harm rate of at most 1%. Otherwise free-text answers are turned off for the
  pilot and only buttons are read.
- Q-053 answered before drift is compared in experiment 7.
- `evaluate_ambient` reads zero on the pilot database on day 1.

## 1. Extraction on Stage A data (Plan 10 experiment 6)

- **Sample:** 100 observations drawn at random from weeks 1–2, stratified by
  understanding kind.
- **Labels:** each hand-labelled by the author and one lab member, blind to
  each other, for grounded (the summary is supported by what was said in the
  window) and force (said as a fact, a plan, a preference, or musing). Because
  the buffer is deleted after reading, labels are taken the same night, from
  the window before it is released. A labelling window is added for the pilot
  only, and its text is deleted with the buffer.
- **Bars:** grounded precision ≥ 0.90; force accuracy ≥ 0.80; inter-rater
  agreement (Cohen's κ) reported.
- **Gate:** Stage B (server listening) waits on both bars.

## 2. Validation precision (Plan 10 measure 1, the primary number)

- From `ValidationRecord` over the four weeks (`evaluate_ambient --days 28`).
- **Bars:** at least 0.70 yes, among yes-or-no answers, for
  `enduring_interest` and for `project_development`. Each needs at least 20
  answers, or it is inconclusive.
- A kind below 0.50 stops being asked after the pilot, whatever the go/no-go
  says.

## 3. Personalization replay (Plan 10 experiment 7)

- For each participant and week: rank twice from the same corpus, declared
  profile only and declared plus confirmed explorations at weight 0.15. List
  the items that differ.
- One extra Plan 06 question that week, opt-in, asks which of up to five
  differing items were more useful and which assumptions were wrong.
- **Bar:** a majority (> 50%) of the participants who answer prefer the
  context arm. At least 5 must answer, or it is inconclusive. The list of
  wrong assumptions is recorded in full.

## 4. Question budget (Plan 10 experiment 10)

- Weeks 1–2 at one question a week per person, weeks 3–4 at two.
- **Reported:** answer rate and validation precision per arm.
- **Rule:** keep two a week if the answer rate drops by no more than 15
  percentage points and precision by no more than 0.10. Otherwise one.

## Go / no-go (Plan 10 step 13)

**Go** past the pilot only when all three hold:
1. both kinds clear the validation-precision bar in §2;
2. every harm check reads zero on every nightly run of the pilot;
3. the replay shows a majority for the context arm (§3).

Otherwise:
- **hold:** Stage B stays off;
- the DM and mention paths stay on;
- the floors are revised using this experiment's data;
- the pilot repeats after the revision.

An inconclusive section counts as not met.

## Recording

- Every nightly `evaluate_ambient` goes to `data/` as JSON: counts and ids
  only.
- The dataset export (`export_ambient_dataset`) stays outside the repository.
  Only its manifest and aggregates are stored here.
- Failed nights and withdrawn consents are recorded, not dropped.

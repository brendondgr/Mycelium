# Protocol — Alert precision, and the thresholds it sets

Written before the run. Nothing below has been executed.

## The question

Three of the five project-alert triggers rest on a raw-cosine similarity against
a threshold (`overlap_risk`, `unblocks`, `team_gap` — see
`apps/content/matchers/`). The thresholds currently in `settings.py` were chosen
by nobody: they are placeholders, and `PROJECT_ALERTS_ENABLED` ships **off**
precisely because a similarity threshold set by taste fires constantly or never,
and both teach a reader to stop opening the report.

**What threshold for each trigger maximises alert precision at a usable recall,
and is any of the three good enough to enable at all?**

The two remaining triggers (`timeline`, `deadline_moved`) are arithmetic over
stored dates. They are not in scope and already run.

## The measure

**Alert precision** = the share of fired alerts the reader acted on, where
acting is *saved or opened within seven days* and not acting is *dismissed, or
untouched at seven days*.

This is a weak label and is recorded as one. It is what the product can observe
without asking anybody anything, and the alternative — a labelling exercise over
somebody's own research — costs a researcher an afternoon per fifty alerts and
cannot be repeated when a threshold moves. The bias is known and stated: an
alert a reader agreed with but had no time to act on reads as a false positive,
so the measure is **pessimistic**, which is the safe direction for a decision
about whether to interrupt people.

Secondary: **fire rate** — alerts per target per week at each threshold. A
threshold with perfect precision that fires twice a year is not usable, and the
daily cap (3) means a threshold that fires eight times a day is really a
threshold that fires three times and holds five.

## Method

1. **Shadow run.** With `PROJECT_ALERTS_ENABLED` off, run
   `evaluate_project_alerts` nightly with the three similarity thresholds set to
   a floor low enough to admit everything worth considering (0.35), writing
   every candidate and its computed score to the alert row's `evidence`. Nothing
   is delivered: the rows are written with `status=held`, and no notification or
   Discord message is produced.
2. **Accrue for four weeks.** Long enough for the seven-day action window to
   close on at least three weeks of alerts.
3. **Join.** For each shadow alert, read `SavedOpportunity`, `ProjectItemSeen`
   and `IgnoredItem` for that (target, item) pair within seven days of
   `fired_on`.
4. **Sweep.** For each trigger independently, compute precision and fire rate at
   thresholds 0.35 → 0.80 in steps of 0.01.
5. **Choose.** Per trigger, the lowest threshold whose precision clears the bar
   below, or *no threshold* if none does.

## The bar, stated before the numbers exist

A trigger is enabled only if some threshold gives **precision ≥ 0.5** at a fire
rate of **at least one alert per target per fortnight**.

Half is not an arbitrary round number: below it, a reader is more often wrong
than right to trust the interruption, and an alert that is wrong half the time
is worse than no alert because it also devalues the ones that are right. The
fire-rate floor exists so a trigger cannot buy precision by never firing.

A trigger that clears neither stays off, and that is a real and acceptable
outcome — `timeline` and `deadline_moved` carry the feature on their own.

## What would make this wrong

- **Cold start.** A project with no stated claim produces no `overlap_risk`
  candidates at all, so the measure is over projects that have described
  themselves. If fewer than ten such projects exist at the end of the window,
  the run is abandoned rather than reported, and this file says so.
- **The weak label.** See above. If precision lands near the bar rather than
  clearly on one side, the decision is deferred and a hand-labelled sample is
  scoped instead — a near-miss on a pessimistic weak label is not evidence.
- **One reader's taste.** Precision aggregated over very few readers measures a
  person, not a threshold. Reported per-reader as well as pooled.

## Entrypoint

Not yet written. It will be `code/run.py` in this folder, reading the shadow
alert rows through the ORM and writing `data/metrics.json` and
`data/metrics.csv`; `figures/make_figures.py` will read those files and nothing
else.

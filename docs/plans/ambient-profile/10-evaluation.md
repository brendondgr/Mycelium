# Plan 10 — Evaluation: Is Mylo Making Correct Changes?

**Status:** draft. **Depends on:** Plans 05–09. **Unblocks:** tuning of every
floor, cap, and half-life; Stage B of Plan 02.
**Correlation ID:** `20260917-ambient-profile-10`

## Objective

Answer, with numbers in the research record, whether the ambient profile makes
the recommendations better and whether the changes it proposes are ones people
agree with. If it does not, the record says so and the floors are raised or the
feature is held. Every run below follows `docs/research/AGENT_INSTRUCTIONS.md`:
scaffold with `make new-experiment`, fill `PROTOCOL.md` first, record failed
runs, never quote a metric that is not in `manifest.yaml` and `RESULTS.md`.

## Measures

1. **Validation precision** (from Plan 06's `ValidationRecord`): the share of
   asked findings that were `confirmed`, by understanding kind, by force, by
   source path (DM, mention, server listening), and by lab. This is the
   primary number. A kind whose precision is low gets a higher floor or stops
   being asked.
2. **Attribution accuracy** (from Plan 03's corrections and a hand-labelled
   sample): correct project, unresolved when it should be, wrong project.
   Wrong project is the cost that matters.
3. **Recommendation usefulness** (from `RelevanceEvent`): save, open, thumbs,
   and dismiss rates on items whose ranking or explanation used ambient
   context versus items that did not, within the same person and week.
4. **Maintenance burden**: profile edits per person per month before and after;
   questions asked versus answered; undo rate on confirmed changes.
5. **Harm checks**: stated fields changed by any automatic path (must be zero);
   any non-certain-tier change applied without a confirmation record (must be
   zero); personal observations in lab packets (must be zero); ambient
   questions over the daily cap (must be zero); raw text or verbatim
   fragments found anywhere outside the transient buffer (must be zero);
   observations surviving an opt-out deletion (must be zero); observations
   for any free-effective-tier or unlinked person (must be zero); a declined
   topic asked again inside 30 days (must be zero); a covered topic asked at
   all (must be zero); any observation or explanation with `origin = rule`
   (must be zero).

## Experiments

6. **EXP: extraction on Stage A data.** Before any server listening, run the
   extractor over DM and mention windows from consenting pilot users. Hand-label
   a sample for grounding and force. Report precision of observations and the
   refusal rate. Gate: Stage B of Plan 02 waits on this.
7. **EXP: personalization replay.** For each pilot person and week, rank twice
   from the same corpus: declared profile only, and declared plus evolving
   context. Compare the slates, then ask the person (through the Plan 06
   dialogue, one extra question that week, opt-in) which of the differing
   items were more useful and which assumptions were wrong. Record per-person
   preference and the wrong-assumption list. This is the replay the README
   describes and the closest thing to a ground truth we have.
8. **EXP: drift blend ablation.** The eval harness on the declared-only arm and
   on the drift arm at three cap values, per the global rule for ranking
   changes. Numbers into the changelog and the experiment folder.
9. **EXP: attribution floor and margin.** Sweep against the labelled sample;
   pick the operating point that minimises wrong-project attributions at an
   acceptable unresolved rate.
10. **EXP: question budget.** Answer rate and precision at one versus two
    questions per week for the pilot group.

## Instrumentation

11. `ValidationRecord`, `ObservationFeedback`, and the reasoning trace are
    exportable as a dataset. Personal text is limited to Mylo's summaries
    and explanations — no message text exists to redact — and speaker ids
    are hashed. The research folder stores the manifest and aggregates only.
12. `run_analytics.py` gains ambient counters: windows, observations by kind
    and origin, suggestions, confirmations, proposals, questions asked and answered, undo.

## Go / no-go

13. Proceed past the pilot when validation precision for enduring-interest and
    project-development findings clears a threshold set in the protocol before
    the run, the harm checks are zero, and the replay shows a majority
    preference for the context arm. Otherwise hold Stage B, keep the DM and
    mention paths, and revise floors.

## Open decisions

- **OD-10a** Pilot size and duration. Recommendation: one lab, four weeks,
  every member consenting individually.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.

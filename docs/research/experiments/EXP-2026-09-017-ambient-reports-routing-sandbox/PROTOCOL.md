# EXP-2026-09-017 — Protocol

Written 2026-09-19, before any report was generated for this experiment.

## Question

Ambient Plan 09 routes what changed into reports. Does each change reach the
right reports and no others?
- A personal change goes to that person only.
- A change on a lab project the lab shares goes to the lab weekly and to each
  project member's weekly, once each.
- A change on an unshared lab project goes to its members only.

Does every `[O#]` resolve? When the real model writes the weekly, does it use
`[O#]` to say why an item matters now, and does the verifier keep only the
citations that resolve? Do the dailies carry the "Changed today" lines exactly
where they should?

## Hypotheses (pre-registered)

- **H1 (routing, zero violations).** Over every weekly generated:
  - (a) no change whose visibility is personal, and no personal-kind change,
    appears in any lab weekly or in anyone else's weekly;
  - (b) each lab-visible change on a shared project appears exactly once in
    that lab's weekly "What changed" and exactly once in each project member's;
  - (c) a lab-visible change on an unshared project is absent from the lab
    weekly and present once in each member's;
  - (d) no one who is not a member of the project sees a project change.

  Presence is counted as `[O#]` rows in the "What changed" section, matched on
  the change's topic.
- **H2 (citations).** Every `[O#]` in every stored body resolves to a row of
  that body's "What changed". The verifier's removal count is reported.
- **H3 (interpretation line).** With `AMBIENT_DRIFT_ENABLED` off it appears in
  no weekly. With it on, it appears in exactly the weeklies of people with a
  confirmed, not-undone exploration this week.
- **H4 (dailies).**
  - A person's daily carries "Changed today" iff they have a profile or
    stated-state edit, or an alert-changing development, in the last 24 hours.
  - A lab daily carries only stated-state edits on its shared projects.
  - No lab daily carries a development line (OD-09a).
- **H5 (budget).** Under 60 minutes; at most 8 concurrent model calls.

Reported without a bar:
- how many model-written sentences cite `[O#]`, and how many of those survived;
- ten of them, read by the author for whether the link is real.

## Setup

- Database: `mycelium_sandbox_ambrep`, a copy of `mycelium_sandbox_ambweb` as
  EXP-2026-09-016 run 4 left it. Its real changes: 6 profile edits (1 undone),
  6 confirmed explorations, 6 confirmed understandings, 18 personal told
  facts, 1 lab told fact, and 1 accepted stated-state edit.
- `code/run.py` plants, through the real recorder (`review.record`):
  - Projects A1, B2 and C1 marked shared, and A2, B1 and C2 not shared;
  - one lab-visible told fact on each of the six projects, spoken by a member.

  It then generates, with the real model (`weekly_report` component, 8
  threads), the weekly for every `amb_` person and every `amb-` lab, dated
  2026-09-19 (week of 14 Sep). It generates it again with drift on for the
  people H3 names, and the dailies with the model off (the fallback prose,
  since only the frame is under test).
- Checks are computed from the stored bodies and the change rows, never from
  the builder's own lists.

## Procedure

```bash
docker compose exec -T backend sh -c 'cd /app && export DATABASE_URL=${DATABASE_URL%/*}/mycelium_sandbox_ambrep && \
  uv run --project web/backend python web/backend/manage.py shell < docs/research/experiments/EXP-2026-09-017-ambient-reports-routing-sandbox/code/run.py'
```

## What would falsify this

Any H1, H2, H3 or H4 violation.

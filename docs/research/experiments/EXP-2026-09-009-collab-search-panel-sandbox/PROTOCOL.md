# EXP-2026-09-009 — Protocol

Written 2026-09-18, before the panel harness (`sandbox.collab panel`) ran
against any world, and before any browser run.

## Question

Does plan CN-06's collaborator search work end to end through the real API
for hundreds of fake seekers — from a funding call, from their lab's project,
and from their own words — and does every response stay a coarse pointer,
with each path that must not offer a search refusing?

## Hypothesis

- **H1 (invariants, API).** Zero, over every search: a response with keys
  beyond `slots, lanes, groups, explained, search_id`; a found person carrying
  a field beyond the coarse pointer (`username, name, institution, lane, slot,
  facet, matched, tier, reason`); a person the gate (re-derived from the plan)
  would refuse; a tier other than declared or demonstrated; a lane returned
  that was not asked for; groups that are not an exact partition of the lanes
  (fills a gap = method bridge, problem bridge, resource; shares expertise =
  in field); any count of people held back; a dry run that logs a search or
  returns more than slots; a slot vector in any response; the sent slots not
  being the ones searched.
- **H2 (refusals).** Zero wrong answers on: flag off (availability
  `not_enabled`, search 404); unverified seekers (`unverified`, 403); the free
  plan while plans are enforced (`paid_plan`, 403); the daily limit
  (`daily_limit`, 403); a scope beyond the launch limit (403); a project the
  seeker cannot open (refused iff the real visibility rule says hidden).
- **H3 (saved list).** A saved person is listed; the same person is gone from
  the list once they switch collaboration off.
- **H4 (latency, exploratory).** p50/p95 per entry point, model on.
- **H5 (browser).** At 1280×800 and 390×844, against a second backend on the
  sandbox database: the grant card's "Find collaborators" opens the panel with
  the call's chips and coverage marks; Run shows the two groups as separate
  sections; the project page's Collaborators tab opens it pre-filled; the ⌘K
  palette opens it with the typed words; no horizontal scroll at phone width;
  no console errors. Checked by screenshots and DOM assertions.

## Setup

- System: the commit in `manifest.yaml` (CN-06 panel and endpoints; CN-05
  matcher at lane cosines 0.70 / 0.55, three places per lane).
- World: EXP-2026-09-008's 600-person world (`seed 20260918`), consent matrix
  planted by EXP-2026-09-007's code; 150 planted calls seeded, requirements
  read by the model for 30 of them.
- Seekers: 120 verified people with a lab, sampled with a fixed seed; each
  searches from a call and their lab's project, and every fourth also from
  their own words (read by the model). A third of searches with results save
  the first person.
- Model: `default-model` on the relay (upstream `gemma4-26B-mtp`) for slot
  reading and the rerank.

## Procedure

```bash
cd web/backend
uv run --project . python -m sandbox.collab panel --people 600 --budget-minutes 45 \
  --seekers 60 --rerank-seekers 10 --read-calls 20 --out /app/data/sandbox/exp009.json
```

Then the browser check: a second backend container on the sandbox database
(its own Redis database, so nothing it queues reaches the development worker)
and a second web container proxying to it (its own `.next`), driven by
Playwright from the host (`code/browser_check.py`).

## What would falsify this

Any H1, H2 or H3 violation; in the browser, any failed H5 assertion.

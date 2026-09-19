# EXP-2026-09-010 — Protocol

Written 2026-09-18, before the graph harness (`sandbox.collab graph`) ran.

## Question

On the 600-person synthetic world, do plan CN-07's graph features name only
who they may and find what they should: introduction paths, "outside my
network", team formation, and searches at country and anywhere scope?

## Hypothesis

- **H1 (invariants).** Zero: the co-authorship table differing from the
  planted edge list; an introduction path whose consecutive people did not
  co-author in the planted graph; an intermediary who is not open, is
  expired, or whose audience excludes the seeker; an introduction path longer
  than a brute-force shortest path through the same allowed people, or
  missing when one exists (≤ 3 hops); a person returned with
  `outside_network` who is within two co-authorships of the seeker; a team
  member the gate (re-derived from the plan, planted co-authors included)
  would refuse; a search result at country or anywhere scope outside
  audience ∩ scope.
- **H2 (team quality).** Team cover precision — the member holds the planted
  method they are listed as covering — ≥ 0.80 (the same bar as CN-05's
  method-bridge precision, since it is the same matching). Reported, no bar:
  share of gaps covered; gaps listed as uncovered while an eligible person
  holds the method (a recall miss, not a leak).
- **H3 (exploratory).** Share of shown candidates with an introduction path;
  mean path length; mean team size; latency of each.

## Setup

- World: EXP-2026-09-008's 600-person world and consent matrix. The world's
  co-authors are only lab-mates, so the harness plants cross-lab co-authorship
  first: 400 extra two-author works between people of different labs
  (fixed seed), written as `AuthorWork` rows through the real models, then
  `rebuild_coauthorship`. The planted edge list is the brute-force reference.
- Seekers: every lab lead (verified), searching from their lab's project at
  institution scope; introductions asked for every person shown; teams
  assembled for a three- to four-method need drawn from other fields' planted
  methods; `outside_network` searches for the same projects.
- Scope checks: the same searches at country and anywhere scope with
  `COLLAB_MAX_SCOPE` raised inside the harness only.
- Model: none. The rerank is switched off (the harness passes a model that
  is unavailable, so every shortlist stands unexplained): it can only drop a
  person and is not what is tested here, and 400 model-reranked searches
  would take hours. Teams and paths never use a model.

## Procedure

```bash
cd web/backend
uv run --project . python -m sandbox.collab graph --people 600 \
  --out /app/data/sandbox/exp010.json
```

## What would falsify this

Any H1 violation.

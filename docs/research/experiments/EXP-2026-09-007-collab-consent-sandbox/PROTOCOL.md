# EXP-2026-09-007 — Protocol

Written 2026-09-18, before the consent harness was built or run.

## Question

Across a synthetic population, does plan CN-04 ever make a person findable, or
reveal anything about them, that their own settings and verified email do not
allow — and does the appearance cap actually spread exposure away from the
most sought-after people?

## Hypothesis

Everything but the cap's effect is an invariant: it must be exactly right.

- **H1 (verified scope).** Every person's derived institution and country
  equal the planted ones (accuracy 1.0); personal-address people have no
  institution; unverified people have no affiliation at all.
- **H2 (mutual visibility).** For every (seeker, candidate, seeker scope)
  triple, `consent.mutually_visible` agrees with an independent reference
  written from the planted world (disagreements = 0).
- **H3 (refusals and expiry).** Every attempt to choose an audience the
  person's verified email does not support is refused; every planted expired
  setting reads as closed with no job run (violations = 0).
- **H4 (preview).** No opted-in person's preview lists a concept they hold
  only through conversation (confirmed or pending) or only through a project
  (violations = 0), and every listed concept is one they hold through a
  declared or demonstrated edge.
- **H5 (appearance cap).** In a simulated week of searches no candidate is
  shown to more distinct seekers than `COLLAB_APPEARANCE_CAP` (violations =
  0). Exploratory: the Gini coefficient of distinct seekers per candidate with
  the cap, against the same searches without it.

## Setup

`apps/collab` at the commit in `manifest.yaml` (`affiliation.py`,
`consent.py`, `preview.py`) on EXP-2026-09-005's world in `mycelium_sandbox`
(240 people, their declared and demonstrated edges, 48 lab projects with
declared edges). No model is called; the embedder is used only to link the
planted conversational edges.

## Data

Synthetic, seed 20260918. Planted on top of the world: 10% of people moved to
a personal email domain, 5% unverified; 40% of the rest open to
collaboration (audiences 40% institution, 30% country, 30% anywhere; open-to
types at random); 10% of the open settings already expired; for 30% of people
a confirmed and a pending conversational edge on a topic they hold nowhere
else. The search week: 2,000 searches by random seekers at random scopes,
with seekers drawn toward popular candidates by a Zipf weight (s = 1.2), each
returning every mutually visible open candidate that passes the cap.
**Judgments are planted ground truth.**

## Metrics

Primary: **the sum of all violation counters** (H1–H5), which must be 0.
Also: scope accuracy; triples checked; refusals attempted; previews checked;
Gini of distinct seekers per candidate with and without the cap; share of
search results the cap withheld.

## Baselines

The reference implementation (H2) and the same search week without the cap
(H5).

## Procedure

```bash
uv run --project . python -m sandbox.collab consent --people 240 \
  --out /app/data/sandbox/exp007.json
```

## What would falsify this

Any violation counter above zero.

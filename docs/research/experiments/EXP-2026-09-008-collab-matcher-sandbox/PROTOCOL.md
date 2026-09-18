# EXP-2026-09-008 — Protocol

Written 2026-09-18, before the 600-person world was built or any search ran.

## Question

At 600 people, does plan CN-05's matcher return, in the method-bridge lane,
people from another field who really use the method a project needs — and
never anyone the gate should have kept out, anyone found only through
conversation, or anyone the model invented?

## Hypothesis

- **H1 (invariants).** Zero: returned people who fail the gate re-derived from
  the plan (closed, expired, outside audience ∩ scope, lab-mate, co-author,
  the seeker); returned rows whose evidence tier is not declared or
  demonstrated; people returned for a method they hold only through a
  confirmed conversational edge; any person above the weekly cap in the load
  run.
- **H2 (method bridge).** Over every project method slot that has at least one
  eligible person in another field who used or declared the method: hit rate
  (at least one such person in the lane's three places) ≥ 0.80, and precision
  of method-bridge rows (the person really holds the named method and sits in
  another field) ≥ 0.80. Reported at institution scope (launch) and at
  anywhere scope.
- **H3 (in-field).** Exploratory: precision of in-field rows (same field, a
  paper on the project's problem).
- **H4 (problem bridge).** Exploratory: the world's problems are field-specific,
  so every problem-bridge row is a false bridge; report the count.
- **H5 (load).** 300 searches with the model off: p95 latency ≤ 2 s; the cap
  holds; Gini of distinct seekers per person with and without the cap.

## Setup

- System: `apps/collab` matcher at the commit in `manifest.yaml` (lane match
  cosine 0.70, differ 0.55, shortlist 8, three places per lane), on the
  knowledge core as shipped (merge 0.92, works `w2`).
- World: `sandbox.collab.world.build(seed=20260918, people=600)`, seeded and
  read by the real pipeline (`all`), then EXP-2026-09-007's consent matrix
  planted by the same code, plus a confirmed conversational `uses_method`
  edge on an unheld method for 5% of people.
- Model: `default-model` (relay upstream `gemma4-26B-mtp`) writes the papers,
  reads them, and reranks the quality runs; the load run turns the model off.

## Data

Synthetic; planted ground truth. The quality run: each lab's lead searches
from their lab's project (its problem, stated methods, data and uncovered
need). Truth for a method slot is the set of eligible people (gate re-derived
from the plan) in another field whose planted methods include it.

## Metrics

Primary: **`method_bridge_hit_rate`** at institution scope. Also: method-
bridge precision and recall@3; in-field precision; problem-bridge rows;
every violation counter; latency p50/p95 (model on in quality runs, off in the
load run); Gini and maximum distinct seekers with and without the cap.

## Baselines

The load run without the cap; none for quality (the question is agreement
with planted truth).

## Procedure

```bash
uv run --project . python -m sandbox.collab all --people 600 \
  --out /app/data/sandbox/exp008-world.json
uv run --project . python -m sandbox.collab match --people 600 \
  --out /app/data/sandbox/exp008.json
```

## What would falsify this

H1: any violation. H2: hit rate or precision below 0.80 at institution scope.
H5: p95 above 2 s, or any cap violation.

# EXP-2026-11-015 — Protocol

Written 2026-11-12, before the recorded pass (one dry pass checked the script
first; see ISSUES.md).

## Question

How much is the live Mycelium instance used? Descriptive only; no claim.

## Hypothesis

None — a descriptive snapshot. Usage is expected to be small (one lab's
early deployment); the point is to state it, not to make it look larger.

## Setup

`code/snapshot.py`, run once in a one-off backend container against the live
database, read-only, counts only. No name, username, email or message text is
read out.

## Data

The live instance's own tables, as of the run time recorded in
`data/metrics.json`.

## Metrics

- Accounts (real; the public demo's six fictional people counted separately),
  active, email-verified (`Profile.is_verified`), staff; labs; departments;
  labs with a real member.
- People active in the last 7 and 30 days: logged in, sent Mylo a message,
  gave feed feedback (`RelevanceEvent`) or saved an opportunity.
- Mylo threads and turns (user messages) created in the last 30 days, by
  surface (web, Discord, demo). Demo threads are deleted after 24 hours, so
  demo threads under-count; demo questions are counted from `DemoQuestion`.
- Demo: first question, total questions, distinct visitor cookies, distinct
  hashed addresses.
- Nightly runs in the last 30 days, measured two ways: days with daily
  briefings written, and run-analytics reports in `data/analytics/`.
- Corpus items by type.

Threads created by this session's experiments (`demo_visitor` starting
`EXP-`) are excluded from every usage count.

## Baselines

None.

## Procedure

```bash
docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
  python docs/research/experiments/EXP-2026-11-015-deployment-usage-snapshot/code/snapshot.py
```

## What would falsify this

Not applicable (descriptive). A count that cannot be computed is reported as
unknown, never estimated.

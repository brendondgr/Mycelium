# EXP-2026-11-005 — Protocol

## Question

What share of the live conference corpus gets (a) a location line that names a
country and (b) a continent forum tag, before and after `geography.place_for`?

## Hypothesis

Stated 2026-11-08 before the run. Before: about 42% of conferences have a
continent (only the 380 or so with a structured country code; counted in a
read-only survey while planning). After: at least 70% get a continent, because
most of the place-text-only records end in a country, a US state, or a common
alias. Every record whose `city` holds a venue name shows its full `place_text`.

## Setup

`tools/retrieval/geography.py` on branch `discord-forum-upgrades` (Phase 1 of the
plan `docs/plans/20261108-discord-forum-location-populate-project-notes.md`).
The "before" arm re-implements the shipped logic exactly: `item_host` as
`city, country` falling back to `place_text`, and a continent only from the
structured `country_code` / `country`.

## Data

Every `ContentItem` of type `conference` in the live development database on
2026-11-08 (compose Postgres, read-only). No judgments: the measurement is
whether a field is produced, not whether it is right. Correctness is checked by
reading a random sample of 40 after-arm locations by hand, recorded in RESULTS.

## Metrics

- **continent_rate** (primary): share of conferences with a non-empty continent
  (one of the six, or Online). Primary because it is what the forum filter needs.
- **country_rate**: share whose location names a country (structured or parsed).
- **venue_only_before**: records whose before-arm line is the `city` field alone
  while `place_text` holds more; **venue_only_after** the same for the after arm.
- **sample_wrong**: of 40 random after-arm (location, continent) pairs, how many
  a human reader judges wrong.

## Baselines

The shipped logic (before arm), as above.

## Procedure

```bash
DATABASE_URL=postgres://mycelium:<pw>@localhost:11450/mycelium \
  uv run --no-sync --directory web/backend python \
  ../../docs/research/experiments/EXP-2026-11-005-conference-location-coverage/run.py \
  --out ../../docs/research/experiments/EXP-2026-11-005-conference-location-coverage/data
```

## What would falsify this

An after-arm continent_rate under 60%, or more than 2 of the 40 sampled pairs
wrong (a wrong continent tag misleads a filter, which is worse than none).

# EXP-2026-11-005 — Results

## 1. Headline

`geography.place_for` gives 90.4% of the 912 live conferences a continent, up from
41.8% with the shipped logic, and turns all 107 venue-only location lines into the
full place text. The hypothesis (≥70%, venue-only to zero) survived, and none of
40 randomly sampled (location, continent) pairs was wrong.

## 2. Results table

From `data/metrics.json` (n=1 run, n=912 conferences).

<!-- BEGIN GENERATED TABLE -->
| Metric | Before | After |
|---|---|---|
| continent_rate | 0.4178 | 0.9035 |
| country_rate | 0.4178 | 0.898 |
| venue-only lines | 107 | 0 |
| sample wrong (n=40) | — | 0 |
<!-- END GENERATED TABLE -->

After, by continent: Asia 283, Europe 277, North America 169, Oceania 74,
South America 9, Africa 7, Online 5, none 88.

## 3. Figures

None.

## 4. Interpretation

Continent tags are worth shipping for conferences: nine in ten threads will carry
one, so a forum filtered by continent misses about one conference in ten. Supports
no claim in `../../CLAIMS.md`.

## 5. Threats to validity

- The hand check judges 40 placed records only; it says nothing about the 88 the
  parser left without a continent (by design those show no tag rather than a guess).
- One judge (the agent), reading place names it knows; Barbados is counted as North
  America by convention (Caribbean).
- Live data on one day.

## 6. What surprised us

The 0.5-point gap between country_rate and continent_rate is the five online-only
conferences, which have a continent (*Online*) but no country.

## 7. Follow-ups

- The 88 unplaced are mostly bare cities ("Pittsburgh", "Atlanta, Georgia") and
  placeholder text. A small city table, or fixing it at ingest in the collector,
  would place most of them. Not opened as a question yet; revisit if users ask.

## 8. Reproduction

```bash
DATABASE_URL=postgres://mycelium:<pw>@localhost:11450/mycelium \
  uv run --no-sync --directory web/backend python \
  ../../docs/research/experiments/EXP-2026-11-005-conference-location-coverage/run.py \
  --out ../../docs/research/experiments/EXP-2026-11-005-conference-location-coverage/data
```

## AMENDMENTS

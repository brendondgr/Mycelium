# EXP-2026-11-005 — Protocol

Written 2026-11-08, before the run.

## Question

Once the PubMed-sourced papers carry their own DOI and PMCID instead of a
cited paper's (Q-057), what fraction of `EXP-2026-11-004`'s frozen 200-paper
sample does the full-text tool retrieve, and how many of that run's 28
`identifier_mismatch` stops become fetches?

## Hypothesis

`identifier_mismatch` falls from 28 to at most 3, and `full_text_rate` rises
from 0.54 to at least 0.60. Reasoning: `EXP-2026-11-004` traced every one of
the 28 to a stored DOI/PMCID that was a cited paper's, and 27 of them had a PMC
deposit on paper; PMC served 0.78 of the papers it was asked for there, so
about 20 of the 28 should come back.

## Setup

- System: the full-text engine (`tools/fulltext/engine/`) at the commit in
  `manifest.yaml`, driven by `run.py` in this folder, with this instance's
  configuration (`tools/fulltext/config.py`), a fresh scratch cache, an
  in-process `MemoryState`, `min_chars` 500 and 4 workers — the same settings
  as `EXP-2026-11-004`.
- The identifiers are corrected by the repair's own code, not a copy of it:
  for each sampled paper whose corpus source is PubMed, `run.py` fetches its
  PubMed record and applies `tools/retrieval/pubmed_repair.py`'s decision
  (`parse_own_ids` + `_decide`) — exactly what `repair_pubmed_ids --apply`
  writes to the corpus. Other papers keep their stored ids, as the repair
  leaves them. This makes the run independent of whether, or when, the live
  repair is applied, and writes nothing to any database.
- Two arms, same day, same network, so provider drift since `EXP-2026-11-004`
  does not pass for the repair's effect:
  - **own** — all 200 papers with corrected ids (the primary arm);
  - **stored** — only the papers whose ids the repair changes, with the ids as
    stored (the paired control).

## Data

- `data/sample.json`: `EXP-2026-11-004`'s frozen sample, copied byte for byte
  (sha256 `22b22d46…c86835`, recorded in `manifest.yaml`). 200 `paper` rows of
  the live corpus drawn by `md5(id || 'fulltext-coverage-2026-11')`: 115
  OpenAlex, 74 PubMed, 11 Semantic Scholar.
- No human judgments. "Full text" is the engine's own test: a converted body
  of at least 500 characters (5,000 for an HTML page).

## Metrics

- **Primary: `full_text_rate`** (own arm) — `full_text` / 200.
- `status.<status>` per arm; `ids_changed` — papers whose ids the repair
  changes; `changed.full_text_rate.own` vs `changed.full_text_rate.stored` —
  the paired contrast on those papers; `mismatch_resolved` — of the papers
  that were `identifier_mismatch` under stored ids, how many are not under
  own ids.
- `full_text_by_source.<source>`, `full_text_rate_with_pmcid` /
  `_without_pmcid`, `median_chars`, `wall_clock_seconds` (own arm), as in
  `EXP-2026-11-004`.

## Baselines

`EXP-2026-11-004` (0.54, 28 mismatches) as the historical reference, and the
**stored** arm as the same-day control.

## Procedure

```bash
EXP=docs/research/experiments/EXP-2026-11-005-fulltext-coverage-own-ids
DATABASE_URL=postgres://mycelium:mycelium@localhost:11450/mycelium \
  uv run --no-sync --directory web/backend python ../../$EXP/run.py
```

The database is only read for Django setup and the tool's configuration; the
identifiers come from `data/sample.json` and PubMed.

## What would falsify this

More than 3 `identifier_mismatch` in the own arm, or `full_text_rate` below
0.60. Mismatches that remain under own ids would point at a second source of
bad identifiers (OpenAlex or Semantic Scholar rows), or at the engine.

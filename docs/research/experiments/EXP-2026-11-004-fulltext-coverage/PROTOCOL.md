# EXP-2026-11-004 — Protocol

Written 2026-11-08, before the run.

## Question

What fraction of the papers in Mycelium's live corpus can the full-text tool
(`tools/fulltext`) retrieve as full text on this instance as it is configured
today — no publisher keys, no contact email — and from which sources?

## Hypothesis

Between 25% and 45% of sampled papers come back as full text, with PubMed
Central the largest single source. Reasoning: the PubMedExtraction project this
engine was ported from measured 33.3% on a biomedical corpus from a home
network without Elsevier (36.3% on campus with Wiley); Mycelium's corpus is
broader (OpenAlex, Semantic Scholar, PubMed), 15% of its papers carry a PMCID,
and Unpaywall, which supplied 5.6 points in that run, is off here because the
instance has no contact email.

## Setup

- System: the full-text engine at the commit recorded in `manifest.yaml`
  (`tools/fulltext/engine/`), driven by `run.py` in this folder.
- Configuration: this instance's settings (`tools/fulltext/config.py`
  `credentials()` and `source_order()`) — on the run date, no Elsevier,
  Springer, Wiley or CORE key and no contact email, so Elsevier, Springer,
  Wiley and Unpaywall are off; PMC, Europe PMC, arXiv, OpenAlex, Crossref,
  CORE (anonymous rate) and Semantic Scholar (with the instance's key) are on.
  `run.py` records the source list it actually used.
- Held fixed: a fresh engine cache (scratch directory) and an in-process
  `MemoryState`, so no earlier answer or switch-off leaks in; `min_chars` 500;
  4 workers. The run writes nothing to the app database or to the tool's store.

## Data

- Collection: `ContentItem` rows of type `paper` in the live Mycelium database
  on 2026-11-08 (35,209 papers).
- Sample: 200 papers, the first 200 by `md5(id || 'fulltext-coverage-2026-11')`
  — a deterministic pseudo-random draw. The sampled ids and identifiers are
  frozen in `data/sample.json` before fetching.
- Identifiers given to the engine: DOI, PMID, PMCID and arXiv id from each
  item's metadata, as a dict; the engine resolves and cross-checks them.
- No human judgments are involved. "Full text" means the engine's own test:
  a converted body of at least 500 characters (5,000 for an HTML page).

## Metrics

- **Primary: `full_text_rate`** — papers with status `full_text` / papers
  sampled.
- `full_text_by_source.<source>` — share of the sample served by each source.
- `status.<status>` — count per engine status (`full_text`, `abstract_only`,
  `not_found`, `identifier_mismatch`, `invalid_identifier`, `error`).
- `full_text_rate_with_pmcid` / `_without_pmcid` — the rate split by whether
  the paper has a PMC deposit after resolution.
- `median_chars` — median body length of retrieved papers.
- `wall_clock_seconds`.

## Baselines

No in-repo baseline: this is the first measurement of the tool. The external
reference point is PubMedExtraction's 33.3% (home network) on a different,
biomedical-only corpus; it frames the hypothesis but is not a like-for-like
comparison.

## Procedure

```bash
EXP=docs/research/experiments/EXP-2026-11-004-fulltext-coverage
DATABASE_URL=postgres://mycelium:mycelium@localhost:11450/mycelium \
  uv run --no-sync --directory web/backend python ../../$EXP/run.py \
  --sample 200 --out ../../$EXP/data
```

`run.py` freezes the sample, runs the engine, and writes `data/sample.json`,
`data/results.jsonl` (one line per paper: ids, status, source, chars,
attempts), `data/metrics.json` and `data/metrics.csv`; `tables/summary.md` is
generated from `metrics.json` by the same script.

## What would falsify this

A `full_text_rate` below 0.25 or above 0.45, or a source other than PMC
serving the most papers. Either revises the hypothesis; a rate below 0.15
would also say the engine or its routing is broken for this corpus and needs
investigating before the tool is relied on.

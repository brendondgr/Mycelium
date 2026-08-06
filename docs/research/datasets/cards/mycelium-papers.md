# Dataset card — Mycelium paper corpus

## Identity

| Field | Value |
|---|---|
| Name | Mycelium paper corpus |
| Source | OpenAlex, ingested by `apps.scraper` |
| Licence | CC0 (OpenAlex) |
| Redistributable | Yes |
| Version | Rolling — grows daily; there is no frozen release |

## Composition

Titles, abstracts, authors, venue, and publication date, embedded with
`BAAI/bge-small-en-v1.5` (384 dimensions) into a pgvector column. The corpus has
no ANN index: every similarity query is an exact sequential scan.

## Status: no experiment uses this yet

Every number in the record so far comes from LongEval-Sci. This corpus has no
relevance judgments, so nothing can be measured on it.

Two things must happen before it can carry an experiment:

1. **A frozen snapshot with a hash.** A rolling corpus cannot be an experimental
   dataset — the same command run twice returns different numbers for reasons
   that have nothing to do with the change under test.
2. **Judgments.** Tracked as W3 (instrument the feed to emit `RelevanceEvent`s;
   no personal endpoint currently calls `record_event`) and W5 (hand-label
   250–300 (item, researcher) pairs, graded TREC-CDS style). See
   [`../../OPEN_QUESTIONS.md`](../../OPEN_QUESTIONS.md).

Until both exist, claims C-002 through C-007 cannot move off `unsupported`.

## Known issues

- **No seeds in the matching path.** Nothing in the production matching pipeline
  sets a seed. Retrieval is deterministic, but the LLM scoring layer is not, and
  `LLM_TEMPERATURE` defaults to 0.2.
- **Contamination is unchecked.** Papers postdating a model's training cutoff
  have never been separated from those preceding it, so any LLM-scoring result
  would be unverifiable (W12).

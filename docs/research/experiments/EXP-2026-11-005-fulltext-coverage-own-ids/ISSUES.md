# EXP-2026-11-005 — Issues

- **The repair this run used was improved because of it.** `run.py` corrects
  ids with `tools/retrieval/pubmed_repair.py` at commit 323a054, which clears a
  stored PMCID only when it is one of the article's references. The 4
  remaining `identifier_mismatch` stops were all PMCIDs belonging to another
  PMID that are not in the article's *current* reference list: 2 on PubMed
  rows, 2 on OpenAlex rows that absorbed a bad PubMed record's PMCID at
  ingest. Commit 4d27303 adds a PMC ID-converter check that catches these; a
  check of those 4 rows confirms the improved repair corrects all four (see
  `RESULTS.md` §4). This run's numbers are for the 323a054 repair, unchanged.
- **Generated table shows the wrong `n` for two rows.** `run.py` writes the
  plain counts `changed.stored_status.*` with `n` = 200 in `tables/summary.md`
  and `metrics.csv`; they are counts over the 45 changed papers. The values
  are right; the `n` column is not. Left as generated.
- **Tracebacks in the run log are caught source timeouts** (for example a read
  timeout from www.nature.com), logged by the engine and recorded as a failed
  attempt; no paper ended with status `error`. The log was not kept.
- Unpaywall, Elsevier, Springer and Wiley were off, as in `EXP-2026-11-004`.

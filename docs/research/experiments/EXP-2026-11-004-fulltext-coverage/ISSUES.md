# EXP-2026-11-004 — Issues

- **Dirty tree at scaffold time.** `code.dirty: true` because the Phase 4
  doors of the full-text tool (`tools/fulltext/service.py`, `read.py`, the
  `fulltext_get` command) and another session's unrelated research notes were
  uncommitted. `run.py` uses none of them: it drives the engine
  (`tools/fulltext/engine/`) and `tools/fulltext/config.py`, both unchanged
  since commit 19e5355. The experiment folder is committed with the doors.
- **An engine bug found by this run, fixed after it.** The engine's PubMed
  parser (ported from PubMedExtraction) read `.//ArticleId`, so a paper with no
  DOI of its own would have taken the DOI of the first paper it cites. It now
  reads only `PubmedData/ArticleIdList` (falling back to the article's
  `ELocationID`), with a regression test. `check_ids.py` shows the old parsing
  affected **no** paper in this run (`no_own_doi_but_reference_dois: 0`), so
  the run's numbers stand. The same bug exists in PubMedExtraction itself.
- **The corpus bug behind the 28 mismatches is not fixed here.** It is in the
  retrieval tool's PubMed scraper, outside this experiment and this tool; see
  Q-057.
- Unpaywall was off for the whole run (the instance has no contact email). That
  is the configuration under test, not a fault, but it is the single biggest
  free source left out.

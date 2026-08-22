# EXP-2026-08-014 — Issues

## 1. This experiment reports no result of its own

By design, and it is worth being explicit because a folder in this record that
contains no verdict looks like an unfinished one. `PROTOCOL.md` fixes the
procedure and the presentation and deliberately fixes no hypothesis. The output
is a blinded booklet; the judgment is the user's and arrives afterwards.

**If a preference is recorded, it goes in `RESULTS.md` as a preference from one
person** — evidence about what this user wants from their own feed, which is the
right basis for a product decision and is *not* W5. It must never be cited as a
relevance judgment, aggregated with anything, or reported with an interval.

## 2. The pool builders are imported, not reimplemented

`code/run.py` imports `production_pool.py` from
`EXP-2026-08-013-production-pool-contrast/code/`. That folder is complete and
immutable; this one reads it and does not modify it.

The alternative — copying the union-pool builder into this experiment — is worse
for the reason the record already gives about metrics and bootstraps: two
implementations of one idea is two chances to build subtly different pools and
then present them side by side as if they were the same thing. The import makes
the arms here *the same arms* as `EXP-2026-08-013`'s.

## 3. Blinding, and what it costs

Arms are labelled A–J in a permutation fixed as `BLIND_ORDER` in `code/run.py`,
recorded there and printed on the booklet's last page. It is not alphabetical and
not grouped by base arm.

The cost of blinding is that the tables cannot carry explanatory captions — a
note saying "this arm has no lexical channel" would unblind it instantly. So the
booklet is thinner on interpretation than it could be, on purpose.

## 4. Three gates are switched off, and each one is load-bearing in production

Named on the booklet's cover as well, because a reader could otherwise mistake
these tables for a screenshot of the feed:

- **Match thresholds** (`PAPER_MATCH_THRESHOLD` = 0.5, the opportunity
  thresholds = 0.4). These gate on `best_cosine`, which `_build_pool` populates
  only from the dense channel — so leaving them on would empty `bm25_only` and
  most of the union arms and produce a comparison of nothing against something.
  That is C-019, measured in `EXP-2026-08-013`.
- **Fellowship eligibility.** `fellowships.py` runs a deterministic stage ladder
  and prose-constraint gates *before* relevance. With it on, the fellowship pages
  would compare rule engines rather than retrieval.
- **The paper freshness gate.** The deployed paper feed is scoped to
  `latest_gather_date`; here papers are ranked over the whole 35,205-document
  corpus so the paper tables are comparable to the three opportunity tables.

## 5. SPLADE had to be encoded first, and it is the dominant cost

39,106 documents through `prithivida/Splade_PP_en_v1`, measured at ~17 docs/s on
this host — slower than the 24.3 docs/s `EXP-2026-08-008` measured, because that
figure came from a machine doing nothing else. Roughly 40 minutes, once, cached
content-addressed under `data/eval-cache/embeddings/`.

Run **alone**: `EXP-2026-08-008` ISSUES §5 measured two concurrent ONNX sessions
on this host as catastrophically slower than serial, so the cross-encoder work in
`code/run.py` waits for the encode to finish rather than overlapping with it.

## 6. Timing is honest about what is amortised

Per-query latency and one-time index construction are reported in **separate**
places in the booklet — a chart and a table. Rolling the SPLADE encode into a
per-query number would make the three-channel arm look absurd; hiding it entirely
would make it look free. It is neither: it is forty minutes once, plus a second
index to keep in step with the corpus forever.

The BM25 index build is also one-time *per process*, which flatters it — the
deployed pipeline builds a BM25 index per run, over a much smaller day-scoped
pool, so the number here is not the production cost of that channel either.

## 7. Titles are what gets judged

The booklet shows title, source and a ~190-character snippet. Nobody reads 35,205
abstracts, and neither will the reader of a feed — so this is the right stimulus.
But it means an arm that ranks a genuinely better document with a duller title
will lose, and that bias is shared with the product rather than introduced here.

## 8. Working tree dirty

`code.dirty: true`. Uncommitted while running: this experiment's folder. No file
under `web/backend/apps/` was modified; every arm calls the production functions.

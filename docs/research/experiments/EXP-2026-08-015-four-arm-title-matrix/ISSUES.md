# EXP-2026-08-015 — Issues

## 1. No verdict here either, and the same reason

Same instrument as `EXP-2026-08-014`: the corpus has no relevance judgments, an
LLM judge is the component `EXP-2026-08-008` measured as non-monotonic in
relevance, and my own opinion of a grant listing is not evidence. The judgment is
the reader's. If a preference comes back it is recorded as **one person's
preference over one query** — no interval, no aggregation, never cited as W5.

## 2. The presentation change is the experiment

`EXP-2026-08-014` was rejected as an instrument before it was answered as a
question: 42 pages, and the reader could not tell which arm ranked what. That is
recorded there as an amendment and it is why this exists.

Everything cut here was cut deliberately — snippets, sources, carrier sets, two
of the three queries, six of the ten arms. The cost is that a good document under
a dull title is now easier to miss, since the title carries the whole judgment.
That bias is shared with the real feed, which is also mostly title.

## 3. New letters, on purpose

Arms are **W–Z**, not A–J. Reusing the old letters would carry the previous
verdicts into this read; using A–D would invite the assumption that the mapping
was unchanged. The permutation is `BLIND_ORDER` in `code/run.py`.

## 4. This is a second round on survivors

The four arms were chosen by the reader *because of* their `EXP-2026-08-014`
verdicts — three rated very good, one never rated. So this is not an independent
sample and the population it is drawn from is "arms that already passed one
read". A preference expressed here says which of four acceptable options is
best; it cannot say anything about the six that were dropped.

## 5. A fresh query, not a re-presentation

`Agentic AI in healthcare` was **not** among `EXP-2026-08-014`'s three queries
(that used *AI agents in healthcare*). These are new lists over documents the
reader has not judged, which is the right way round — re-showing already-judged
lists in a nicer format would measure the format, not the arms.

## 6. Arm W's timing is the whole chain, not the rerank alone

`fusion_dense_pool+xenc` is recorded as the base retrieval **plus** the
cross-encoder pass, because that is what answering a query with it actually
costs. The other three are single-stage. The comparison is therefore end-to-end
per query and not "how long does the reranker take".

## 7. Same three gates off

Match thresholds, fellowship eligibility, the paper freshness gate — unchanged
from `EXP-2026-08-014` ISSUES §4 and for the same reasons. Stated on the cover so
the tables are not mistaken for the feed.

## 8. Working tree dirty

`code.dirty: true`. Uncommitted while running: this experiment's folder. Nothing
under `web/backend/apps/` was modified; every arm calls the production functions,
and the union-pool builders are imported from `EXP-2026-08-013`.

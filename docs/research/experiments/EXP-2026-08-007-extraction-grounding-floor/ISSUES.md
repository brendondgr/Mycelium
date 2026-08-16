# ISSUES — EXP-2026-08-007

## 1. `out_of_bounds` is now the dominant failure, and its bounds were never examined

All remaining refusals are conferences hitting the summary-length bound
(40–900 chars) or the topic-count bound (2–6). Those numbers were carried over
from the first draft of the harness without measurement.

A venue described in nine source words may honestly warrant a summary shorter
than 40 characters, in which case the bound is manufacturing a refusal. Before
Phase 8 ships, check the distribution of honest summary lengths per domain and
set the floor from it. **Do not simply lower it to make the number go down** —
the point of the bound is to catch a model that returns `"A conference."`

## 2. The 80-word threshold is untested in the middle of its range

`MIN_SOURCE_WORDS_FOR_OVERLAP = 80` sits far above the conference maximum (14)
and far below the grant median (484), so **no record in this corpus is near the
boundary**. That makes the split clean here and completely unvalidated for any
future source landing in the 15–80 band — for example, a conference once its
website has been fetched and reduced, which is exactly what Phase 8 §8.3 does
for the enrichment path.

When that path lands, re-measure. A fetched page will often fall in the gap.

## 3. Zero `unsupported_claim` in the live run

The protocol named this as a suspicious outcome, so the validator was exercised
directly with hand-built cases (RESULTS.md table). Both regimes fire correctly.
Recorded here because "the check never fired" is a fact a future reader should
see reconciled rather than have to rediscover.

## 4. A wrong fixture during that verification

The first verification pass reported `RICH + ungrounded prose -> PASS`, which
would have meant the strict floor was broken. The fixture had 46 content words —
below the 80 threshold — so it took the stub branch correctly. Rebuilt at 107
words, the strict floor fires as designed. **The code was right and the test was
wrong**; noted because the intermediate result was alarming and someone reading
only the transcript would see it.

## 5. `code.dirty: true` — what was uncommitted

The vendored collector (`web/backend/apps/scraper/collect/`) and the lifted
eligibility/fellowship packages were committed at `e06926b` before this run, but
the EXP-2026-08-007 folder itself was untracked while running. The harness
imports only `apps.core.llm` and reads the two upstream SQLite stores directly;
it does not import `apps.scraper.collect`. Not a confound.

## 6. `LLM_BASE_URL` overridden, as in EXP-2026-08-006

`.env` sets `http://host.docker.internal:4000/v1`, which resolves only inside a
container. The run used `http://localhost:4000/v1` — the same proxy by its
host-side name. No other setting changed.

## 7. Throughput is not comparable cell-for-cell with EXP-2026-08-006

That run measured `thinking-medium` at 12 workers (0.099 rec/s); this one at 16
(0.359 rec/s). Part of the 3.6× gain is the extra workers and part is fewer
repair attempts now that the floor is satisfiable (mean attempts fell to 1.03).
**The two effects are not separated here** and no claim is made about their
split.

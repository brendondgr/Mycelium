# EXP-2026-08-013 — Protocol

**Pre-registered.** Written before either arm was scored. What existed first was
setup knowledge only: the store's row counts, the code path
(`apps.content.pipeline._build_pool`), and a query-side/corpus-side embedder
alignment check (§6). No contrast had been computed.

## Question

`Q-001`, open since `EXP-2026-08-002` and the last gate between this programme
and a production change:

> Does the union pool's recall advantage survive on the **production corpus**,
> where documents are longer and queries are declared interests rather than
> keywords?

Twelve experiments have measured the pool contrast on LongEval-Sci. C-008 (the
union pool beats the dense-restricted pool on recall) is supported on **two**
snapshots under **two** judgment regimes (`EXP-2026-08-012`). Every one of those
numbers comes from `query → documents`. Mycelium does
`declared-interest profile → feed`. This experiment moves the contrast onto the
real store, the real targets, and the real declared interests.

## The asymmetry this experiment is built around — state it first

**There are no relevance judgments for the production corpus.** W5 (250–300
hand-graded `(item, researcher)` pairs) is not started, and the store carries
almost no behavioural substitute: 9 saved opportunities, 0 collection items, 0
ignores, 2 relevance events. The 4,588 `RelevanceScore` rows are the deployed
LLM's own opinion — the component C-004 is about, and `EXP-2026-08-008` showed a
rubric scorer of that shape is non-monotonic in relevance. Using it as ground
truth would be circular. It is not used.

So this experiment is **decisive in one direction only**, and that is
deliberate:

- It **can** establish that the C-008 fix is **inert on production** — that
  corpus-wide BM25 reaches nothing the dense pool has not already got, or that
  it changes nothing a reader sees. That closes `Q-001` negatively and needs no
  labels at all.
- It **cannot** establish that the fix **helps**. That is a relevance question
  and stays blocked on W5.

Any result in the second branch must be reported as "the mechanism is live and
this large", never as "ship it".

## What production actually does

`_build_pool` (`web/backend/apps/content/pipeline.py`) retrieves
`pool_per_interest = 100` nearest neighbours **per interest**, unions them into
one pool, and then builds the BM25 index over `pool.values()`. The lexical
channel can therefore only reorder what the dense channel already chose. That is
the exact configuration C-008 says is wrong, running in production today.

Two further facts shape the design and were established before any scoring:

1. **The paper feed is day-scoped.** `recommend_for_user` and
   `recommend_for_target` both set
   `created_on = latest_gather_date(ContentItem.Type.PAPER)`, so a run's corpus
   is a single gather batch, not the 35,205-paper store. Batches in this store
   run 303–4,475 papers. When a batch is small relative to
   `pool_per_interest × n_interests`, the dense pool can cover most or all of it
   and the fix is inert **by arithmetic**. This is measured per day, not
   assumed.
2. **Opportunity matching is not day-scoped.** `opportunities.py` leaves
   `created_on = None`, so grants (2,171), conferences (912) and fellowships
   (818) are matched over their whole corpora through the *same*
   `fuse_interests_pool`. That is a second deployed regime with a very different
   corpus-to-pool ratio.

## Arms

Both arms call the **same production functions** — `embeddings.embed_text`,
`build_bm25_index`, `rank_bm25_over`, `fuse_interest`, `combine_interests`. Only
pool membership differs, mirroring `eval/harness/arms.py` exactly.

| Arm | Pool |
|---|---|
| **A1 `dense_pool`** | `_build_pool` verbatim — production as deployed |
| **A2 `union_pool`** | union of each interest's dense top-100 **∪** union of each interest's corpus-wide BM25 top-100, both channels then restricted to the union and handed to the same `fuse_interest` |

**A3 `union_pool_fts` (exploratory).** Same as A2 but the corpus-wide lexical
channel is Postgres FTS over `ContentItem.search_vector` — the channel
`apps/content/search.py` already runs in production for `/api/search/`. Included
because it is the implementation Mycelium would actually ship (the index exists;
`rank_bm25` over 35k documents in-process does not scale), so the decision needs
to know whether the mechanism holds under it and not only under BM25Okapi.

No new ranking logic reaches `apps.content`. The A2/A3 pool builders live in
this experiment's `code/`.

## Regimes

| ID | Scope | Corpus per query | Deployed? |
|---|---|---|---|
| **R1** | papers, `created_on = <each gather day>` | 303–4,475 | **yes** — the paper feed |
| **R2** | papers, `created_on = None` | 35,205 | not for the feed; the scope `/api/search/` and a lifted freshness gate would use |
| **R3** | grants / conferences / fellowships, `created_on = None` | 2,171 / 912 / 818 | **yes** — the opportunity matchers |

R1 is run over **all 17 gather days**, not just the latest, so the answer is a
curve against batch size rather than one point that happens to fall on a quiet
day.

## Targets and queries

**Inclusion, fixed now:** every user / lab / project profile in the store with
at least one non-empty `interests.areas` entry. That is **6 targets and 38
declared interests** — `brendondgr` (22 areas, 5 clusters), `bdgr` (5), `bdgr2`
(5), `PULSE Lab` (3), `uitest` (2), `Test Lab` (1). The project profile has zero
areas and is excluded.

**Pre-registered sensitivity split.** Some of these are development fixtures.
Every headline number is reported twice: all 6 targets, and the 4
plausibly-real ones (`brendondgr`, `bdgr`, `bdgr2`, `PULSE Lab`). Declared now so
the split cannot be chosen after seeing which one is friendlier.

## Metrics

**Primary — `bm25_reachability@100`**, per (target, interest, regime):

> of the corpus-wide BM25 top-100 for this interest, what fraction is already in
> the target's dense pool?

This is the mechanism C-008 names, measured directly rather than through a proxy.
`1.0` means the lexical channel could never add a document because there is
nothing left to add, and the fix is inert. `0.0` means every lexically-strong
document is unreachable today.

**Secondary, per target × regime:**

- `pool_growth` = `|union pool| / |dense pool|`
- `novel_share` = `|union \ dense| / |union|`
- `surfaced_entrants` — how many union-only documents survive the **whole**
  deployed path (`fuse_interest`'s `DEFAULT_INTEREST_FLOOR = 0.15`,
  `combine_interests(beta)`, `PAPER_MATCH_THRESHOLD`, `PAPER_MATCH_MAX_SURFACE`)
  into the final surfaced list — and at what ranks
- `surfaced_jaccard` — A1 vs A2 surfaced-set overlap

**`Q-018` companion, free with this run:** candidates emitted per interest after
the 0.15 floor, against pool size, on real declared interests.
`EXP-2026-08-008` measured 59–97 per query (median 74) from a 200-document pool
on LongEval; this says whether the floor is the binding cut in production.

**Premise checks.** `Q-001` asserts production differs from LongEval in two named
ways. Both are cheap to measure and either one could undercut the question:

- **document length** — production paper token counts vs the frozen LongEval-Sci
  subset
- **query length** — declared-interest word counts vs LongEval query word counts.
  This bears directly on the cross-encoder refutation, which was significantly
  harmful at 1–4 words (`EXP-2026-08-009`, `EXP-2026-08-010`).

**Intervals.** `harness.stats.paired_bootstrap` — the same bootstrap, seed and
decision rule as every interval since `EXP-2026-08-009` — over interests for the
primary metric. **n = 38 is small and n = 6 targets is very small**; target-level
contrasts are reported as counts and per-target tables, not as intervals that n
cannot support.

## Decision rule — fixed now

- **Inert ⇒ do not ship, `Q-001` closes negative.** Median
  `bm25_reachability@100` ≥ 0.90 in the deployed regimes (R1, R3) **and**
  `surfaced_entrants = 0` for ≥ 90% of (target, regime) pairs.
- **Live ⇒ mechanism confirmed on production, value still blocked on W5.**
  Median reachability ≤ 0.50 **and** `surfaced_entrants > 0` for a majority of
  (target, regime) pairs. This does **not** authorise a production change.
- **Anything between** — report the curve and change no recommendation.

The two branches are stated with a deliberate gap between them so a marginal
result is reported as marginal rather than rounded to whichever side is more
convenient.

## What would falsify what

- **C-008's production relevance** falls if the inert branch fires. The LongEval
  claim survives untouched — it is about LongEval — but the production change it
  implies would be withdrawn.
- **The experiment itself is invalid**, not any claim, if the embedder alignment
  gate (§6) fails.

## 6. Gates run before any contrast

1. **Embedder alignment.** `embeddings.embed_text` over a stored item's own
   `search_text` must reproduce that item's stored `ContentItem.embedding` to
   cosine ≈ 1.0 — otherwise the query side and the corpus side are different
   models and every dense pool is wrong. **Run before this protocol was written:
   0.9999999999999998.**
2. **A1 must equal `_build_pool`.** A1 calls `_build_pool` directly rather than
   reimplementing it, so this holds by construction.

## Threats to validity, declared in advance

1. **n = 6 targets, 38 interests.** Small, and no amount of care fixes it. The
   store has 6 users.
2. **This is a development store**, not a production deployment: it contains test
   fixtures, and its freshest gather day is 2026-07-20.
3. **No relevance labels** — §2. The value half of `Q-001` stays open regardless
   of what this returns.
4. **Day-scoping makes R1 partly arithmetic.** If the fix is inert on R1 it may
   be inert *because the batch is small*, which is a fact about the freshness
   gate rather than about pooling. The per-day curve is what separates those.

## Procedure

```bash
docker compose up -d postgres
uv run --project eval python \
  docs/research/experiments/EXP-2026-08-013-production-pool-contrast/code/run.py
```

No LLM is called anywhere in this experiment.

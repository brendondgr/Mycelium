# EXP-2026-08-010 — Issues

## 1. Pre-registration status

`PROTOCOL.md` was written after the query expansions were generated and inspected,
and **before any rerank arm ran**. The hypothesis, the falsifier, the decision
rule, and the specific worry about ambiguous one-word queries were all recorded
before a single score existed.

Generating the expansions first is deliberate and is not a leak: the expansion
prompt sees the query string alone — no documents, no candidates, no judgments —
so nothing about relevance could enter the arm. Inspecting them first was
necessary to confirm the intervention was the one intended (prose describing the
topic) rather than something degenerate.

## 2. The intervention is confined to one stage, by construction

Every arm retrieves with `bm25_only` over the **original** query and reranks the
same top 50 with the same cross-encoder. The only thing that varies is the string
handed to `encoder.rerank(...)`. This is enforced in `ladder.xenc_rerank`: the
base ranking is computed before any expansion is loaded, and the expansion is
never passed to the retriever.

The check that this held: `R@100` must be identical across every arm and equal to
`bm25_only`'s, since reranking a fixed top-50 cannot change what was retrieved. A
difference there would be a bug, and is called out in `PROTOCOL.md` as a
falsifier rather than something to explain away.

## 3. Expansion quality, and where it is likely to fail

All 492 queries expanded cleanly at all four lengths — 0 failures, medians of 8,
15, 19 and 38 words against targets of 8, 16, 20 and 40. Spot-checked examples are
on-topic and preserve the rare terms that BM25 depends on (`Merleau-Ponty`,
`crania` → "skulls", "European").

The known weak case is **ambiguity**, and it was recorded before the run. The
expansion for `operation` hedges across "mathematical function, surgical
procedure, functional process" — three unrelated fields. No amount of extra length
fixes that; it makes it worse, because a longer hedge drifts further from whatever
the query actually meant. If the 1-word bucket fails to recover while longer
buckets do, this is the first explanation to test.

## 4. Confounded with length: prose *style*

An expansion is not just "the same query, longer". It is a different register —
full sentences, framing phrases like "This search targets…", explicit statements
of what kind of paper would satisfy it. So an effect attributed here to *length*
is really an effect of *length and register together*, and this design cannot
separate them.

The clean control would be a length-matched arm whose extra words carry no
information — padding, or a generic scientific preamble. It was not run. Any
positive result should be read as "prose of about this length helps", not
"more words help".

## 5. One model, one prompt, one reranker, one snapshot

The expansion comes from `skynet`, a relay alias whose upstream is not pinned
(the same gap audit item W1 names). The reranker is
`Xenova/ms-marco-MiniLM-L-6-v2`, 22M parameters, chosen because this host has no
GPU — and `Q-021` already asks whether `EXP-2026-08-009`'s refutation is a
property of that specific model. If it is, this experiment inherits the same
scope limit: a bigger reranker might not need the prose at all.

Only `sci-2025-01` was run. The 2026 snapshot has longer queries and showed no
harm to recover, so it is a poor test bed for this — but that also means the
result here is single-snapshot.

## 6. Working tree dirty

`code.dirty: true`. Uncommitted while running: `eval/expand_queries.py`, the
`expand_words` path in `eval/harness/ladder.py`, `eval/harness/stats.py`, the four
`xenc_bm25base_expand*` configs, and this experiment's folder. `apps.content` is
unchanged — nothing here touches production.

`harness/stats.py` was extracted mid-experiment so `EXP-2026-08-009` and this one
share one bootstrap implementation rather than keeping two copies that could
drift. The refactor was verified behaviour-neutral: `EXP-2026-08-009`'s paired
table reproduces byte-identically afterwards (+0.0001 / +0.0088 / −0.0439 with the
same intervals, win/loss counts and p-values).

## 7. What the intervals can and cannot say

The bootstrap resamples **queries**, so an interval answers "would this survive a
different sample of topics from this collection". It says nothing about a
different corpus, a different judgment set, or Mycelium's task. LongEval is
`query → documents`; the product is `declared-interest profile → feed`, and
`Q-001` is untouched.

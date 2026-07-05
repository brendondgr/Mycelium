# Multi-Interest BM25 + RRF Fusion — Implementation Plan

## Objective

Replace the daily research pipeline's single-vector retrieval + lexical-overlap
re-rank with a **per-interest** retrieval + fusion pipeline: score each candidate
paper *per declared research area*, fuse a BM25 lexical channel with the pgvector
semantic channel per interest (RRF), normalize per interest, then combine across
interests so papers matching **several** of a researcher's interests are preferred
over papers matching only one — before the LLM validation step.

Also (product requirement from this session): the daily research report **surfaces
the top 25 papers**, but **only the top 10 receive LLM headlines/reasons/match
scores**; papers ranked 11–25 carry deterministic (fallback) rankings.

Grounded in `docs/plans/daily-research-suggestions.md` and the current code in
`web/backend/apps/content/` (`pipeline.py`, `retrieval.py`, `ranking.py`,
`suggest.py`).

## Locked decisions (from the source plan's open questions)

All six open decisions are resolved to the source plan's recommended defaults;
they are placeholders subject to later empirical tuning, not final constants.

1. **Search interest = one entry in `interests.areas`.** `interests.keywords` are
   attached to *every* interest's BM25 `query_text` as auxiliary terms (not their
   own interests). `embed_text = area + keywords`. Zero areas ⇒ `search_interests`
   returns `[]` and the pipeline **falls back to the current single-vector path**
   unchanged (no-op safety, mirrors `rerank_by_focus`).
2. **BM25 runs in-process** (`rank_bm25.BM25Okapi`) over the day's candidate
   `ContentItem` pool — the same bounded pool the vector ANN draws from. No search
   engine, no full-corpus index. Index built **once per run**, scored per interest.
3. **Combination = softened CombMNZ:**
   `combined = mean(normalized_scores) * (1 + β·(n_matched − 1))`, `β = 0.15`.
4. **Floor guarantee: yes for v1.** The single best paper per interest (by that
   interest's own normalized score) is guaranteed into the surfaced set even if its
   combined score missed the natural cutoff.
5. **Per-interest floor = 0.15**, applied *after* per-interest min-max
   normalization; sub-threshold contributions are dropped ("didn't match this
   interest").
6. **Correlated-interest damping: deferred.** Flagged, not built.

**Surfacing knobs:** `SURFACED_LIMIT = 25` (rows flagged `suggested`), `LLM_RANK_LIMIT = 10`
(rows given LLM headline/reason/match). Both overridable per run.

## Dependencies changing

- Add `rank_bm25` (pure-Python, needs `numpy`) + `numpy` to `web/backend`
  **core** dependencies in `web/backend/pyproject.toml`. BM25 is now central to the
  pipeline, so it is not optional — but it is **lazily imported** and the pipeline
  degrades to vector-only fusion if the import fails, per the "every missing
  capability degrades to a status, not a crash" convention.

## Public interfaces / files changing

New modules under `web/backend/apps/content/`:
- `interests_query.py` — `SearchInterest` dataclass + `search_interests(interests) -> list[SearchInterest]`.
- `lexical.py` — `rank_bm25_over(query_text, candidates) -> list[Hit]` (+ index builder).
- `fusion.py` — `fuse_interest(...)`, `combine_interests(...)`, `CombinedHit`.

Modified:
- `pipeline.py` — rewire `run_for_user`; keep single-vector fallback for no-areas.
- `suggest.py` — LLM-rank top 10, deterministic fallback for 11–25 in one call.
- `views.py` / `serializers.py` — surface 25; summary rolls up the surfaced set.
- `research-papers-section.tsx` — render 25 with a divider after rank 10;
  the existing `origin` badge already distinguishes LLM picks from topical matches.
- `pyproject.toml`, `docs/repo-map.md`, `docs/changelog.md`.

No API contract shape change (same `/api/daily-report/` fields; `signals` gains
`per_interest` + `n_matched` keys alongside the existing ones).

## Implementation phases (each validated before the next)

### Phase 0 — Scaffolding
- Fresh git worktree off `main`; add `rank_bm25` + `numpy` deps; `uv sync`.
- **Validate:** `import rank_bm25, numpy` succeeds; baseline `apps/content` suite green.

### Phase 1 — `interests_query.py` (pure)
- `SearchInterest(label, query_text, embed_text)` frozen dataclass; `search_interests`
  dedupes areas order-preservingly, attaches keywords, `[]` on empty areas.
- **Validate:** unit tests — dedupe/order (mirrors `test_build_queries_...`),
  empty-areas ⇒ `[]`, keywords attached to `query_text`.

### Phase 2 — `lexical.py` (BM25 channel)
- `build_bm25_index(candidates)` once; `rank_bm25_over(query_text, index) -> [(item, score)]`
  descending; empty pool / empty query ⇒ `[]` (no crash). Simple shared tokenizer.
- **Validate:** unit tests — term unique to one title ranks it first; empty-pool guard;
  missing `rank_bm25` import degrades cleanly.

### Phase 3 — `fusion.py` per-interest RRF + normalization
- `fuse_interest(bm25_hits, vector_hits, *, k=60)` → RRF dict → min-max to [0,1]
  → drop < 0.15.
- **Validate:** unit tests — RRF math vs hand-computed fixture; doc in both top-3
  lists normalizes ≈1.0; sub-floor dropped; absent doc simply not in dict.

### Phase 4 — `fusion.py` cross-interest combination
- `combine_interests(per_interest_scores, *, beta) -> [CombinedHit]` with
  `mean·(1+β(n−1))`, sorted desc, plus the best-per-interest floor guarantee.
- **Validate:** **primary regression test** — paper matching 3 interests @0.8 each
  outranks paper matching 1 interest @0.8; floor guarantee keeps a niche strong
  match; empty input ⇒ `[]`.

### Phase 5 — Wire into `pipeline.py`
- `search_interests(interests)`; empty ⇒ existing single-vector path unchanged.
- Else: build candidate pool (union of per-interest vector ANN pulls, widened to
  ~100), build BM25 index once, per interest fuse+normalize, `combine_interests`,
  feed `(item, combined_score)` pairs to `generate_suggestions`.
- Persist `per_interest` + `n_matched` into `RelevanceScore.signals`; flag top 25
  `suggested`, rank 1–25.
- **Validate:** new pgvector-gated integration test (2+ areas; synthetic papers
  hitting 1 vs 2 areas) — 2-interest paper higher-scored and present in
  `signals["per_interest"]`; update the existing with-areas pipeline tests to the
  new signals; **no-areas profiles unchanged** (existing suite stays green).

### Phase 6 — Top-25 surface / top-10 LLM split
- `generate_suggestions(..., llm_limit=10, surface_limit=25)`: LLM ranks top 10;
  ranks 11–25 get deterministic fallback entries (`source="fallback"`). One list of
  25 returned, ranks 1–25.
- `views.py`/`serializers.py`: return all 25; summary counts the surfaced set.
- `research-papers-section.tsx`: render 25; subtle "Also surfaced" divider after 10.
- **Validate:** unit test — 12 candidates, `llm_limit=3` ⇒ ranks 1–3 `source="llm"`,
  4+ `source="fallback"`, total ≤ `surface_limit`; daily-report API test asserts 25
  returned with correct origins; frontend renders (preview DOM read).

### Phase 7 — LLM prompt polish (optional)
- Pass matched interest labels / `n_matched` per candidate into the prompt so the
  reason can name *which* interests a paper bridges. Skip if time-boxed.

## Validation & acceptance criteria

- Root-level backend validation via host venv (root-owned `.venv` workaround):
  `export UV_PROJECT_ENVIRONMENT=/home/bdgr/.cache/mycelium-backend-venv`.
- Offline unit suite: `DATABASE_URL="sqlite:///…" uv run --directory web/backend python -m pytest apps/content -q`.
- pgvector integration: throwaway `pgvector/pgvector:pg17` on `:5433`, run the full
  suite so the fusion pipeline test and migration chain execute.
- `uv run --project web/backend ruff check web/backend`.
- Frontend: `next` dev/preview DOM read of the Research Papers page showing 25 items.
- Acceptance: 3-interest-beats-1-interest regression passes; no-areas users keep
  current behavior; report shows 25 papers, 10 LLM-ranked; suite + lint green;
  changelog + repo-map updated; committed (not pushed); worktree merged to main.

## Security / data ownership

- No auth-surface change. `/api/daily-report/` stays `IsAuthenticated` and returns
  only `target_user == request.user` rows. No new cross-lab exposure; scoring stays
  per-user. `signals` remains an auditable per-signal breakdown.

## Explicit exclusions

- Correlated-interest damping (decision 6).
- Empirical tuning of `β` / floors (needs engagement or labeled data).
- Promoting `keywords` to standalone interests.
- BM25 over the full corpus / any external search engine.

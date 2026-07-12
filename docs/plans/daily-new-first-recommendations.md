# New-First Daily Recommendations, Match Floors, and Interest-Based Fellowships

**Status:** implemented (2026-07-12)
**Areas:** `web/backend/apps/content/`, `web/app/src/components/portal/sections/`, settings/env, docs.

## Objective

Three linked fixes to the daily recommendation runs (papers, grants, conferences, fellowships):

1. **Only new items go through the LLM.** Nightly runs currently re-send the same
   top-10 fused items to the model every day, so previously-scored items burn the
   whole LLM budget and freshly-ingested items never get a Mylo report. Carry
   forward prior LLM verdicts and spend the per-run LLM slots on items that have
   never been scored (newest first).
2. **Hide weak matches everywhere.** An item whose LLM percent-match falls below a
   floor (e.g. the 10% Cattlemen's scholarship, the 40% Luce Asia program) must not
   surface at all — not in the feeds, not in the briefing. Non-LLM items stay gated
   by the existing embedding thresholds.
3. **Fellowships must be graded on research fit, not just eligibility.** The rule
   engine's `fit` has zero topical signal (tier/stage/field/recency/stipend only),
   which is why irrelevant-but-eligible fellowships outrank everything. Blend in
   the pgvector embedding match (fellowship `search_text` already embeds title +
   blurb + **description** + facets), gate on it, and surface the description on
   the fellowship cards (backend already stores it; serializer/UI drop it today).

Additionally the **daily briefing** should lead with what is *new* ("6 new
conferences") instead of the total corpus matched ("140 conferences").

## Assumptions / decided defaults

- Prior-run memory lives in the existing `RelevanceScore` rows (they persist across
  runs; only the read layer filters to the latest `run_at`). No new model/migration.
- A carried-forward verdict keeps `source="llm"` (UI keys off it) plus a
  `llm_scored_at` signal stamped when the model actually ran.
- New settings (env-tunable, documented in `.env.example`):
  - `OPPORTUNITY_MIN_MATCH_PERCENT` (default **60**) — floor for LLM-scored
    grants/conferences/fellowships.
  - `PAPER_MIN_MATCH_PERCENT` (default **60**) — same floor for papers.
  - `FELLOWSHIP_MATCH_THRESHOLD` (default **0.4**) — embedding-cosine floor for
    fellowships (mirrors `GRANT_MATCH_THRESHOLD` / `CONFERENCE_MATCH_THRESHOLD`).
- Below-floor items are persisted with `signals.suggested=False` (keeping their LLM
  verdict) so carry-forward remembers them and never re-sends them to the model;
  the opportunity read views gain the `suggested=True` filter papers already have.
- Fellowship blended fit: `0.65 * embedding_match + 0.35 * rule_fit`, hard
  eligibility gates unchanged and still first. Ranked by blended fit (tier stops
  being the primary sort key). `match_percent` for rules-sourced rows becomes the
  embedding percent instead of `rule_fit*100` (the old value masqueraded as topical
  relevance). Users with no interests/embeddings fall back to today's rule-only
  ordering (no gate — cannot compute one).
- Briefing: keep `counts` (totals) for back-compat, add `new_counts`; showcase and
  LLM prompt prefer new items; UI leads with new.

## Phases

### Phase 0 — Isolation + baseline
- `git worktree add` a feature branch off **local** `main` (origin lags).
- Baseline: `uv run --project web/backend pytest apps/content` must pass (or note
  pre-existing failures) before any edit.

### Phase A — Carry-forward LLM scoring + match floors (backend core)
Files: `opportunities.py`, `opportunity_llm.py`, `pipeline.py`, `suggest.py`,
`views.py`, `config/settings.py`, `.env.example`, tests.
- New helper (in `opportunity_llm.py` or a small `prior.py`): load prior LLM
  verdicts `{content_id: {match_percent, headline, reason, llm_scored_at}}` for a
  `(target, content_type)` from existing `RelevanceScore.signals`
  (`source=="llm"`, `match_percent is not None`). Called in the *prepare* (DB)
  phase; scoring stays ORM-free.
- LLM subset selection: surfaced candidates **without** a prior verdict, ordered
  new-first (`metadata.first_seen`/`created_at` within the New window first, then
  fused rank), capped at `llm_limit`. Prior-scored items merge their carried
  verdict instead of a fallback row.
- Floor applied after merge: `match_percent is not None and < floor` → not
  suggested (persisted with full signals, `suggested=False`).
- `_OpportunityFeedView._latest_scores` filters `signals.suggested` (papers parity).
- Same mechanism for papers (`pipeline.py` + `suggest.py`).
- **Validate:** new unit tests (carry-forward selection, floor gating, read filter)
  + `pytest apps/content` green.

### Phase B — Fellowship research-fit overhaul (backend)
Files: `fellowships.py`, `opportunities.py` (fellowship path), `serializers.py`, tests.
- `_prepare_fellowship_match` also runs `fuse_interests_pool(content_type=FELLOWSHIP)`
  over the user's opportunity search interests → `embed_by_id` map.
- `match_fellowships(..., embed_by_id, match_threshold)` — after the hard gates:
  drop items whose embedding match < `FELLOWSHIP_MATCH_THRESHOLD`; blended fit
  ranks; `match_percent` (rules rows) = embedding percent; persist
  `embedding_match` in signals.
- `FellowshipSerializer` exposes `description` (from `metadata.description`,
  falling back to `blurb`) like `GrantSerializer` does.
- **Validate:** updated `test_fellowships*.py` (fake embedder) + suite green.

### Phase C — New-first briefing + frontend
Files: `briefing.py`, `test_daily_briefing.py`, `daily-reports-section.tsx`,
`fellowships-section.tsx`, `lib/portal/types.ts`.
- Briefing gathers `new_counts` alongside `counts`; showcase sorts new-first; LLM
  prompt + deterministic fallback lead with "N new" per category.
- Daily UI: stat tiles lead with the new count ("6 new · 140 matched").
- Fellowship card renders the description (clamped) under the title; TS type gains
  `description`.
- **Validate:** briefing tests; `npm run lint` / `tsc --noEmit` / `next build` for
  the web app.

### Phase D — Docs, merge, commit
- Update `.env.example`, `docs/changelog.md`, memory notes; `docs/repo-map.md` only
  if paths change (none expected).
- Full backend suite + frontend build in the worktree, merge local `main` in, then
  merge the branch to `main` and commit (no push).

## Interfaces that change

- `GET /api/opportunities/{grants,conferences,fellowships}/` — now returns only
  `suggested` rows (weak matches disappear); fellowships gain `description`.
- `GET /api/daily-briefing/` — payload gains `new_counts` (additive).
- Settings/env: `OPPORTUNITY_MIN_MATCH_PERCENT`, `PAPER_MIN_MATCH_PERCENT`,
  `FELLOWSHIP_MATCH_THRESHOLD`.
- `RelevanceScore.signals` gains `llm_scored_at` (and `embedding_match` for
  fellowships). No schema migration.

## Acceptance criteria

- A nightly re-run sends **zero** previously-scored items to the model; only
  unscored (preferring new) items consume the `llm_limit` slots; prior verdicts
  still render in the feeds.
- An LLM verdict below the floor never appears in any feed or briefing.
- An eligible-but-topically-irrelevant fellowship (embedding match below the
  threshold) is not surfaced; fellowship cards show the description.
- The briefing/daily page leads with new-item counts.
- Backend suite green; web app typechecks, lints, builds.

## Exclusions

- No re-scoring cron for stale LLM verdicts (a profile change already triggers
  `refitting.py`, which stays a full re-score by design).
- No lab/project fellowship matching (still user-only).
- No changes to ingest/prune or the Pivot scrapers.

# Lab Projects — implementation plan

## Objective

Make the lab overview and project pages show **real** daily recommendations
(research papers, grants, conferences) driven by the lab's aggregate interests and
by each project's own focus, and surface **which lab members** are likely
interested in a given item. Today those surfaces are honest "coming soon" stubs;
the goal is to turn the lab into a first-class scoring target alongside the user.

## Key finding — the data model already supports this

The schema was built for this and is currently unused at the pipeline layer:

- `content.RelevanceScore` is already polymorphic: `target_user`, `target_project`,
  `target_lab`, `target_department`, guarded so exactly one is set. The pipelines
  only ever write `target_user`.
- `research.Project` already has an `embedding` ("derived from goals; the project
  relevance target") and a free-form `goals` JSON; `accounts.LabProfile` has curated
  `interests`/`embedding` + a `derived_embedding` blended from members and projects
  (`accounts.aggregates.derive_lab_vector`); `accounts.LabWatchPreference` carries
  `topics`/`categories`/`cadence`. None of these feed matching yet.
- The matching core is already target-agnostic where it counts:
  `content.pipeline.fuse_interests_pool(content_type=…)` is parameterized by content
  type, and `content.interests_query.search_interests(interests_dict)` is a pure
  function over *any* interests dict. Only the outer entry points and the persist
  step are hard-wired to `user`.

So the work is **"generalize the matcher's target from `user` to `{user, lab,
project}`, then wire surfaces to read the new scores"** — not "build a recommender."

## Assumptions & decisions

1. **Project focus is explicit.** A project stores its focus in `goals`:
   `goals.interests = {areas, keywords, statement}` and `goals.watch_topics = [...]`.
   Kept in the free-form `goals` JSON so **no migration** is needed; a builder reads
   it with fallbacks to legacy `goals` fields (`description`/`goal`/`topics`).
2. **Fellowships stay individual-only.** They gate on a person's
   citizenship/stage/eligibility rule engine and are meaningless at lab/project
   scope. Labs and projects match papers + grants + conferences only.
3. **Lab feeds reuse existing pages** via a scope filter rather than a new nav area.
4. **Object-level authorization is preserved.** Lab feeds require lab access
   (`user_has_lab_access`); project feeds require `Project.objects.visible_to`.

## Ordered implementation phases

Each phase is a self-contained commit that is validated before the next begins.

### Phase 1 — Generalize the matcher (backend, no UI)
- New `apps/content/targets.py`: a `MatchTarget` descriptor (kind, key, interests,
  watch_topics, profile_meta, persist_kwargs, embedding_text) + builders
  `target_for_user` / `target_for_lab` / `target_for_project`, plus
  `project_interests(project)` / `project_watch_topics(project)` derived from `goals`.
- Generalize the persist step (`pipeline._persist`, `opportunities._persist`) to take
  the target's `persist_kwargs` instead of a hard-coded `user`.
- Add `recommend_for_target` (+ `recommend_for_lab`/`recommend_for_project`) and
  `match_opportunities_for_target` (+ `run_opportunities_for_lab`/`_project`).
- `*_for_user` entry points become thin wrappers over the target path and keep
  identical behavior (watch-topic opt-in gate, profile-vector persistence).

### Phase 2 — Project focus + create/edit API
- Surface `goals.interests`/`goals.watch_topics` through the project serializers.
- Add a project update endpoint (edit name + goals/focus) with manage/member auth.

### Phase 3 — Lab + project recommendation read API
- `GET /api/projects/<id>/recommendations/` — the project's matched papers/grants/
  conferences, `visible_to`-gated.
- Lab-scoped feeds: `?scope=lab&lab=<slug>` on the grants/conferences/papers feeds
  (or dedicated lab endpoints), lab-access-gated, reading `target_lab` scores.

### Phase 4 — Scheduling & on-demand refit
- Extend `run_daily_batch` and `run_daily_opportunities_batch` to also match labs and
  their lab-scoped projects over the **shared** corpus (one scan, many targets), with
  the existing per-target LLM cap and logging. Fellowships remain user-only.
- On-demand refit entry points for a lab/project (post-edit, first-run).

### Phase 5 — Surfaces (UI)
- Lab overview: replace the three "coming soon" stat cards with real lab counts.
- Project detail: fill the "Recommended by Mylo" card + project feed from the new
  endpoint, reusing `MatchBadge`/`MyloReason`/`NewTag`/`OpportunityFeed`.
- Grants/conferences/papers: a "Lab / Mine" scope toggle where feasible.

### Phase 6 — "Who's interested?" collaboration layer
- For a lab/project item, surface members whose *individual* `RelevanceScore` for the
  same `ContentItem` clears a threshold (or on-demand profile-vs-item cosine). Render
  member chips on the card. Seeds the collaboration-suggestions goal.

## Interfaces / files that change

- Backend: `content/targets.py` (new), `content/pipeline.py`, `content/opportunities.py`,
  `content/refitting.py`, `content/views.py` + `serializers.py` + `urls.py`,
  `research/views.py` + `serializers.py` + `urls.py`, `content/tasks.py`.
- Frontend: `lab-overview-section.tsx`, `project-detail-section.tsx`, grants/conferences/
  papers sections, `lib/portal/{client,hooks,types}.ts`.
- Docs: `docs/repo-map.md`, `docs/changelog.md`, this plan.

## Validation & acceptance

- Unit + pgvector tests: a lab and a lab project each produce `target_lab`/
  `target_project` `RelevanceScore` rows on the correct FK, distinct from the members'
  own scores; a project's declared focus changes its matches; re-runs are idempotent.
- Permission tests: only lab members read lab feeds; only `visible_to` users read a
  project's recommendations.
- No LLM-cost regression: per-target LLM scoring stays capped and logged.
- Frontend: `tsc` + `eslint` + `next build` clean (the worktree cannot be
  browser-verified — Preview MCP is pinned to the main checkout).

## Explicit exclusions

Fellowships at lab/project scope; the Neo4j knowledge graph; Slack/Discord digests;
department-scoped matching (the target abstraction leaves room for it, but it is not
wired in this pass); auto-linking arbitrary DOIs to a project (the disabled
"paste a DOI" box) — a separate manual-curation feature.

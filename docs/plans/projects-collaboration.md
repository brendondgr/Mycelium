# Projects Page — Team Collaboration (MVP)

**Status:** in progress · branch `projects-collab` (isolated worktree)
**Source brief:** the six-feature "Workspace Sharing & Collaboration" plan, reconciled to
Mycelium's real models. **This session builds the approved MVP slice: B + A + E + light D.**

## Objective

Turn the project detail page from an individual recommendation feed into a real
**team collaboration surface**: members can share a paper into a shared project feed,
paste an external DOI / arXiv / URL to pull a paper in, the feed dedupes and shows who
else has seen each item, and lightweight engagement events are captured for a future
team-relevance signal. All in-app, reusing `ContentItem` / `RelevanceScore`.

## Reconciliation with the brief (what changed and why)

| Brief assumption | Mycelium reality | Decision |
|---|---|---|
| Unified `Workspace` (Lab/Dept) as the collab unit | No such model; `Project` has real `ProjectMember` membership, visibility, and `recommend_for_project()` scoring; the project detail page already ships **disabled** paste-a-link + feed UI | **Project is the collaboration unit** |
| `shared_by → Membership` | `ProjectMember` has no roles; equality of members | Use `shared_by → User`, gate by project participation |
| Slack/Discord delivery exists | Confirmed **absent**; deferred in `docs/goals.md` | **In-app only** (feed + seen badges); no external delivery |
| New `WorkspaceItemSeen` / `MemberSuggestion` tables | `RelevanceScore` is a universal polymorphic table; `ContentItem` already dedups on `(source, external_id)` | Reuse where natural; add only the 3 records the brief needs |
| D2 "embedding dimension lock" is a blocker | `ContentItem` embeddings are real (fastembed `bge-small-en-v1.5`, 384‑dim); retrieval embeds interest text on demand | Not a blocker for this MVP; noted for deferred F |

## Scope

**In:** B (project seen/dedup ledger), A (share to project + feed), E (paste-a-link
ingest), lightweight D (weighted engagement events + "seen by / who's interested").
**Deferred (clean seams left):** C (collections), full D (project-profile recompute),
F (cross-member fan-out + notifications). The share service leaves a `# fan-out seam`
hook; events are captured now so D has data when it lands.

## Data model (new — `content` app, beside `SavedOpportunity`)

- **`ProjectShare`** — `project`(FK research.Project), `content`(FK ContentItem),
  `shared_by`(FK User), `note`(text), `source`(digest|external_link|collection),
  `created_at`. Index `(project, created_at)`. No unique on `(project, content)` —
  re-shares allowed; the feed collapses by `content`.
- **`ProjectItemSeen`** — `project`, `content`, `first_seen_at`, `first_seen_via`
  (digest|share|external_link), `seen_by`(M2M User). `unique_together (project, content)`.
  The dedup ledger: one row per paper per project.
- **`RelevanceEvent`** — `user`, `project`(nullable), `content`, `action`
  (view|save|share|thumbs_up|thumbs_down|dismiss|open_external), `weight`(float,
  config-driven), `created_at`. Indexes `(project, created_at)`, `(user, content)`.
  Append-only weak-label stream for the future team signal.

## Config (settings.py)

`RELEVANCE_EVENT_WEIGHTS` (env-tunable): view 0.1, open_external 0.3, save 0.5,
share 0.7, thumbs_up 1.0, dismiss −0.3, thumbs_down −0.7.

## Services (`content/collaboration.py`, new)

- `mark_seen(project, content, via, user=None)` — idempotent upsert of `ProjectItemSeen`;
  adds `user` to `seen_by` when given. First path wins for `first_seen_via`.
- `project_seen_map(project, content_ids) -> {id: {first_seen_at, first_seen_via, seen_by_count}}`
  — one query, for feed badging (no N+1).
- `record_event(user, content, action, project=None)` — writes `RelevanceEvent` with the
  configured weight.
- `share_to_project(project, content, user, note, source)` — creates `ProjectShare`,
  `mark_seen(via='share')`, `record_event('share')`; returns the share. Leaves the
  fan-out seam.

## External ingest (Feature E) — DONE (parallel)

`scraper/resolver.py` (`resolve_external(raw_input) -> ResolveResult{content_item, created, embed_status}`)
+ `ResolveError`. Detects arXiv / DOI / URL, fetches canonical metadata (arXiv API /
Crossref +OpenAlex enrich / OpenAlex), dedups on `(source, external_id)`, embeds the
abstract (or `embed_status='no_abstract'`). 14 unit tests pass (network + embedder mocked).

## API (research app — project-scoped routes, reuse project visibility gate)

All under `/api/projects/<uuid:pk>/…`, both slash + no-slash variants:
- `POST …/shares/` `{content_item, note, source?}` → participant gate → `share_to_project`.
- `GET  …/feed/` → shares collapsed by `content` (co-sharers surfaced), seen-map annotated.
- `POST …/ingest-link/` `{raw_input, note?}` → participant gate → `resolve_external`
  (422 on `ResolveError`) → `share_to_project(source='external_link')`. Returns share +
  `embed_status`.
- `POST …/items/<uuid:content_id>/seen/` → visible gate → `mark_seen(user=…)` +
  `record_event('view')`; returns seen metadata.
- `POST …/events/` `{content_item, action}` → participant gate → `record_event`.

Gate helper `_user_is_project_participant(user, project)`: a `ProjectMember`, the personal
owner, or a lab manager of a lab project. Read endpoints use `project.is_visible_to`.
All mutating endpoints `record_audit_event`.

## Backfill

`backfill_project_seen` management command: walk `RelevanceScore(target_project=…)` rows
→ `mark_seen(via='digest')` so day-one "already surfaced in this project" is accurate.

## Frontend (`web/app`)

Activate the **already-present disabled UI** in `project-detail-section.tsx`:
- Enable the DOI/article input → `useIngestProjectLink` mutation → resolving/success/422 states.
- Project Feed card → `useProjectFeed(id)` → share rows (sharer, note, "also seen by N",
  co-sharers), reusing `PaperFeedRow` styling + `SaveButton`.
- "Share to project" affordance on the Mylo/recommended rows → `useShareToProject`.
- Data layer: `types.ts` (ProjectShare/FeedItem), `client.ts` (`fetchProjectFeed`),
  `mutations.ts` (`shareToProject`, `ingestProjectLink`, `markProjectItemSeen`), `hooks.ts`.
- Heed `web/AGENTS.md`: modified Next.js — stay within existing client-component + react-query patterns.

## Validation gates (validate at each step)

1. **Models** → `makemigrations` (one migration) + `migrate` on the compose Postgres;
   `manage.py check` clean.
2. **Services + endpoints** → `APITestCase` (pytest-style, matches app convention):
   share creates share+seen+event; non-participant 403; re-share collapses in feed;
   ingest dedups (mock `resolve_external`); garbage → 422; mark-seen increments seen_by;
   backfill populates from project scores. Run against compose Postgres.
3. **Frontend** → `tsc --noEmit`, `eslint`, `next build` (worktree-safe; browser preview
   is pinned to the main checkout).
4. **Docs** → update `docs/repo-map.md` + `docs/changelog.md`.
5. **Commit** on `projects-collab` (no push).
6. **Merge to main** — attempt only if it does not collide with the concurrent
   `unified-search` WIP; otherwise leave committed on the branch and report.

## Acceptance criteria (smoke)

- Member shares a digest item → appears in project feed with note; seen badge correct.
- Second member re-shares same item → feed collapses, both credited, one seen row.
- Paste an arXiv id / DOI → resolves, dedups if present, lands as an external share.
- Paste garbage → 422, nothing created.
- Mark-seen increments `seen_by` only on real view, not on delivery/backfill.
- Non-participant blocked from share/ingest/event (403); non-visible blocked from feed.
- No individual `Profile` is mutated; no `RelevanceScore` semantics changed.

## Explicit exclusions (Phase 1)

Slack/Discord, Neo4j/graph signals. (Collections, team-profile recompute, and
cross-member fan-out moved into Phase 2 below.)

---

# Phase 2 — Collections (C), Team signal (D), Fan-out (F)

**Status:** complete (backend + frontend, verified) · same branch `projects-collab`, on top of Phase 1.
All Project-scoped, all in-app, reusing `ContentItem` embeddings (384-dim) + `RelevanceScore`.

## Feature C — Shared collections / reading lists

**Models (`content` app):**
- `Collection` — `project`(FK), `name`, `description`, `created_by`(User), `is_archived`
  (default False), `created_at`.
- `CollectionItem` — `collection`(FK), `content`(FK ContentItem), `added_by`(User),
  `note`, `added_at`. `unique_together (collection, content)` (no dupes → 200, not 500).

**Endpoints (research app, project-scoped):**
- `GET/POST /api/projects/<id>/collections/` — list (excludes archived by default) / create.
- `GET/PATCH /api/projects/<id>/collections/<cid>/` — detail (with items) / rename / archive.
- `POST /api/projects/<id>/collections/<cid>/items/` `{content_item, note?}` — add;
  also `mark_seen(via='share')` + `record_event('save')`.
- `DELETE /api/projects/<id>/collections/<cid>/items/<content_id>/` — remove.
Participant gate for writes, visible gate for reads. Archiving hides but preserves items.

## Feature D — Team relevance signal (project profile recompute)

**Model `ProjectProfile`** (OneToOne → Project; **never** touches individual `Profile`):
`interests`(JSON aggregated terms), `embedding`(VectorField 384), `last_recomputed`,
`recompute_reason` (membership_change | engagement | manual).

**Service `recompute_project_profile(project, reason)`:**
1. Member interest vectors: each member's `Profile.embedding`, or embed their canonical
   interest text on demand when null.
2. Engagement vectors: `ContentItem.embedding` for items members engaged with, weighted by
   `RelevanceEvent.weight × time-decay` (90-day half-life, `PROJECT_PROFILE_HALFLIFE_DAYS`).
   Negative-weight actions (dismiss/thumbs_down) subtract.
3. **Normalize every vector before combining** (project principle). Weighted centroid of
   members (`PROJECT_PROFILE_MEMBER_WEIGHT`, default 0.6) + engagement
   (`PROJECT_PROFILE_ENGAGEMENT_WEIGHT`, default 0.4). Aggregate interest terms too.
4. Stamp `last_recomputed` / `recompute_reason`.

**Triggers:** membership add/remove (immediate, from join/leave/members endpoints);
`recompute_project_profiles` management command + Celery task; optional nightly beat.
**Feeds:** blended into the project's recommendation target so engagement measurably
shifts ranking (a paper 3 members thumbs-up outranks one 1 member thumbs-up).

## Feature F — Cross-member relevance fan-out + in-app notifications

**Model `MemberSuggestion`:** `user`(recipient), `project`(FK), `content`(FK),
`origin_share`(FK ProjectShare null), `score`(float normalized cosine), `suggested`(bool),
`floor_used`(float), `delivered_via`(default 'in_app'), `dismissed`(bool), `created_at`.
`unique_together (user, content)` — never notify the same member twice for the same paper.

**Task `fanout_relevance(share_id)`** (enqueued from `share_to_project`'s seam):
1. Load `ContentItem.embedding`; abort if null (no abstract → nothing to score).
2. For each active project member **except the sharer**:
   - `member_vector` = `Profile.embedding` or on-demand embed of interest text.
   - **Score the normalized cosine directly** (never an RRF rank — project principle).
   - `≥ FANOUT_COSINE_FLOOR` (default 0.35) → `MemberSuggestion(suggested=True)` + deliver
     in-app; else persist `suggested=False` (abstention, audited), no notify.
3. Respect `unique_together` — never double-notify.
Delivery: in-app only (Slack/Discord absent/deferred). Two-tier push margin deferred.

**Read surface:** `GET /api/suggestions/` (own `suggested=True`, undismissed) +
`POST /api/suggestions/<id>/dismiss/` (records a `dismiss` event). Surfaced in the header
notification bell alongside deadline alerts, plus a "Suggested for you" list.

## Open decisions — resolved defaults (brief §8)
D1 weights: set (Phase 1). D3 decay: 90-day half-life. D4 floor: global 0.35, env-tunable
(`FANOUT_COSINE_FLOOR`); per-member push-margin deferred. D6: **Project-member scope** for
fan-out (our workspace = project); dept-wide deferred. D7: membership-change immediate +
nightly beat.

## Validation (Phase 2)
- C: add/list/archive/remove tests; duplicate add → 200; archive hides but preserves;
  non-participant 403.
- D: recompute never mutates any `Profile`; 3× thumbs-up outranks 1×; negative weight lowers
  a topic's presence; normalize-before-fuse asserted.
- F: below every floor → 0 `suggested=True`, N audit rows; sharer never suggested to self;
  re-share never double-notifies; threshold reads cosine, not RRF.
- Frontend: `tsc` + `eslint` + `next build` clean.

# Lab feed parity + member recommendations

## Objective

Two changes, one sprint:

1. **Parity.** The lab workspace's Research Papers, Grants, Fellowships and
   Conferences pages must be structurally identical to their personal-space
   counterparts — same layout, same filter rail, same card, same behaviour, all
   of it visible. Papers/Grants/Conferences already reuse the personal section
   bodies; **Fellowships is the one page that does not**, because at lab scope a
   fellowship is currently only a read-time union of member eligibility rather
   than a scored feed.
2. **Recommendations.** Layer on the one genuinely new capability: for every
   item in every lab feed, Mylo says **who in the lab it is most applicable to**,
   grounded in each member's own background and research interests. Papers, the
   daily paper report, grants, fellowships and conferences all get it.

## Assumptions

- **A1 — Lab fellowships become a scored target.** Decision D-1 ("fellowships
  are individual, so a lab never scores them") is superseded for the *feed*: a
  lab target scores fellowships on research fit only, exactly as a project
  already does (`match_fellowships(skip_eligibility=True)` — a lab has no
  citizenship or career stage). This is what makes the page structurally
  identical to the personal one.
- **A2 — D-11 survives.** The *eligibility* claim ("Ana qualifies") is still
  disclosed only for members who are qualified/conditional **and** opted into
  `interests.eligibility.lab_visible`. It moves from being the card to being one
  basis inside the new recommendation layer. Research-fit recommendations are
  not eligibility claims and follow the same disclosure rule the existing
  `interested` map already uses for papers/grants/conferences.
- **A3 — Mylo drives, arithmetic backs him up.** The member ranking is a cosine
  between the item vector and each member's profile vector (deterministic,
  always present); Mylo's LLM pass writes the *why* and may re-order the top
  few. Every LLM seam degrades to the deterministic ranking, per the house rule.
- **A4** — the recommendation layer is computed at scoring time and persisted in
  `RelevanceScore.signals`, so the read path stays a single query per area.

## Phases

### Phase 1 — Lab fellowships become a first-class scored feed (backend)

- `content/opportunities.py`: `run_opportunities_for_target` routes
  `fellowships` for `target.kind in {"project", "lab"}`;
  `run_daily_opportunities_batch` fans the day's new fellowships out to labs
  alongside projects (append semantics unchanged).
- `content/refitting.py`: labs refit fellowships too (whole-corpus replace).
- `content/views.py`: `_recommendations_payload` serves a lab's fellowships from
  its own `target_lab` scores through `FellowshipSerializer`; `_window_counts`
  counts the same rows.
- Member eligibility is kept, but as an input to Phase 2 rather than a card.

### Phase 2 — The member-fit layer (backend)

- New `content/member_fit.py`: `member_fit_for_scores(...)` ranks a scope's
  members per item by cosine (reusing `fanout.member_vector` / `_cosine`),
  above `MEMBER_FIT_COSINE_FLOOR`, capped at `MEMBER_FIT_MAX_MEMBERS`, and
  persists `signals["member_fit"]`.
- New `content/member_llm.py`: Mylo the consultant — reads the item and the
  candidate members' profiles and returns who it is most applicable to plus a
  one-line why; deterministic templated fallback from the shared interests.
- Wired into `refitting.refit_lab` and the daily lab batch; backfill command
  `annotate_member_fit`.

### Phase 3 — `recommended_for` on the API

- `_recommendations_payload` emits `recommended_for: {content_id: [...]}`,
  merging persisted member fit, the existing `interested` map (a member's own
  strong personal match), and — fellowships only — the consented eligibility
  tier. One shape for all four areas.

### Phase 4 — Lab Fellowships gets the personal structure (frontend)

- Delete `LabFellowshipsFeed` / `LabFellowshipRow`; both scopes render the same
  `FellowshipsFeed` body (filter rail, infinite reveal, `FellowshipRow`), with
  `labName` swapping copy only.
- `EligibilityBadge` renders only when a tier exists (a lab/project fellowship
  has none, and must not claim "Possible fit").
- `TargetRecommendations.fellowships` becomes `FellowshipOpportunity[]`.

### Phase 5 — "Recommended for" on the cards (frontend)

- New `portal/primitives/recommended-for.tsx`.
- Optional `recommendedFor` prop on `SuggestionCard`, `GrantRow`,
  `FellowshipRow`, `ConferenceCard` — absent on personal pages, so they are
  untouched.
- Threaded through all four lab feeds and the lab overview panels.

### Phase 6 — Daily papers adjusted (backend)

- Labs now score fellowships, so `LAB_BRIEFING_CATEGORIES` gains fellowships.
- The lab briefing specialists name who each item suits, from `member_fit`.

## Interfaces that change

- `GET /api/labs/<slug>/recommendations/` — `fellowships[]` becomes the standard
  fellowship card shape; new `recommended_for` map (additive).
- `GET /api/projects/<id>/recommendations/` — new `recommended_for` map.
- `RelevanceScore.signals["member_fit"]` — new, additive, no migration.
- Settings: `MEMBER_FIT_COSINE_FLOOR`, `MEMBER_FIT_MAX_MEMBERS`,
  `MEMBER_FIT_LLM_LIMIT`.

## Validation

- `uv run --directory web/backend python -m pytest -q` against the compose
  Postgres, with new tests per phase.
- `npm run typecheck` / `lint` / `build` in `web/app`.
- Docs: `docs/repo-map.md` rows for the changed areas, `docs/changelog.md`.

## Exclusions

- No change to personal-space behaviour beyond the empty-tier badge fix.
- No department-scope recommendations.
- No push delivery (Discord/Slack) of member recommendations this pass.

# Fellowship Matching — Implementation Plan

Working document for the fixes diagnosed in
`docs/fellowship-matching-investigation.md`. Delete both when the work ships.

## Objective

Make career stage actually bind on fellowship matching, and make the percentages
on a lab fellowship card mean one thing each.

## Decisions taken (locked by the user)

1. **Stage gate:** F1 asymmetric ladder. Hard-drop only when the award's
   *minimum* stage exceeds the user's. Over-qualified stays soft.
2. **Stage availability:** derive first, then require. Map
   `academic_title` / `eligibility.career_stage` → `eligibility.stage`; make the
   onboarding stage choice required only when nothing derives.
3. **Chip percent:** the member's own-feed percent, falling back to the profile
   cosine, each labelled with its own scope. Never both undifferentiated.
4. **Scope:** everything — F1 through F11, including the F3 ingest extraction.

## Assumptions

- `researcher` and `staff` are ambiguous titles (a staff scientist and a senior
  grad student both pick them), so they derive *nothing*; `student` →
  `doctoral_early`, `postdoc`/`pi` → `postdoc`.
- A user whose stage is still unknown keeps today's soft behaviour. Gating on an
  unknown stage would silently empty feeds for every existing account.
- `max_years_post_phd` can only gate when the profile records a PhD year, so a
  new optional `eligibility.phd_completed_year` is added and the gate applies
  only when both sides are known.
- A facet-empty (scrape-miss) record is tiered `unverified` and labelled, not
  withheld — silently dropping 33 real awards is worse than labelling them. A
  setting allows withholding instead.
- F5 omits ineligible members silently, disclosing nothing. This is the reading
  of D-11 the investigation argues for and the user accepted.

## Phases

Each phase is independently committable and independently validated.

### Phase 1 — the stage ladder (F1)

`web/backend/apps/content/fellowships.py`

- Add `STAGE_RANK` (user token → int) and `FACET_STAGE_RANK` (Illinois facet
  string → int) over the ladder
  `masters < doctoral_early < doctoral_dissertation < postdoc`.
- `Elig` gains `stage: str` (the raw token) beside the existing `stage_tokens`.
- In `evaluate_eligibility`, add to `gates` when the user's stage is known and
  `min(rank of stage_f) > rank(user stage)`. Nothing else becomes a gate.

**Validate:** new unit tests in `apps/content/tests/` — postdoc-only award +
early-doctoral user → `not_eligible`; the reverse → not gated; unknown user
stage → unchanged from today.

### Phase 2 — make stage exist (F2)

- `fellowships.py`: `derive_stage(profile)` — explicit `eligibility.stage`, then
  `eligibility.career_stage`, then `Profile.academic_title`. Wired into
  `eligibility_from_profile`, so existing accounts gain a stage with no data
  migration.
- `apps/accounts/intake/agent.py`: write `stage` alongside `career_stage`.
- `apps/accounts/interests.py`: document the derivation; add optional
  `phd_completed_year`.
- `onboarding-flow.tsx`: extend `stageFromRole` to cover `pi`; require a
  non-empty stage to leave the eligibility step (the derivation pre-fills it, so
  the requirement only bites when nothing derived); show the PhD-year field when
  the stage is `postdoc`.

**Validate:** backend tests for each derivation source and precedence;
`npm run lint` + `tsc` for the onboarding change.

### Phase 3 — parse the prose (F3)

- New `apps/scraper/pivot/fellowships/constraints.py`: a deterministic regex
  pass (the `within N years` / `received the PhD` class) with an LLM seam for
  the rest, emitting
  `{min_stage, max_years_post_phd, degree_required, source, evidence}`.
- `records.py` writes `metadata["constraints"]`; re-ingest carries an existing
  block forward so extraction is once-per-record, not nightly.
- `evaluate_eligibility` gates on `constraints.min_stage` by the same asymmetric
  rule, on `degree_required == "phd"` for a pre-PhD user, and on
  `max_years_post_phd` when `phd_completed_year` is known.
- Setting `FELLOWSHIP_CONSTRAINT_EXTRACTION` (default on, LLM step degrades to
  regex-only when the model is unavailable).

**Validate:** parser unit tests over the real phrasings; an eligibility test per
new gate.

### Phase 4 — fail closed on a scrape miss (F4)

- `parsers.py`: `facets_incomplete` flag when every facet bucket is empty.
- `evaluate_eligibility`: such a record tiers `unverified` — never `qualified` —
  with an explicit reason. `unverified` is not an eligible tier for the lab
  disclosure.
- `FELLOWSHIP_WITHHOLD_UNVERIFIED` (default `False`) drops them instead.
- Frontend badge gains the third tier.

**Validate:** ingest test that a facet-less record is flagged; eligibility test
that it tiers `unverified`.

### Phase 5 — the lab strip stops naming ineligible members (F5)

`apps/content/views.py`

- `_recommended_for` evaluates each rostered member's own `Elig` against each
  fellowship's metadata in-process (pure function, no extra queries) and drops
  hard-fails from that item's strip. Read-time, so it corrects rows already
  persisted without a re-score.
- Nothing is disclosed about who was dropped.

**Validate:** view test — a postdoc-only fellowship on a lab feed never names
the pre-PhD member, and still names the postdoc.

### Phase 6 — one scale per label (F8, F9, F10)

- `_recommended_for` emits `profile_cosine` and `own_feed_percent` instead of
  the polymorphic `fit`.
- Ordering: Mylo-explained (`profile_fit`) members first, each group sorted on
  its own scale, so the explained recommendation leads the strip.
- `recommended-for.tsx`: chip shows the own-feed percent when present, else the
  profile cosine, always labelled with its scope; tooltip and basis note name
  which is which.
- `types.ts` and `docs/api-contract.md` updated.

**Validate:** view test for the two fields and the ordering; `tsc` + lint.

### Phase 7 — honest numbers and copy (F6, F7, F11)

- `opportunity_llm.py`: clamp a model percent on a `conditional`/`unverified`
  row to the computed percent, so a hedged item cannot carry a confident number.
- `fellowships-section.tsx`: subtitle no longer promises eligibility-filtered
  results unconditionally; ring labelled with its scope on a lab feed; a notice
  when the reader's own stage is unset.
- `FellowshipsView` returns `stage_set` so the notice is truthful.

**Validate:** `tsc` + lint; backend test for the clamp.

### Phase 8 — orchestrator audit and docs

- Confirm `manual_all.py`'s stage list is unchanged and that no refit was
  introduced: every change here is either read-time (Phases 5–7) or affects
  scoring of *new* items only (Phases 1–4). Existing wrongly-surfaced rows clear
  on the next on-demand `run_refitting`, which stays out of the daily chain.
- Update `docs/repo-map.md`, `docs/api-contract.md`, `docs/changelog.md`.
- Delete this plan and the investigation doc.

## Interfaces that change

| Surface | Change |
|---|---|
| `RelevanceScore.signals` | unchanged |
| `metadata["constraints"]` | new block on fellowship ContentItems |
| `metadata["flags"]["facets_incomplete"]` | new |
| `interests.eligibility.phd_completed_year` | new optional int |
| Lab/project `recommended_for[]` | `fit` → `profile_cosine` + `own_feed_percent` |
| `GET /api/fellowships/` | adds `stage_set` |
| Fellowship `tier` | adds `unverified` |

## Validation commands

```bash
uv run --project web/backend python -m pytest apps/content/tests apps/scraper/tests apps/accounts/tests -q
```

```bash
npm --prefix web/app run lint && npx --prefix web/app tsc --noEmit
```

## Exclusions

- No change to `FELLOWSHIP_FIT_THRESHOLD` / `FELLOWSHIP_MATCH_THRESHOLD`
  defaults — the gate is the fix, not a tuned floor.
- No refit scheduled into the daily chain.
- No new onboarding step; the eligibility step already exists.

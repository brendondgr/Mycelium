# Plan CN-05 — The Matcher

**Status:** draft. **Depends on:** CN-02, CN-03, CN-04. **Unblocks:** CN-06.
**Correlation ID:** `20260918-collaboration-network-05`

## Objective

One matcher behind three entry points: from a call, from a project, or typed by
hand (`design §8.1`). It takes an editable query, runs one retrieval per lane,
credits works to their authors, passes every candidate through a hard consent
gate, lets a model explain (never add to) a short list, and returns results
grouped by lane — never merged (`design §6`, `§9.1`). It launches at
**institution scope only**.

## The query object

1. `{slots, lanes, scope}`, the same shape from every entry point:
   - **call** — CN-03's slots, with coverage marked;
   - **project** — the project's declared edges as slots, read through
     `read.project_edges(project, viewer)`;
   - **manual** — the seeker's text run through the same slot extractor as
     calls, with the same schema and grounding against what they typed.
   The seeker edits it before running. Lanes default to all four; scope
   defaults to, and is capped at, `COLLAB_MAX_SCOPE` (`institution` at
   launch).
2. Nothing about the query is written anywhere shared (principle 6). Query
   vectors are computed per request and discarded. The seeker's own search
   history (`SearchLog`: slots, lanes, scope, time) is private to them and
   deleted after 90 days.

## Lanes

3. Each lane is its own retrieval over `WorkFacets` vectors of works whose
   authors could pass the gate, per `design §4`:

   | Lane | Retrieve on | Must differ |
   |---|---|---|
   | In-field | problem ∧ setting | — |
   | Method bridge | method (field-specific **or** neutral phrasing) | field (`openalex_field_id`) |
   | Problem bridge | problem | setting and method |
   | Resource | `reusable` (offer) ↔ data slots | — |

   "Differ" uses the field ruler at field level (`design §5.6`); a work with
   an unknown field is eligible for in-field and resource lanes only.
4. Declared edges also retrieve (a person's declared `uses_method` can match a
   method slot) but rank below demonstrated evidence and carry the
   `declared` tag (`design §5.4`).
5. **Author aggregation** (`design §5.2`). A person's lane score is their best
   work's score with a mild recency preference (OD-CN02a); never an average.
   Author position is not weighted.

## The hard gate

6. Applied after aggregation, before anything is shown or explained. A
   candidate passes only if every one holds:
   - `CollaborationSetting.open`, not expired;
   - their `audience` includes the seeker and the seeker's `scope` includes
     them, both from `VerifiedAffiliation`;
   - under the appearance cap, or already seen by this seeker this week;
   - not the seeker; not a member of the seeker's lab (they belong in
     CN-03's team-internal view); not an existing co-author of the seeker
     (CN-02's author ids);
   - their evidence came from `read.discoverable_edges` or their works — never
     a conversational or project edge (principle 5, enforced by the boundary
     test from CN-01).
7. The gate writes the `Appearance` row for each candidate actually returned.

## Rerank and rationale

8. The top `COLLAB_SHORTLIST_PER_LANE` (default 8) per lane go to the model
   with the query's slots and each candidate's matching facets (not their
   whole profile): a verdict (keep / drop) and a one-line rationale naming the
   facet that matched. The model may drop a candidate and may never add one;
   any name not in the shortlist is discarded (the `member_fit.py` rule).
9. Without the model the lanes return in retrieval order with the matched
   facet shown and no rationale, and the panel says the explanations are
   unavailable. (The ambient series' no-fallback rule is specific to reading
   conversation; this follows the repo's usual degrade-to-deterministic
   convention.)

## Results

10. The rollup (`design §4`): **Fills a gap** = method bridge, problem bridge,
    and resource, applied to uncovered slots; **Shares expertise** = in-field,
    applied to covered slots. Each lane has guaranteed places
    (`COLLAB_RESULTS_PER_LANE`, default 3) and each result a lane label.
11. A result is a coarse pointer: name, verified affiliation, the one matching
    facet, its tier, and the rationale. Nothing else about the person.
12. **Save** and **Not relevant** write `MatchFeedback` (append-only). Nothing
    is sent to the candidate, ever (`design §9.3`).

## Cost and limits

13. Runs on click only (`design §8.1`). A result is cached per query hash for a
    day for the same seeker. At most `COLLAB_SEARCHES_PER_DAY` searches per
    seeker (default 20). Model cost is logged in the daily LLM ledger under
    its own component name.

## Q4

14. A search from a fixture project needing a method, with an opted-in
    candidate in another field whose paper uses that method, returns them in
    the method-bridge lane; the proof query.

## Steps

15. Query object and the manual slot path; `SearchLog`.
16. Lane retrievals and aggregation.
17. The gate and `Appearance` writes.
18. Rerank prompt, verdict validation, the model-down path.
19. `POST /api/collab/search/`, feedback endpoints.
20. Tests, including every gate condition negated one at a time; changelog;
    repo map; `docs/api-contract.md`.

## Acceptance

- Negating any single gate condition removes the candidate; a test per
  condition.
- A candidate whose only match is a conversational edge never appears.
- Every lane that has results shows them; no lane is crowded out by another.
- No shared table row contains project text or a query vector after a search.
- A name the model returns that was not shortlisted never reaches the response.

## Open decisions

- **OD-CN05a** Launch scope. Recommendation: `institution` until CN-08's
  first human-judgment round and concentration numbers are in.
- **OD-CN05b** Whether lab-mates are excluded or shown in a separate "in your
  lab" group. Recommendation: excluded here; CN-03's line already shows them.

## Sandbox validation (before moving on)

The largest run in the series, because the matcher is where every earlier
plan meets. The world is scaled up (at least 600 people across the six
institutions) and the planted truth defines, for every project need and every
call gap, which opted-in people *should* appear in which lane: same field and
problem (in-field), same method in another field (method bridge), same problem
by another method (problem bridge), a reusable dataset (resource).

- **Lane recall@k and precision@k** against that truth, per lane, with the
  bridge lanes reported separately — a method-bridge result from the same
  field is a failure, not a hit.
- **The gate, exhaustively:** every search's results re-checked against
  consent, audience ∩ scope, the appearance cap, lab-mates and co-authors
  excluded. Any violation is an invariant failure.
- **The model never adds a name:** every rationale's person is in the
  shortlist (invariant).
- **Load:** a simulated week of searches (hundreds of seekers) to measure the
  appearance cap's effect on concentration (Gini before and after the cap) and
  per-search latency p50/p95 with the model on and off.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.

# Plan CN-02 — Demonstrated Expertise

**Status:** draft. **Depends on:** CN-01. **Unblocks:** CN-04, CN-05.
**Correlation ID:** `20260918-collaboration-network-02`

## Objective

Give every person a `demonstrated` side: what their own published works show,
decomposed by facet, one work at a time (`design §5.1–5.4`). This is the paper
side of document-centric retrieval — the matcher ranks works, then credits
their authors — and the evidence tag that separates "says they do this" from
"has published doing this".

## Facets per work

1. **`WorkFacets`** (in `apps/knowledge`; the first **amendment** to the
   shared core, recorded in the README when it lands): one row per
   `AuthorWork`, holding `problem`,
   `method`, `setting`, `reusable` (the offer), `method_neutral` (the
   field-neutral phrasing), `openalex_field_id`, one embedding per facet
   (`problem_vec`, `method_vec`, `setting_vec`, `reusable_vec`),
   `prompt_version`, and `source_fingerprint`.
2. **The extractor** reuses `apps/content/comprehension.py`'s discipline:
   profile-blind (the reader is absent from the input), a fixed schema,
   deterministic validation, one repair, then refusal, and a cache key of
   (prompt version, source fingerprint) — never time. It adds one field the
   corpus précis does not have: `method_neutral`, the method restated without
   field vocabulary ("estimating a hidden state from noisy observations"),
   with an instruction and a validator against over-abstraction (a neutral
   phrase must keep the operation, not collapse to "uses statistics";
   a phrase from a short deny-list of empty abstractions is refused). Methods
   only, per OD-CN3; problems later if CN-08 shows method transfer works.
3. When an `AuthorWork` has a DOI that matches a `ContentItem` with an
   `ItemComprehension`, the existing précis is reused and only the neutral
   phrase is asked for. One model call per work, ever.
4. **Grounding.** Every facet must share content words with the work's title
   and abstract, using `state_extract.py`'s floor. A work with no abstract gets
   a title-only pass and is marked thin; thin works never produce
   `demonstrated` edges on their own.

## Field and co-authors

5. **Field.** For works imported from OpenAlex, the work's primary topic's
   field id; for others, one OpenAlex lookup by DOI, cached; otherwise
   unknown. A person's fields are the fields of their works. Unknown is a real
   value and is never guessed.
6. **Co-author identity.** `AuthorWork.coauthors` holds names only. Where the
   source gives author ids (OpenAlex), keep them alongside, so CN-05's
   exclusion ("already works with the seeker") and CN-07's introduction paths
   rest on identities, not name matching.

## Demonstrated edges

7. Each non-thin work links its facets through the CN-01 linker **in global
   scope** (a published work is public): `works_on` (problem),
   `uses_method` (method, and the neutral phrase as an alias of the same
   concept), `works_in_setting` (setting), `offers` (reusable). Edges hang off
   the `author_work` subject, and a rolled-up `user` edge carries the work
   count and the most recent year as recency. Nothing is averaged into one
   vector per person (`design §5.3`); the per-work vectors stay per work.
8. The linker's `openalex_field_id` on a concept is set from the works that
   minted it when they agree, and left null when they do not.

## Q2

9. `read.own_edges` gains a comparison view: for each of a person's declared
   concepts, whether a demonstrated edge backs it and from which works. The
   person sees it on their profile page later (CN-04 preview uses it); it is
   the proof query.

## Steps

10. `WorkFacets` model and migration.
11. The work extractor (prompt, schema, validator, repair, neutral-phrase
    guard) and the DOI reuse path.
12. OpenAlex field and author-id enrichment, cached.
13. Linking and `demonstrated` edges; the rollup.
14. A backfill command bounded per night (`KNOWLEDGE_WORK_FACETS_NIGHTLY_CAP`,
    default 200 works), added to the nightly run outside `CONTAINER_STAGES`
    so its failure never fails the run; new imports are faceted on arrival.
15. Q2 and its test; changelog; repo map.

## Acceptance

- A work with a changed abstract is re-extracted; an unchanged one never is.
- A thin work produces no demonstrated edge.
- No person has a single averaged expertise vector anywhere in the schema.
- A neutral phrase from the deny-list is refused and the work keeps its
  field-specific method only.
- Q2 on a fixture person returns declared-and-demonstrated, declared-only, and
  demonstrated-only concepts correctly.

## Open decisions

- **OD-CN02a** Recency weighting. Recommendation: none in storage; the matcher
  applies a mild recency preference at query time (CN-05), so it can be tuned
  without re-extraction.
- **OD-CN02b** Whether demonstrated edges are shown to the person before they
  opt in to collaboration. Recommendation: yes — it is their own record, and it
  is what the preview (CN-04) shows others.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.

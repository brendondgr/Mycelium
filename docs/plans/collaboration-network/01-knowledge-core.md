# Plan CN-01 — The Knowledge Core

**Status:** draft. **Depends on:** nothing. **Unblocks:** CN-02, CN-03, and
ambient-profile Plans 04 and 05.
**Correlation ID:** `20260918-collaboration-network-01`

## Objective

Build the one structure both series need: **concepts** and **typed, evidenced
edges** from people, projects, labs, and works to those concepts, in
`apps/knowledge`. Load what already exists — declared profiles and stated
project state — as `declared` edges. Give every other app one door in and one
tier-filtered door out.

This is the "choose the approach, define node and edge types, load existing
content" of `docs/goals.md` Next 1. The approach is Postgres + pgvector, not
Neo4j: every question the two series ask in their first plans is one or two
hops, and deletion must cascade through foreign keys so that "delete my
observations" and "forget me" stay guaranteed rather than best-effort across
two stores (`design §10`, OD-CN6).

## The model

1. **`Concept`** — one idea, independent of who holds it.
   - `label` (≤ 80 chars, Mylo's canonical wording), `facet` ∈ {`area`,
     `problem`, `method`, `setting`}. `area` holds broad declared research
     areas that are not one facet ("machine learning"); the other three are
     `design §3`'s facets. Offer and need are edge relations, not facets.
   - `neutral_label` (blank until CN-02 fills it for methods): the
     field-neutral phrasing (`design §5.5`).
   - `embedding` (pgvector, the corpus embedder's dimension), with an HNSW
     index.
   - `scope` ∈ {`global`, `lab`, `personal`} plus `scope_lab` / `scope_user`.
     A concept minted from a project's state or from conversation is born in
     the narrowest scope that produced it and is **never** global (principle
     6). It is promoted to global only when it matches a concept that came
     from a public source — a paper's facets, a call's slots — and promotion
     keeps no trace of which private source met it first.
   - `openalex_field_id` (nullable; filled by CN-02) — the field ruler, used
     for distance only (`design §5.6`).
   - `status` ∈ {`active`, `merged`}, `merged_into` (self FK).
2. **`ConceptAlias`** — a normalised surface form → concept, carrying the same
   scope rule. The linker's exact-match path.
3. **`Edge`** — one subject's relation to one concept.
   - Subject: exactly one of `user`, `project`, `lab`, `author_work`,
     `content_item` (nullable FKs with a check constraint that exactly one is
     set). Real foreign keys, so deleting any subject deletes its edges.
   - `relation` ∈ {`interested_in`, `works_on`, `uses_method`,
     `works_in_setting`, `wants_to_learn`, `can_do`, `offers`, `needs`,
     `rejected`}.
   - `tier` ∈ {`declared`, `demonstrated`, `conversational`} (README tier
     table). `status` ∈ {`pending`, `active`, `faded`, `rejected`}. A
     conversational edge is `pending` until the person confirms it (AP-06).
   - `weight`, `first_seen`, `last_reinforced`, `half_life_days` (null for
     declared and demonstrated edges, which do not decay).
   - `evidence` (JSON ids only: observation ids, author-work ids, or the
     profile path the edge mirrors, such as `interests.clusters[2].topics[1]`).
   - Unique on (subject, relation, concept, tier).
4. **`ConceptMerge`** — an append-only log of merges and splits, so any merge
   can be reversed and Plan CN-08 / AP-10 can measure them.

## The linker

5. `link(surface, facet, scope)` → a concept, in `apps/knowledge/linker.py`:
   1. **Alias.** Normalised exact match in the scope chain: personal → lab →
      global.
   2. **Embedding.** Nearest concept of the same facet visible in that chain,
      accepted at cosine ≥ `KNOWLEDGE_MERGE_COSINE` (default **0.92**,
      deliberately conservative: a wrong merge makes "uses statistics" match
      everything; a missed merge only splits a count, which the next merge
      review repairs).
   3. **Mint.** Otherwise a new concept in the narrowest scope, with the
      surface form as its first alias.
   The linker is model-free. If the embedder is unavailable it links by alias
   only and **defers** the rest to the next run rather than minting
   duplicates.
6. A staff-only merge / split action (Django admin) writes `ConceptMerge` and
   re-points edges and aliases in one transaction.

## Loading what exists: declared edges

7. `project_declared(subject)` mirrors, idempotently:
   - a user's `Profile.interests`: `areas` → `interested_in` (`area`), cluster
     topics and `keywords` → `interested_in` (facet chosen by the linker's
     match, `area` when new), `skills` → `can_do` (`method`);
   - a project's stated state: `problem` → `works_on`, `method` →
     `uses_method`, `data` → `works_in_setting`, `needs.expertise` → `needs` —
     all in the project's own scope, never global;
   - a lab's declared interests, the same way as a user's.
   Values that disappeared from the source delete their mirrored edges. The
   JSON stays the source of truth; **nothing writes back from edges to a
   profile or a project** (`state.py` invariant 9 is untouched).
8. It runs on save (a post-save hook on `Profile` and the project state, queued
   so a save never waits on the embedder) and nightly as a reconciliation
   sweep (`manage.py project_declared_edges`), because a hook can be missed.
9. A one-time backfill over every existing profile, lab, and project.

## The doors

10. **`apps/knowledge/service.py`** — the only write path from outside:
    `project_declared`, `record_conversational` (AP-04/05),
    `confirm` / `reject` / `fade` (AP-06, AP-05),
    `record_demonstrated` (CN-02), `forget_conversational(user)` (ambient's
    opt-out and forget paths call it).
11. **`apps/knowledge/read.py`** — the only read path from outside, with the
    tier filter built into each function rather than passed as an argument:
    - `own_edges(user)` — everything the person may see about themselves, all
      tiers.
    - `ranking_edges(user)` — declared, demonstrated, and **active**
      conversational edges: what may shape the person's own recommendations.
    - `lab_declared_edges(lab_members)` — declared only (principle 10).
    - `discoverable_edges(users)` — declared and demonstrated only, users only,
      never projects. The only function `apps/collab` may call for candidates.
    - `project_edges(project, viewer)` — the project's edges, only to a viewer
      who can already see the project (`ProjectQuerySet.visible_to`).
12. An AST boundary test: outside `apps/knowledge`, only `service` and `read`
    may be imported, and `apps/collab` may import only `read.discoverable_*`,
    `read.own_edges`, and `read.project_edges`.

## Q1

13. `read.undeclared_project_concepts(project)`: the project's `works_on`,
    `uses_method`, `works_in_setting`, and `needs` concepts that no project
    member holds a declared edge to. Surfaced nowhere yet; it is the proof
    query and the input CN-03's coverage marking generalises.

## Steps

14. `apps/knowledge` app, models, migrations, admin.
15. Linker with alias, embedding, mint, and defer paths.
16. Declared-edge projection, save hook, nightly sweep, backfill command.
17. `service.py`, `read.py`, the boundary test.
18. Q1 and its test.
19. `docs/repo-map.md`, `docs/architecture.md` (the graph approach, replacing
    "Neo4j runs but no code uses it"), `docs/goals.md` (Next 1 progress),
    changelog.

## Acceptance

- Deleting a user, project, lab, or work leaves no edge that referenced it.
- A concept minted from project state or conversation is never `global`; a
  test tries every mint path.
- `discoverable_edges` returns no `conversational` edge and no project edge
  under any input.
- Re-running the projection on an unchanged profile writes nothing.
- Removing a keyword from a profile removes its mirrored edge on the next
  save, and the profile JSON is byte-identical before and after projection.
- With the embedder down, the linker mints no concept that an alias match did
  not produce.
- Q1 returns the expected concepts on a fixture lab.

## Open decisions

- **OD-CN01a** Merge threshold default. Recommendation: 0.92 cosine, tuned by
  the shared concept-merge experiment (CN-08, AP-10).
- **OD-CN01b** Whether declared cluster topics get facets by the linker's match
  or all start as `area`. Recommendation: the linker's match when it hits an
  existing faceted concept, `area` otherwise; a person's own words are never
  reinterpreted by a model at projection time.
- **OD-CN01c** Whether `Observation` gets a `concept` FK now or AP-04 adds it.
  Recommendation: AP-04 adds it, as an `apps/ambient` migration depending on
  this app's first migration, so this plan touches no ambient file.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.

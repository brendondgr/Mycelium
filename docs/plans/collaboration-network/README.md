# Collaboration Network — Plan Series

**Status:** discussion draft, nothing implemented.
**Correlation ID:** `20260918-collaboration-network`
**Owner:** Brendon (product direction); plans are working documents and are
deleted as their work ships, with the outcome recorded in `docs/changelog.md`.
**Source design:** [`design.md`](design.md), cited below as `design §N`.

## The problem

Two things Mycelium is meant to do need the same missing piece.

- **Collaboration suggestions from missing expertise** (`docs/goals.md`, "Not
  built"). A call needs a co-investigator in environmental health; the lab has
  none. Today `team_gap.py` can say *that* nobody on the team covers it. It
  cannot say who could.
- **Close the graph gap** (`docs/goals.md`, "Next", item 1): choose the
  approach, define node and edge types, load existing content, and prove four
  cross-entity queries.

Both reduce to one structure: **concepts** (a problem, a method, a setting, a
research area) and **typed, evidenced edges** from people, projects, and works
to those concepts. That structure is also what the
[ambient-profile](../ambient-profile/README.md) series needs to count "the same
topic" across differently worded conversations. So it is built once, as a
shared core, and both series build on it.

## The end state

Starting from a call or a project a researcher chooses to search from, Mycelium
returns two kinds of people, in separate lanes: those in the same field who
could share the work, and those from other fields who bring what the work is
missing (`design §1`, `§4`). Before any outside search it shows what the
researcher and their own lab already cover. Every person returned opted in,
chose an audience that includes the seeker, and is shown as a coarse pointer
with the one facet that matched and whether that facet is declared or
demonstrated by their papers.

## How the two series share one structure

```
                         ┌──────────────────────────────────────────────┐
                         │  CN-01  Knowledge core  (apps/knowledge)     │
                         │  Concept · Edge · linker · declared edges    │
                         └───────┬───────────────────────┬──────────────┘
                                 │                       │
        ambient-profile          ▼                       ▼        collaboration-network
   AP-04 reasoning agent ── links observations    CN-02 demonstrated expertise
            │                to concepts                 │     (facets of people's papers)
   AP-05 evolving profile ── writes conversational  CN-03 requirement slots
            │                edges                       │     + team-fit line
   AP-06 … AP-11                                  CN-04 collaboration consent
                                                         │
                                                  CN-05 matcher ─▶ CN-06 panel
                                                         │
                                                  CN-07 wider scopes + graph features
                                                  CN-08 evaluation  ◀── shares the
                                                                         concept-merge
                                                                         experiment with AP-10
```

**The shared rule that keeps them safe together — evidence tiers.** Every edge
carries a tier (enforced by `apps/knowledge/read.py`, which fixes the tiers each
function may return):

| Tier | Where it comes from | Who may read it |
|---|---|---|
| `declared` | The person's own profile or a project's stated state | The person; their consented lab scope (as today); collaboration search, only with CN-04 consent and never for project edges |
| `demonstrated` | Facets of the person's own published works (CN-02) | The person; collaboration search with CN-04 consent |
| `conversational` | Ambient observations (AP-04); inert until confirmed (AP-06) | **The person only.** Ranks their own recommendations once confirmed. Never read by collaboration search, never by anyone else |

"Conversation never makes anyone findable" is enforced in code, not policy:
the collaboration app reads the graph only through `apps/knowledge/read.py`
functions that filter the tier set, and an AST boundary test fails the build if
`apps/collab` imports anything else from `apps/knowledge` (the same pattern
`apps/ambient` already uses).

## Principles every plan obeys

1. **Opportunity-triggered, pre-filled, user-run** (`design §8.1`). The cheap
   deterministic part — slots, coverage — is precomputed and shown passively.
   A search for outside people runs only when the seeker clicks. Nothing runs
   searches for everyone every night.
2. **Lanes are never merged** (`design §9.1`). Each lane has guaranteed slots.
   Out-of-field people match on fewer facets and would lose any single ranking.
3. **Nobody is findable without opting in** (`design §7`). Default off,
   expiring, with an audience the person chooses. A person appears only when
   their audience includes the seeker **and** the seeker's scope includes them.
4. **Scopes are verified, never typed** (`design §7`). Institution and country
   come from a verified email domain matched against the affiliation directory
   (`web/app/public/data/institutions.json` carries each institution's domain),
   not from the free-text `Profile.institution`.
5. **Conversation never makes anyone findable.** Only `declared` and
   `demonstrated` edges reach another person's search. See the tier table.
6. **Project secrecy** (`design §9.2`). A project drives its seeker's search
   and never becomes part of anyone's discoverable profile. Concepts minted
   from project state or private conversation stay in that lab's or person's
   scope; nothing derived from project content enters a shared embedding.
7. **No notifications to candidates** (`design §9.3`), not even aggregate
   counts. A search leaves no trace the candidate can see.
8. **Coarse pointer disclosure** (`design §9.4`). Name, verified affiliation,
   the matching facet, the evidence tier. Not a dossier.
9. **Appearance cap** (`design §7`). A person is shown to a bounded number of
   distinct seekers per week, so the most sought-after people are not flooded.
10. **Stated, not inferred, inside the lab.** The team-internal view keeps
    `team_gap.py`'s rule: a lab-mate is named for a requirement on the strength
    of what their profile states, because that is what they control. Demonstrated
    evidence names someone only through their own collaboration consent.
11. **The model explains; it never manufactures a candidate.** The rerank may
    drop a shortlisted person and writes the one-line rationale; every person
    it names came from retrieval (the `member_fit.py` rule).
12. **Feedback from day one** (`design §8.2`). "Not relevant", "we do cover
    this", and "this isn't a requirement" are stored as append-only labels.
13. **A discussion gate before every plan**, exactly as in the ambient series.

## What already exists and is reused

| Foundation | Where | Reused for |
|---|---|---|
| Profile-blind, cached per-item précis with problem / method / setting / reusable | `apps/content/comprehension.py`, `ItemComprehension` | The facet extractor for people's works (CN-02) — same prompt discipline, same cache key rule |
| The person's own published works, kept | `apps/accounts/author_works.py`, `AuthorWork` | The paper side of every person (document-centric retrieval) |
| `required_expertise` extracted from call text, grounded | `apps/scraper/collect/extract.py` | Grows into faceted requirement slots (CN-03) |
| Requirement vs member coverage, consented scope only | `apps/content/matchers/team_gap.py`, `member_fit.scope_members` | The team-internal check (CN-03) |
| Shortlist-then-explain, may drop never add | `apps/content/member_fit.py` | The rerank rule (CN-05) |
| Project state: problem, method, data, `needs.expertise`, stated / inferred | `apps/research/state.py` | Project facets and declared project edges (CN-01, CN-03) |
| Opt-in default-off consent (`eligibility.lab_visible`) | `apps/accounts/interests.py` | The consent pattern (CN-04) |
| Verified email | `Profile.is_verified`, `accounts/permissions.py` | Verified scope (CN-04) |
| Affiliation directory with domains and country codes | `web/app/public/data/institutions.json` | Email domain → institution → country (CN-04) |
| pgvector, the corpus embedder | `apps/scraper/embedding.py`, `apps/content/embeddings.py` | Concept and facet vectors |
| One-door app boundary + AST test | `apps/ambient/{read,service}.py`, `apps/ambient/tests/test_import_boundary.py` | `apps/knowledge` and `apps/collab` boundaries |

## The plans, in order

| # | Plan | Delivers | Depends on |
|---|---|---|---|
| 01 | Knowledge core — **shipped 2026-09-18** | `apps/knowledge`: Concept, Edge, the linker, declared edges projected from profiles and projects, the tier-filtered read door, Q1. **Shared with ambient-profile.** Plan deleted; what was built and where it departed from the plan is in `docs/changelog.md` under `20260918-collaboration-network-01`, and the app is described in `docs/architecture.md` and `docs/repo-map.md` | — |
| 02 | Demonstrated expertise — **shipped 2026-09-18** | Facets of each person's own works, field-neutral method phrasing, OpenAlex field, per-work vectors, `demonstrated` edges, Q2. Validated in `EXP-2026-09-005`. Plan deleted; record in `docs/changelog.md` under `20260918-collaboration-network-02` | CN-01 |
| 03 | Requirement slots and team fit — **shipped 2026-09-18** | Slots from call text, coverage marking, the team-fit line on grant cards, slot feedback, Q3. Validated in `EXP-2026-09-006`. Plan deleted; record in `docs/changelog.md` under `20260918-collaboration-network-03` | CN-01 |
| 04 | [Collaboration consent](04-collaboration-consent.md) | Open to collaboration, audience, open-to types, expiry, verified scope, preview, appearance ledger, the Settings tab | CN-01, CN-02 |
| 05 | [The matcher](05-matcher.md) | The query object, four lanes, author aggregation, the hard gate, the shortlist rerank, feedback; institution scope only | CN-02, CN-03, CN-04 |
| 06 | [Search panel and entry points](06-search-panel.md) | The side panel, "Find collaborators" on cards, the project Collaborators tab, manual search | CN-05 |
| 07 | [Wider scopes and graph features](07-wider-scopes-and-graph.md) | Country and anywhere scopes; introduction paths, exclusion, team formation; the Neo4j decision | CN-06, CN-08 first results |
| 08 | [Evaluation](08-evaluation.md) | Slot quality, concept linking, the two lane objectives, concentration, harm checks — under the research rules | CN-03 onward, run continuously |

**Build order (decided 2026-09-18):** this series is built first, one plan at
a time — CN-01 through CN-06, with CN-08's protocols and counters registered as
each plan ships. CN-07 waits for CN-08's first results from real use. The
ambient series resumes at its Plan 04 afterwards and plugs into the finished
core; nothing in this series waits for it. CN-02 and CN-03 are independent of
each other once CN-01 has shipped.

## The four cross-entity queries (`docs/goals.md`, Next 1)

The graph is proved by four queries, each owned by the plan that builds its
inputs:

| Q | Question | Path | Proved in |
|---|---|---|---|
| Q1 | Which of a project's concepts does none of its members declare? | project → concept ← member | CN-01 |
| Q2 | Which of a person's declared concepts are backed by their own papers, and which are declared only? | person → concept ← person's works | CN-02 |
| Q3 | For this call, which requirement slots does the lab cover, by whom, and which are gaps? | call → slot concept ← lab member | CN-03 |
| Q4 | Who, in the seeker's scope, uses the method this project needs, in a different field? | project → method concept ← work → author, field ≠ | CN-05 |

## Validation in the sandbox

Unit tests prove each rule in isolation; they do not prove the pipeline works
on hundreds of people with a real model. So no plan in this series is retired
until it has also passed a **sandbox validation**: the real code, run at scale
against a synthetic world whose truth is known, scored against that truth, and
recorded as an experiment under `docs/research/experiments/`.

The harness is `web/backend/sandbox/collab/` (run from `web/backend` inside the
backend container: `uv run --project . python -m sandbox.collab all --people N`).
It builds a deterministic fake world — researchers at real university domains,
methods that cross fields under different names, near-miss methods, declared
interests never published on, methods published and never declared, lab
projects with needs no member covers — has the local model
(`llm-tunnel:9090`, `default-model`) write every paper, seeds it into its own
database (`mycelium_sandbox`) through the app's models, runs the pipeline, and
scores it. It refuses to run against any other database and forces both
knowledge hooks off, so nothing reaches the development data or the live
worker. Each plan below states the checks it adds; invariants (things that
must be zero) are a hard gate, rates are compared with a pre-registered bar.

## Keeping the two series apart

The series are built one after the other (see the build order above), but they
share `apps/knowledge` for good, and either may later be worked on in parallel.
These rules hold either way; what keeps them safe is structure, not care:

1. **Separate apps, separate migrations.** Ambient code stays in
   `apps/ambient`, collaboration code in `apps/collab`, the shared core in
   `apps/knowledge`. Each has its own `models.py` and migrations directory, so
   the two tracks never race for the same migration number.
2. **One owner for the shared core.** CN-01 defines `apps/knowledge`. After it
   ships, a change to its schema is an **amendment**: made by one track at a
   time, listed under "Amendments" below, and merged before the other track
   touches that app again.
3. **One door each way.** Writers use `apps/knowledge/service.py`; readers use
   `apps/knowledge/read.py`. No other module of `apps/knowledge` is importable
   from outside it (AST test).
4. **Separate frontend homes.** Collaboration UI lives in
   `web/app/src/components/portal/collab/` with its API layer in
   `web/app/src/lib/portal/collab/`. The shared `lib/portal/{types,client,hooks,mutations}.ts`
   files are not touched by this series.
5. **Nightly stages are separate commands.** Each series adds its own
   management commands; edits to `manual_all.py` are merged one at a time.
6. **Separate verification environments.** Each track works in its own git
   worktree with its own container mount and its own test database — two
   pytest runs against one test database produce false failures. The dev
   database is migrated only from `main`, after a merge.
7. **Separate records.** Each plan logs under its own correlation id; both
   series' changelog entries are resolved at merge.

## Amendments to the shared core

- **CN-02 (2026-09-18):** `WorkFacets` (one row per `AuthorWork`) and
  `read.backing` (Q2); `projection._apply` takes a tier so demonstrated edges
  reuse it. No change to `Concept` or `Edge`.
- **CN-03 (2026-09-18):** `read.concept_vectors(concept_ids)` — a concept's
  embedding, for comparing a call's slot with it; added to the functions the
  collaboration app may import. A vector says nothing about who holds the
  concept, and a caller only has ids from edges it was already allowed to see.

## Cross-cutting open decisions

- **OD-CN1 Contact model** (`design §13.1`). Recommendation: contact stays
  outside Mycelium for this series — the result is a pointer the seeker looks
  up. An in-app introduction request is a messaging system with spam controls,
  blocking, and rate limits, and would be its own series.
- **OD-CN2 Candidate pool** (`design §13.2`). Recommendation: opted-in
  Mycelium users only. A pool of public bibliographic authors fixes the cold
  start but changes the consent posture (people who never agreed would appear);
  it is not in this series and needs its own decision.
- **OD-CN3 Which facet to abstract first** (`design §13.3`). Recommendation:
  methods. Method transfer is the clearest cross-field win in the worked
  example and the easiest to judge.
- **OD-CN4 One switch or a set of types** (`design §13.4`). Recommendation: one
  switch, plus optional "open to" types used only as a filter and a label.
- **OD-CN5 Who may be found, and who may search.** Recommendation: any verified
  account may opt in to be found (the pool is the scarce resource); searching
  outside the lab is a paid capability, resolved by effective tier exactly as
  other caps are.
- **OD-CN6 Graph store.** Recommendation: Postgres + pgvector for CN-01 through
  CN-06; the Neo4j decision is taken in CN-07 against the `design §10` test,
  with measurements, not before.

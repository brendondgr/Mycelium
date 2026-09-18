# Plan CN-07 — Wider Scopes and Graph Features

**Status:** draft. **Depends on:** CN-06, and CN-08's first human-judgment
round and concentration numbers. **Unblocks:** nothing in this series.
**Correlation ID:** `20260918-collaboration-network-07`

## Objective

Open the search beyond one institution once the narrow launch has shown it
works, then add the three features that are genuinely multi-hop and so are the
only ones that justify graph machinery (`design §10`). Decide, with
measurements, whether that machinery is Postgres or Neo4j.

## Wider scopes

1. Raise `COLLAB_MAX_SCOPE` to `country`, then `anywhere`, each step gated on
   CN-08 showing, at the previous scope: Not-relevant rate below its target,
   no person above the appearance cap more than a set share of weeks, and no
   harm-check failure.

## Graph features

2. **Introduction paths.** "Who can introduce me?" — the shortest co-authorship
   path from the seeker to a candidate through people on Mycelium, from
   `AuthorWork` co-author ids (CN-02) and, where a path needs it, OpenAlex
   authorships. A path is shown only through people who are themselves open to
   collaboration with an audience that includes the seeker; an intermediary is
   never named without their own consent.
3. **Exclusion.** Already one hop in CN-05 (existing co-authors); here it
   extends to co-authors of co-authors when the seeker asks for "people outside
   my network".
4. **Team formation.** When a call has three or more gap slots, an
   "Assemble a team" action proposes a small set of candidates who jointly
   cover every slot while staying close in the co-authorship network (the team
   formation problem; greedy cover with a distance penalty first). Every person
   in a proposed team passes the CN-05 gate individually.

## The store decision

5. Build 2–4 first on Postgres (recursive CTEs over a `Coauthorship` edge
   table in `apps/knowledge`, an amendment). Move to Neo4j only if a
   pre-registered benchmark in the research record shows three-hop queries at
   realistic size exceed the latency budget, and only for the co-authorship
   graph; consent, tiers, and deletion stay in Postgres.

## Steps

6. Scope widening behind the gates above.
7. `Coauthorship` table and its population from CN-02's author ids.
8. Introduction paths, extended exclusion, team formation.
9. The store benchmark (research record), and the decision recorded in
   `docs/research/DECISIONS.md`.

## Acceptance

- No introduction path names a person who is not open to the seeker.
- A proposed team never includes a person the gate would have removed alone.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.

# EXP-2026-09-011 — Protocol

Written 2026-09-18, before the benchmark script ran at any size.

## Question

Plan CN-07 walks the co-authorship graph three ways — everyone within two
hops ("outside my network"), distances up to three hops (team formation), and
the shortest path to one person through only consenting intermediaries
("who can introduce me?"). They are built as recursive queries in Postgres.
At realistic size, do those queries stay inside the latency budget, or does
the graph need Neo4j (design §10, plan CN-07 step 5)?

## Hypothesis

**H1.** On a synthetic co-authorship graph of 20,000 people, Postgres answers
each of the three walks with p95 ≤ 250 ms per call, on the development
machine, warm cache. **Decision rule, fixed now:** stay on Postgres if H1
holds; consider Neo4j only if Postgres misses the budget *and* Neo4j meets it
on the same graph; record the outcome in `docs/research/DECISIONS.md` either
way.

**H2 (correctness cross-check).** On every sampled pair, the shortest path
length through allowed intermediaries is identical in Postgres, Neo4j, and a
breadth-first search in Python on the same edge list. Any disagreement
invalidates the latency comparison.

## Setup

- Graphs: `sandbox.collab.store_bench.graph(n, seed)` for n ∈ {1,000, 5,000,
  20,000}: labs of 4–12 people, each lab pair linked with probability 0.6;
  plus cross-lab links, three per person on average, attached preferentially
  (degree-proportional), so a few hubs exist as in real co-authorship.
  30% of people are "open" (allowed as intermediaries).
- Postgres: the production schema (`knowledge_coauthorship`, migrations
  applied) in a separate database `mycelium_bench`, and the production
  functions `read.network_of`, `read.coauthor_distances`,
  `read.introduction_paths` called unchanged.
- Neo4j 5 Community (the compose service): `(:BenchPerson {id, open})`,
  `[:BENCH_COAUTHORED]`, an index on `id`; `shortestPath` with a predicate on
  intermediaries, variable-length expansion for the other two walks. Deleted
  after the run.
- Queries: per size, 300 sampled (seeker, target) pairs — two thirds with a
  target 2–3 hops away, one third random — each walk timed once per seeker
  after 20 warm-up calls. Wall time in the client, including the round trip.

## Metrics

Primary: `pg_intro_p95_ms` at 20,000. Also p50/p95/max per walk, per store,
per size; load time; H2 disagreements.

## Procedure

```bash
cd web/backend
uv run --project . python -m sandbox.collab bench --sizes 1000,5000,20000 \
  --neo4j-password <compose default> --out /app/data/sandbox/exp011.json
```

## What would falsify this

H1: Postgres introduction, network or distance p95 above 250 ms at 20,000.
H2: any disagreement.

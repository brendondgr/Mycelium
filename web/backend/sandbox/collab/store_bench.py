"""EXP-2026-09-011: the co-authorship walks on Postgres and on Neo4j.

Runs against a database of its own, ``mycelium_bench`` (created and migrated
here), never the sandbox or development one, and against the compose Neo4j
under labels nothing else uses (``BenchPerson``, ``BENCH_COAUTHORED``), which
are deleted afterwards. No model is called.

The Postgres side calls the production functions in
:mod:`apps.knowledge.read` unchanged; the Neo4j side is the equivalent
Cypher. A breadth-first search in Python on the same edge list is the
reference both must agree with.
"""

from __future__ import annotations

import os
import random
import re
import statistics
import time
from collections import deque

BENCH_DB = "mycelium_bench"
LABEL = "BenchPerson"
REL = "BENCH_COAUTHORED"


# --- the graph ----------------------------------------------------------------


def graph(
    n: int, seed: int, hubs: float = 0.0
) -> tuple[list[tuple[int, int]], set[int]]:
    """Edges (as index pairs, ``a < b``) and the open people, for ``n`` people.

    Labs of 4–12 with each pair linked at 0.6, then about three cross-lab
    links per person attached in proportion to degree. ``hubs`` makes that
    share of people prolific co-authors with 100–400 extra links each — the
    heavy tail real co-authorship has and the base graph lacks.
    """
    rng = random.Random(seed * 31 + n)
    edges: set[tuple[int, int]] = set()
    lab_of = []
    start = 0
    while start < n:
        size = min(rng.randint(4, 12), n - start)
        members = list(range(start, start + size))
        for i, x in enumerate(members):
            for y in members[i + 1 :]:
                if rng.random() < 0.6:
                    edges.add((x, y))
        lab_of += [start] * size
        start += size
    # Preferential attachment: a node appears in `pool` once per edge end, plus
    # once for itself so a node with no edges can still be chosen.
    pool = list(range(n)) + [v for e in edges for v in e]
    for x in range(n):
        for _ in range(rng.choice((1, 2, 3, 3, 4, 5))):
            y = rng.choice(pool)
            if y == x or lab_of[y] == lab_of[x]:
                continue
            pair = (x, y) if x < y else (y, x)
            if pair not in edges:
                edges.add(pair)
                pool += [x, y]
    for hub in rng.sample(range(n), int(n * hubs)):
        for y in rng.sample(range(n), min(n - 1, rng.randint(100, 400))):
            if y != hub:
                edges.add((hub, y) if hub < y else (y, hub))
    open_people = {x for x in range(n) if rng.random() < 0.3}
    return sorted(edges), open_people


def adjacency(n: int, edges) -> list[list[int]]:
    adj: list[list[int]] = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    return adj


def bfs_path_length(adj, source: int, target: int, through: set[int], hops: int):
    """Shortest path length from source to target, intermediaries in `through`."""
    seen = {source}
    frontier = deque([(source, 0)])
    while frontier:
        node, depth = frontier.popleft()
        if depth == hops:
            continue
        if node != source and node not in through:
            continue
        for other in adj[node]:
            if other == target:
                return depth + 1
            if other not in seen:
                seen.add(other)
                frontier.append((other, depth + 1))
    return None


def within(adj, source: int, hops: int) -> set[int]:
    seen = {source: 0}
    frontier = deque([source])
    while frontier:
        node = frontier.popleft()
        if seen[node] == hops:
            continue
        for other in adj[node]:
            if other not in seen:
                seen[other] = seen[node] + 1
                frontier.append(other)
    seen.pop(source)
    return set(seen)


def pairs(adj, n: int, count: int, seed: int) -> list[tuple[int, int]]:
    """Two thirds with a target 2–3 hops away, one third random."""
    rng = random.Random(seed * 7 + n)
    out = []
    while len(out) < count:
        source = rng.randrange(n)
        if len(out) % 3 == 2:
            target = rng.randrange(n)
        else:
            near = sorted(within(adj, source, 3) - within(adj, source, 1))
            if not near:
                continue
            target = rng.choice(near)
        if target != source:
            out.append((source, target))
    return out


def _summary(values: list[float]) -> dict:
    ms = sorted(v * 1000 for v in values)
    return {
        "p50_ms": round(statistics.median(ms), 2),
        "p95_ms": round(ms[int(0.95 * (len(ms) - 1))], 2),
        "max_ms": round(ms[-1], 2),
    }


# --- Postgres -----------------------------------------------------------------


def setup_postgres() -> None:
    """Point Django at ``mycelium_bench``, create and migrate it, and prove it."""
    import psycopg

    url = os.environ.get("DATABASE_URL", "")
    if not re.search(r"/[^/?]+(\?.*)?$", url):
        raise RuntimeError(f"cannot read a database name from {url!r}")
    admin = re.sub(r"/[^/?]+(\?.*)?$", "/postgres", url)
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", [BENCH_DB]
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{BENCH_DB}"')
    os.environ["DATABASE_URL"] = re.sub(r"/[^/?]+(\?.*)?$", f"/{BENCH_DB}", url)
    for flag in ("KNOWLEDGE_PROJECT_ON_SAVE", "KNOWLEDGE_FACET_ON_IMPORT"):
        os.environ[flag] = "false"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.core.management import call_command
    from django.db import connection

    if connection.settings_dict["NAME"] != BENCH_DB:
        raise RuntimeError(f"connected to {connection.settings_dict['NAME']!r}")
    call_command("migrate", verbosity=0)


def load_postgres(n: int, edges) -> list[int]:
    """Replace the bench database's people and co-authorships; return pk by index."""
    from django.contrib.auth import get_user_model
    from django.db import connection

    from apps.knowledge.models import Coauthorship

    User = get_user_model()
    Coauthorship.objects.all().delete()
    User.objects.filter(username__startswith="bench-").delete()
    User.objects.bulk_create(
        [User(username=f"bench-{i}", password="!") for i in range(n)],
        batch_size=5000,
    )
    pk = dict(
        User.objects.filter(username__startswith="bench-").values_list("username", "pk")
    )
    ids = [pk[f"bench-{i}"] for i in range(n)]
    Coauthorship.objects.bulk_create(
        [
            Coauthorship(a_id=min(ids[a], ids[b]), b_id=max(ids[a], ids[b]))
            for a, b in edges
        ],
        batch_size=5000,
    )
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE knowledge_coauthorship")
    return ids


def run_postgres(ids, open_people, sample, warmup: int = 20) -> dict:
    from apps.knowledge.read import coauthor_distances, introduction_paths, network_of

    through = [ids[i] for i in sorted(open_people)]
    for s, t in sample[:warmup]:
        introduction_paths(ids[s], [ids[t]], through, max_hops=3)
        network_of(ids[s], 2)
    times = {"intro": [], "network": [], "distance": []}
    lengths, network_sizes = [], []
    for s, t in sample:
        started = time.perf_counter()
        path = introduction_paths(ids[s], [ids[t]], through, max_hops=3).get(ids[t])
        times["intro"].append(time.perf_counter() - started)
        lengths.append(len(path) - 1 if path else None)
        started = time.perf_counter()
        network_sizes.append(len(network_of(ids[s], 2)))
        times["network"].append(time.perf_counter() - started)
        started = time.perf_counter()
        coauthor_distances(ids[s], 3)
        times["distance"].append(time.perf_counter() - started)
    return {
        "times": {k: _summary(v) for k, v in times.items()},
        "lengths": lengths,
        "network_sizes": network_sizes,
    }


# --- Neo4j --------------------------------------------------------------------


def _neo4j(password: str):
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        os.environ.get("NEO4J_URI", "bolt://neo4j:7687"),
        auth=(os.environ.get("NEO4J_USERNAME", "neo4j"), password),
    )


def clear_neo4j(driver) -> None:
    with driver.session() as session:
        while True:
            deleted = session.run(
                f"MATCH (p:{LABEL}) WITH p LIMIT 10000 DETACH DELETE p "
                "RETURN count(*) AS c"
            ).single()["c"]
            if not deleted:
                break


def load_neo4j(driver, n: int, edges, open_people) -> None:
    clear_neo4j(driver)
    with driver.session() as session:
        session.run(
            f"CREATE INDEX bench_person_id IF NOT EXISTS FOR (p:{LABEL}) ON (p.id)"
        ).consume()
        session.run("CALL db.awaitIndexes()").consume()
        rows = [{"id": i, "open": i in open_people} for i in range(n)]
        for start in range(0, n, 5000):
            session.run(
                f"UNWIND $rows AS r CREATE (:{LABEL} {{id: r.id, open: r.open}})",
                rows=rows[start : start + 5000],
            ).consume()
        rels = [{"a": a, "b": b} for a, b in edges]
        for start in range(0, len(rels), 5000):
            session.run(
                f"UNWIND $rels AS r MATCH (a:{LABEL} {{id: r.a}}), "
                f"(b:{LABEL} {{id: r.b}}) CREATE (a)-[:{REL}]->(b)",
                rels=rels[start : start + 5000],
            ).consume()


INTRO = f"""
MATCH (s:{LABEL} {{id: $s}}), (t:{LABEL} {{id: $t}})
MATCH p = shortestPath((s)-[:{REL}*..3]-(t))
WHERE all(n IN nodes(p)[1..-1] WHERE n.open)
RETURN length(p) AS hops
"""
NETWORK = f"""
MATCH (s:{LABEL} {{id: $s}})-[:{REL}*1..2]-(o:{LABEL})
WHERE o <> s
RETURN count(DISTINCT o) AS c
"""
DISTANCE = f"""
MATCH p = ANY SHORTEST (s:{LABEL} {{id: $s}})-[:{REL}]-{{1,3}}(o:{LABEL})
WHERE o <> s
RETURN count(o) AS c
"""


def run_neo4j(driver, sample, *, timeout: float, deadline: float, warmup=20) -> dict:
    """Each query under a server-side ``timeout`` (seconds); a timed-out query
    is recorded at the timeout and counted, since it has missed any budget.
    Stops early at the wall-clock ``deadline`` and says so."""
    from neo4j import Query
    from neo4j.exceptions import ClientError

    times = {"intro": [], "network": [], "distance": []}
    timeouts = {"intro": 0, "network": 0, "distance": 0}
    lengths, network_sizes = [], []

    def timed(session, walk, text, **params):
        started = time.perf_counter()
        try:
            value = session.run(Query(text, timeout=timeout), **params).single()
        except ClientError as exc:
            if "imeout" not in f"{exc.code} {exc}":
                raise
            timeouts[walk] += 1
            times[walk].append(timeout)
            return "timeout"
        times[walk].append(time.perf_counter() - started)
        return value

    done = 0
    with driver.session() as session:
        for s, t in sample[:warmup]:
            timed(session, "intro", INTRO, s=s, t=t)
            timed(session, "network", NETWORK, s=s)
        for key in times:
            times[key].clear()
            timeouts[key] = 0
        for s, t in sample:
            if time.monotonic() > deadline:
                break
            row = timed(session, "intro", INTRO, s=s, t=t)
            lengths.append(
                "timeout" if row == "timeout" else (row["hops"] if row else None)
            )
            row = timed(session, "network", NETWORK, s=s)
            network_sizes.append("timeout" if row == "timeout" else row["c"])
            timed(session, "distance", DISTANCE, s=s)
            done += 1
    return {
        "times": {k: _summary(v) for k, v in times.items() if v},
        "timeouts": timeouts,
        "pairs_done": done,
        "stopped_at_deadline": done < len(sample),
        "lengths": lengths,
        "network_sizes": network_sizes,
    }


# --- the run ------------------------------------------------------------------


def main(args) -> dict:
    setup_postgres()
    driver = _neo4j(args.neo4j_password) if args.neo4j_password else None
    report: dict = {"sizes": {}, "hubs": args.hubs, "invariant_failures": []}
    # Nothing in this experiment may run past its wall-clock budget.
    deadline = time.monotonic() + args.budget_minutes * 60
    try:
        for n in [int(v) for v in args.sizes.split(",")]:
            edges, open_people = graph(n, args.seed, hubs=args.hubs)
            adj = adjacency(n, edges)
            sample = pairs(adj, n, args.pairs, args.seed)
            reference = [bfs_path_length(adj, s, t, open_people, 3) for s, t in sample]
            network_reference = [len(within(adj, s, 2)) for s, _ in sample]
            degrees = sorted(len(a) for a in adj)
            row: dict = {
                "people": n,
                "edges": len(edges),
                "open": len(open_people),
                "mean_degree": round(2 * len(edges) / n, 2),
                "max_degree": degrees[-1],
                "pairs": len(sample),
                "reachable": sum(1 for r in reference if r is not None),
            }
            started = time.monotonic()
            ids = load_postgres(n, edges)
            row["pg_load_seconds"] = round(time.monotonic() - started, 1)
            pg = run_postgres(ids, open_people, sample)
            row["pg"] = pg["times"]
            row["pg_disagreements"] = sum(
                1 for a, b in zip(pg["lengths"], reference, strict=True) if a != b
            ) + sum(
                1
                for a, b in zip(pg["network_sizes"], network_reference, strict=True)
                if a != b
            )
            if driver is not None:
                started = time.monotonic()
                load_neo4j(driver, n, edges, open_people)
                row["neo4j_load_seconds"] = round(time.monotonic() - started, 1)
                neo = run_neo4j(
                    driver, sample, timeout=args.query_timeout, deadline=deadline
                )
                row["neo4j"] = neo["times"]
                row["neo4j_timeouts"] = neo["timeouts"]
                row["neo4j_pairs_done"] = neo["pairs_done"]
                row["neo4j_stopped_at_deadline"] = neo["stopped_at_deadline"]
                # A timed-out answer is a miss, not a disagreement.
                row["neo4j_disagreements"] = sum(
                    1
                    for a, b in zip(neo["lengths"], reference, strict=False)
                    if a != "timeout" and a != b
                ) + sum(
                    1
                    for a, b in zip(
                        neo["network_sizes"], network_reference, strict=False
                    )
                    if a != "timeout" and a != b
                )
            for store in ("pg", "neo4j"):
                if row.get(f"{store}_disagreements"):
                    report["invariant_failures"].append(
                        f"{n}.{store}_disagreements = {row[f'{store}_disagreements']}"
                    )
            report["sizes"][str(n)] = row
            print(row, flush=True)
    finally:
        if driver is not None:
            clear_neo4j(driver)
            driver.close()
    return report

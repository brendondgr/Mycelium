"""Plan CN-07's sandbox validation (EXP-2026-09-010): introductions, "outside
my network", team formation, and wider scopes, against planted truth.

The world's co-authors are only lab-mates, which would leave introductions
nothing to find, so cross-lab co-authorship is planted first — two-author
works written through the real models — and the co-authorship table is rebuilt
by the real code. The planted edge list is the reference everything is
checked against: paths by brute-force search, networks by breadth-first
search, the gate by the plan.
"""

from __future__ import annotations

import random
import statistics
import time
from collections import Counter, defaultdict, deque

from . import consent_sim, match_sim
from . import world as world_mod
from .seed import openalex_id

BRIDGE_SOURCE = "sandbox-bridge"


def plant_bridges(world, users, *, seed: int, works: int = 400) -> set[tuple]:
    """Two-author works between people of different labs; returns the pairs."""
    from apps.accounts.models import AuthorWork

    from .bootstrap import assert_sandboxed

    assert_sandboxed()
    AuthorWork.objects.filter(source=BRIDGE_SOURCE).delete()
    lab_of = {m: lab.key for lab in world.labs for m in lab.members}
    keys = [p.key for p in world.people]
    rng = random.Random(seed * 41 + 3)
    pairs: set[tuple] = set()
    rows = []
    while len(pairs) < works:
        x, y = rng.sample(keys, 2)
        if lab_of.get(x) == lab_of.get(y):
            continue
        pair = tuple(sorted((x, y)))
        if pair in pairs:
            continue
        pairs.add(pair)
        for me, other in ((x, y), (y, x)):
            rows.append(
                AuthorWork(
                    user=users[me],
                    source=BRIDGE_SOURCE,
                    source_id=f"BW-{pair[0]}-{pair[1]}",
                    title="A planted bridge paper",
                    year=2024,
                    coauthor_ids=[openalex_id(other)],
                )
            )
    AuthorWork.objects.bulk_create(rows)
    return pairs


def reference_edges(world, bridges) -> set[tuple]:
    edges = {tuple(sorted((p.key, c))) for p in world.people for c in p.coauthors}
    return edges | set(bridges)


def _adjacency(edges) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def _within(adj, source, hops) -> set[str]:
    seen = {source: 0}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if seen[node] == hops:
            continue
        for other in adj[node]:
            if other not in seen:
                seen[other] = seen[node] + 1
                queue.append(other)
    seen.pop(source)
    return set(seen)


def _shortest(adj, source, target, allowed, hops):
    seen = {source}
    queue = deque([(source, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth == hops or (node != source and node not in allowed):
            continue
        for other in adj[node]:
            if other == target:
                return depth + 1
            if other not in seen:
                seen.add(other)
                queue.append((other, depth + 1))
    return None


def run(world, planned, applied, *, seed: int) -> dict:
    from django.conf import settings
    from django.utils import timezone

    from apps.collab import matcher
    from apps.collab.models import CollaborationSetting
    from apps.knowledge import coauthorship
    from apps.knowledge.models import Coauthorship
    from apps.research.models import Project

    users = applied["users"]
    key_of = {u.pk: k for k, u in users.items()}
    people = {p.key: p for p in world.people}
    out = Counter()
    timings = defaultdict(list)

    bridges = plant_bridges(world, users, seed=seed)
    started = time.monotonic()
    rebuilt = coauthorship.rebuild()
    out_rebuild = {**rebuilt.as_dict(), "seconds": round(time.monotonic() - started, 2)}
    reference = reference_edges(world, bridges)
    stored = {
        tuple(sorted((key_of[a], key_of[b])))
        for a, b in Coauthorship.objects.values_list("a_id", "b_id")
    }
    out["violations_table"] = len(stored ^ reference)
    adj = _adjacency(reference)

    labs_of = defaultdict(set)
    for lab in world.labs:
        for member in lab.members:
            labs_of[member].add(lab.key)
    now = timezone.now()
    rows = {
        s.user.username: s for s in CollaborationSetting.objects.select_related("user")
    }
    open_now = {k for k, s in rows.items() if s.is_open(now)}
    audiences = {k: s.audience for k, s in rows.items()}
    place = {k: consent_sim._reference_place(p, planned) for k, p in people.items()}

    def gate(seeker, cand, scope):
        if not match_sim._gate_ok(
            world, planned, people, labs_of, seeker, cand, scope, open_now, audiences
        ):
            return False
        return cand not in adj[seeker]  # planted co-authors, bridges included

    def may_introduce(seeker, person):
        """Open now, and their audience includes the seeker (one-way)."""
        if person not in open_now or place[person] is None or place[seeker] is None:
            return False
        return consent_sim._reference_visible(
            person, place[person], audiences[person], place[seeker], "anywhere"
        )

    def down(system, user):
        raise ConnectionError("rerank off for EXP-2026-09-010")

    settings.COLLAB_APPEARANCE_CAP = 10**6
    settings.COLLAB_SEARCHES_PER_DAY = 10**6
    settings.COLLAB_MAX_SCOPE = "anywhere"
    methods_by_field = defaultdict(set)
    for p in world.people:
        methods_by_field[p.field].update(p.methods)

    path_lengths = []
    team_sizes, gaps_total, gaps_covered = [], 0, 0
    cover_rows = cover_correct = 0
    rng = random.Random(seed * 43 + 1)
    for spec in world.projects:
        lab = next(lab for lab in world.labs if lab.key == spec.lab)
        seeker_key = lab.members[0]
        if seeker_key in planned["unverified"]:
            continue
        seeker = users[seeker_key]
        project = Project.objects.get(
            name=spec.name, scope_lab__slug=f"sandbox-{spec.lab}"
        )

        for scope in ("institution", "country", "anywhere"):
            query = matcher.query_for_project(seeker, project, scope=scope)
            started = time.monotonic()
            result = matcher.search(seeker, query, complete=down)
            timings[f"search_{scope}"].append(time.monotonic() - started)
            out[f"searches_{scope}"] += 1
            shown = {r["username"] for rows_ in result.lanes.values() for r in rows_}
            out[f"shown_{scope}"] += len(shown)
            out[f"violations_scope_{scope}"] += sum(
                1 for c in shown if not gate(seeker_key, c, scope)
            )
            if scope != "institution":
                continue
            allowed = {k for k in people if may_introduce(seeker_key, k)} - {seeker_key}
            for cand in sorted(shown):
                started = time.monotonic()
                via = matcher.introduce(seeker, result.search_id, cand)
                timings["introduce"].append(time.monotonic() - started)
                out["introductions_asked"] += 1
                expected = _shortest(adj, seeker_key, cand, allowed - {cand}, 3)
                if via["path"] is None:
                    if expected is not None:
                        out["violations_path_missing"] += 1
                    continue
                out["introductions_found"] += 1
                chain = [seeker_key, *[p["username"] for p in via["path"]], cand]
                path_lengths.append(len(chain) - 1)
                if any(b not in adj[a] for a, b in zip(chain, chain[1:], strict=False)):
                    out["violations_path_not_coauthors"] += 1
                if any(k not in allowed for k in chain[1:-1]):
                    out["violations_path_intermediary"] += 1
                if expected is None or len(chain) - 1 != expected:
                    out["violations_path_not_shortest"] += 1

        # Outside my network: nobody within two co-authorships.
        query = matcher.query_for_project(seeker, project, outside_network=True)
        result = matcher.search(seeker, query, complete=down)
        near = _within(adj, seeker_key, 2)
        shown = {r["username"] for rows_ in result.lanes.values() for r in rows_}
        out["outside_network_shown"] += len(shown)
        out["violations_outside_network"] += len(shown & near)
        out["violations_outside_network_gate"] += sum(
            1 for c in shown if not gate(seeker_key, c, "institution")
        )

        # A team for methods from other fields.
        home = people[seeker_key].field
        pool = sorted(
            set().union(*(ms for f, ms in methods_by_field.items() if f != home))
        )
        need = rng.sample(pool, k=rng.choice((3, 4)))
        slots = [
            {"facet": "method", "text": world_mod.method(m).names[0]} for m in need
        ]
        query = matcher.Query(
            "manual",
            matcher._with_vectors(slots),
            need_fields=matcher._fields_of([seeker]),
        )
        started = time.monotonic()
        try:
            team = matcher.assemble_team(seeker, query)
        except matcher.SearchRefused as exc:
            out[f"team_refused_{exc.code}"] += 1
            continue
        timings["team"].append(time.monotonic() - started)
        out["teams"] += 1
        team_sizes.append(len(team.team))
        gaps_total += len(slots)
        gaps_covered += len(slots) - len(team.uncovered)
        by_text = {world_mod.method(m).names[0]: m for m in need}
        for member in team.team:
            if not gate(seeker_key, member["username"], "institution"):
                out["violations_team_gate"] += 1
            for c in member["covers"]:
                cover_rows += 1
                cover_correct += int(
                    by_text[c["slot"]] in people[member["username"]].methods
                )
        for text in team.uncovered:
            holders = [
                k
                for k in people
                if by_text[text] in people[k].methods
                and gate(seeker_key, k, "institution")
            ]
            if holders:
                out["team_uncovered_but_held"] += 1

    def summary(values):
        if not values:
            return None
        ordered = sorted(values)
        return {
            "p50": round(statistics.median(ordered), 3),
            "p95": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
        }

    return {
        "rebuild": out_rebuild,
        "bridges": len(bridges),
        "reference_edges": len(reference),
        **dict(out),
        "introduction_share": round(
            out["introductions_found"] / out["introductions_asked"], 4
        )
        if out["introductions_asked"]
        else None,
        "mean_path_length": round(statistics.mean(path_lengths), 3)
        if path_lengths
        else None,
        "mean_team_size": round(statistics.mean(team_sizes), 3) if team_sizes else None,
        "team_gap_coverage": round(gaps_covered / gaps_total, 4)
        if gaps_total
        else None,
        "team_cover_rows": cover_rows,
        "team_cover_precision": round(cover_correct / cover_rows, 4)
        if cover_rows
        else None,
        "latency_seconds": {k: summary(v) for k, v in timings.items()},
    }


def main(world, args) -> dict:
    from django.conf import settings

    settings.COLLAB_SEARCH_ENABLED = True
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    planned = consent_sim.plan(world, args.seed)
    applied = consent_sim.apply(world, planned)
    started = time.monotonic()
    report = {"graph": run(world, planned, applied, seed=args.seed)}
    report["graph_seconds"] = round(time.monotonic() - started, 1)
    report["invariant_failures"] = [
        f"{k} = {v}"
        for k, v in report["graph"].items()
        if k.startswith("violations") and v
    ]
    precision = report["graph"]["team_cover_precision"]
    if precision is not None and precision < 0.80:
        report["bar_failures"] = [f"team_cover_precision = {precision}"]
    return report

"""Plan CN-05's sandbox validation: the matcher against planted lane truth.

Runs on a world already seeded and read (``all``) with a consent matrix
planted (``consent_sim``). Every lab lead searches from their lab's project;
each returned person is scored against the plan — which methods they really
declared or published, in which field — and re-checked against every gate
condition. Then a load run measures latency and the cap's effect.
"""

from __future__ import annotations

import random
import statistics
import time
from collections import Counter, defaultdict

from . import consent_sim
from . import world as world_mod


def plant_conversation(world, users, *, seed: int, share: float = 0.05) -> dict:
    """Give some people a confirmed conversational method they never declared
    or published — which must never make them findable for it."""
    from apps.knowledge import service
    from apps.knowledge.models import Relation

    rng = random.Random(seed * 17 + 9)
    planted = {}
    for person in rng.sample(world.people, k=int(len(world.people) * share)):
        held = set(person.methods)
        choices = [m for m in world_mod.METHODS if m.key not in held]
        method = rng.choice(choices)
        view = service.record_conversational(
            users[person.key], surface=method.names[0], relation=Relation.USES_METHOD
        )
        if view is not None:
            service.confirm(users[person.key], view.concept_id, Relation.USES_METHOD)
            planted[person.key] = method.key
    return planted


def _methods_named(text: str) -> set[str]:
    lowered = f" {str(text).lower()} "
    return {m.key for m in world_mod.METHODS if any(s in lowered for s in m.signature)}


def _gate_ok(
    world, planned, people, labs_of, seeker_key, cand_key, scope, open_now, audiences
):
    """The gate, re-derived from the plan — not from the code under test."""
    if cand_key == seeker_key or cand_key not in open_now:
        return False
    seeker_ref = consent_sim._reference_place(people[seeker_key], planned)
    cand_ref = consent_sim._reference_place(people[cand_key], planned)
    if not consent_sim._reference_visible(
        cand_key, cand_ref, audiences[cand_key], seeker_ref, scope
    ):
        return False
    if labs_of[seeker_key] & labs_of[cand_key]:
        return False
    # In the world, co-authors are exactly lab-mates.
    return cand_key not in people[seeker_key].coauthors


def quality(
    world, planned, applied, conversation, *, scope: str = "institution", complete=None
) -> dict:
    from django.conf import settings
    from django.utils import timezone

    from apps.collab import matcher
    from apps.collab.models import CollaborationSetting
    from apps.research.models import Project

    users = applied["users"]
    people = {p.key: p for p in world.people}
    labs_of = defaultdict(set)
    for lab in world.labs:
        for member in lab.members:
            labs_of[member].add(lab.key)
    now = timezone.now()
    settings_rows = {
        s.user.username: s for s in CollaborationSetting.objects.select_related("user")
    }
    open_now = {k for k, s in settings_rows.items() if s.is_open(now)}
    audiences = {k: s.audience for k, s in settings_rows.items()}
    field_of = {p.key: p.field for p in world.people}

    out = Counter()
    rows_checked = 0
    latencies = []
    per_slot = []
    for spec in world.projects:
        lab = next(lab for lab in world.labs if lab.key == spec.lab)
        seeker_key = lab.members[0]
        if seeker_key in planned["unverified"]:
            continue
        seeker = users[seeker_key]
        project = Project.objects.get(
            name=spec.name, scope_lab__slug=f"sandbox-{spec.lab}"
        )
        query = matcher.query_for_project(seeker, project, scope=scope)
        started = time.monotonic()
        try:
            result = matcher.search(seeker, query, complete=complete)
        except matcher.SearchRefused as exc:
            out[f"refused:{exc}"] += 1
            continue
        latencies.append(time.monotonic() - started)
        out["searches"] += 1
        eligible = {
            k
            for k in people
            if _gate_ok(
                world,
                planned,
                people,
                labs_of,
                seeker_key,
                k,
                scope,
                open_now,
                audiences,
            )
        }
        for lane, rows in result.lanes.items():
            for row in rows:
                rows_checked += 1
                cand = row["username"]
                if cand not in eligible:
                    out["violations_gate"] += 1
                if row["tier"] not in ("declared", "demonstrated"):
                    out["violations_tier"] += 1
                named = _methods_named(row["slot"])
                if (
                    conversation.get(cand) in named
                    and conversation[cand] not in people[cand].methods
                ):
                    out["violations_conversation"] += 1
                if lane == "method_bridge":
                    correct = (
                        bool(named & set(people[cand].methods))
                        and field_of[cand] != field_of[seeker_key]
                    )
                    out["method_bridge_returned"] += 1
                    out["method_bridge_correct"] += int(correct)
                elif lane == "in_field":
                    papers = {p.problem.casefold() for p in people[cand].papers}
                    correct = (
                        row["slot"].casefold() in papers
                        and field_of[cand] == field_of[seeker_key]
                    )
                    out["in_field_returned"] += 1
                    out["in_field_correct"] += int(correct)
                elif lane == "problem_bridge":
                    out["problem_bridge_returned"] += 1
                else:
                    out["resource_returned"] += 1
        # Recall for every method slot of this project: did the lane find at
        # least one person the plan says it should have?
        for slot in query.slots:
            if slot["facet"] != "method":
                continue
            named = _methods_named(slot["text"])
            expected = {
                k
                for k in eligible
                if named & set(people[k].methods)
                and field_of[k] != field_of[seeker_key]
            }
            if not expected:
                continue
            got = {
                r["username"]
                for r in result.lanes.get("method_bridge", [])
                if r["slot"] == slot["text"]
            }
            per_slot.append(
                {
                    "hit": bool(got & expected),
                    "recall_at_k": len(got & expected)
                    / min(settings.COLLAB_RESULTS_PER_LANE, len(expected)),
                }
            )
    rate = lambda n, d: round(n / d, 4) if d else None  # noqa: E731
    return {
        **{k: v for k, v in out.items()},
        "rows_checked": rows_checked,
        "method_bridge_precision": rate(
            out["method_bridge_correct"], out["method_bridge_returned"]
        ),
        "in_field_precision": rate(out["in_field_correct"], out["in_field_returned"]),
        "method_slots_with_truth": len(per_slot),
        "method_bridge_hit_rate": rate(sum(s["hit"] for s in per_slot), len(per_slot)),
        "method_bridge_recall_at_k": round(
            statistics.mean(s["recall_at_k"] for s in per_slot), 4
        )
        if per_slot
        else None,
        "latency_p50": round(statistics.median(latencies), 3) if latencies else None,
        "latency_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 3)
        if latencies
        else None,
    }


def load(world, planned, applied, *, searches: int, cap: int | None, seed: int) -> dict:
    """Many seekers, many searches, model off: latency and concentration."""
    from django.conf import settings

    from apps.collab import matcher
    from apps.collab.models import Appearance, SearchLog

    def down(system, user):
        raise ConnectionError("load test: model off")

    users = applied["users"]
    seekers = [p.key for p in world.people if p.key not in planned["unverified"]]
    rng = random.Random(seed * 19 + 2)
    Appearance.objects.all().delete()
    SearchLog.objects.all().delete()
    previous_cap, previous_limit = (
        settings.COLLAB_APPEARANCE_CAP,
        settings.COLLAB_SEARCHES_PER_DAY,
    )
    settings.COLLAB_APPEARANCE_CAP = cap if cap is not None else 10**6
    settings.COLLAB_SEARCHES_PER_DAY = 10**6
    slots_pool = [
        {"facet": "method", "text": m.names[0]} for m in world_mod.METHODS
    ] + [
        {"facet": "problem", "text": p}
        for probs in world_mod.PROBLEMS.values()
        for p in probs
    ]
    latencies = []
    shown = Counter()
    try:
        for index in range(searches):
            seeker = users[rng.choice(seekers)]
            chosen = rng.sample(slots_pool, k=2)
            query = matcher.Query(
                "manual",
                matcher._with_vectors([dict(s, text=f"{s['text']}") for s in chosen]),
                need_fields=matcher._fields_of([seeker]),
            )
            # Distinct wording per search so the day's cache does not answer it.
            query.slots[0]["text"] += f" ({index})"
            started = time.monotonic()
            result = matcher.search(seeker, query, complete=down)
            latencies.append(time.monotonic() - started)
            for rows in result.lanes.values():
                for row in rows:
                    shown[row["username"]] += 1
    finally:
        settings.COLLAB_APPEARANCE_CAP = previous_cap
        settings.COLLAB_SEARCHES_PER_DAY = previous_limit
    distinct = Counter(Appearance.objects.values_list("candidate__username", flat=True))
    open_people = list(distinct) or [0]
    return {
        "searches": searches,
        "cap": cap,
        "latency_p50": round(statistics.median(latencies), 3),
        "latency_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 3),
        "results": sum(shown.values()),
        "max_distinct_seekers": max(distinct.values(), default=0),
        "gini_distinct_seekers": consent_sim._gini(list(distinct.values())),
        "people_shown": len(open_people),
        "violations_cap": (
            sum(1 for n in distinct.values() if n > cap) if cap is not None else 0
        ),
    }

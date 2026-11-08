"""Plan CN-06's sandbox validation: every entry point through the real API.

Fake seekers drive ``/api/collab/search/`` exactly as the panel does — the
availability check, a dry run for the pre-filled chips, then Run with the
chips sent back — from a funding call, from their lab's project, and from
their own words. Every response is checked for shape and for what it must
never carry: a person the gate would refuse, a field beyond the coarse
pointer, a count of who was filtered out. Then the refusal paths (flag off,
unverified, free plan while plans are enforced, the daily limit, a scope
beyond the launch limit, someone else's project) and the saved list.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from collections import Counter, defaultdict

from . import consent_sim, match_sim

#: What a found person may carry — a pointer, never a profile.
HIT_KEYS = {
    "username",
    "name",
    "institution",
    "lane",
    "slot",
    "facet",
    "matched",
    "tier",
    "reason",
}
RESPONSE_KEYS = {"slots", "lanes", "groups", "explained", "search_id"}
GAP_LANES = {"method_bridge", "problem_bridge", "resource"}
#: Anything that would say how many people were held back.
LEAKY_WORDS = ("filtered", "hidden", "excluded", "considered", "withheld")


def _client(user):
    from rest_framework.test import APIClient

    client = APIClient(HTTP_HOST="localhost")
    client.force_authenticate(user)
    return client


def _saved(client) -> set[str]:
    return {p["username"] for p in client.get("/api/collab/saved/").json()["people"]}


def seed_calls(world, *, seed: int, n: int, read: int, workers: int) -> list:
    """Seed ``n`` planted calls and read the requirements of ``read`` of them
    with the real slot reader (the model), so the call entry has real slots."""
    from pathlib import Path

    from apps.collab import slots

    from . import calls as calls_mod

    planted = calls_mod.build(seed=seed, n=n)
    texts = calls_mod.generate(
        planted,
        Path(f"/app/data/sandbox/calls-{seed}-{n}.json"),
        workers=workers,
    )
    items = calls_mod.seed(planted, texts)
    chosen = random.Random(seed).sample(list(items.values()), k=min(read, n))
    slots.read_calls(chosen)
    return [item for item in chosen if hasattr(item, "requirement_slots")]


def _check_response(body, eligible, out, lanes_asked):
    """Shape and privacy of one search response. Adds to ``out``."""
    if set(body) != RESPONSE_KEYS:
        out["violations_response_keys"] += 1
    text = json.dumps(body).lower()
    if any(f'"{word}' in text for word in LEAKY_WORDS):
        out["violations_leaky_count"] += 1
    for lane, rows in body["lanes"].items():
        if lane not in lanes_asked:
            out["violations_lane_not_asked"] += 1
        for row in rows:
            out["hits"] += 1
            out[f"hits_{lane}"] += 1
            if set(row) != HIT_KEYS:
                out["violations_hit_keys"] += 1
            if row["lane"] != lane:
                out["violations_lane_label"] += 1
            if row["tier"] not in ("declared", "demonstrated"):
                out["violations_tier"] += 1
            if row["username"] not in eligible:
                out["violations_gate"] += 1
            if not row["reason"]:
                out["hits_without_reason"] += 1
    gap = body["groups"]["fills_a_gap"]
    shares = body["groups"]["shares_expertise"]
    if any(r["lane"] not in GAP_LANES for r in gap):
        out["violations_group"] += 1
    if any(r["lane"] != "in_field" for r in shares):
        out["violations_group"] += 1
    seen_in_groups = [(r["lane"], r["username"], r["slot"]) for r in gap + shares]
    in_lanes = [
        (r["lane"], r["username"], r["slot"])
        for rows in body["lanes"].values()
        for r in rows
    ]
    if sorted(seen_in_groups) != sorted(in_lanes):
        out["violations_group_partition"] += 1
    if not gap and not shares:
        out["empty_results"] += 1


def run(
    world,
    planned,
    applied,
    calls,
    *,
    seed: int,
    seekers: int,
    rerank_seekers: int = 10,
    manual_every: int = 6,
    deadline: float | None = None,
    workers: int = 1,
) -> dict:
    from django.conf import settings

    from apps.collab.matcher import project_visible
    from apps.collab.models import CollaborationSetting, SearchLog
    from apps.research.models import Project

    users = applied["users"]
    people = {p.key: p for p in world.people}
    labs_of = defaultdict(set)
    for lab in world.labs:
        for member in lab.members:
            labs_of[member].add(lab.key)
    projects_by_lab = defaultdict(list)
    for spec in world.projects:
        projects_by_lab[spec.lab].append(spec)

    def eligible_for(seeker_key, scope):
        from django.utils import timezone

        rows = {
            s.user.username: s
            for s in CollaborationSetting.objects.select_related("user")
        }
        now = timezone.now()
        open_now = {k for k, s in rows.items() if s.is_open(now)}
        audiences = {k: s.audience for k, s in rows.items()}
        return {
            k
            for k in people
            if match_sim._gate_ok(
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

    rng = random.Random(seed * 23 + 5)
    verified = [
        p.key
        for p in world.people
        if p.key not in planned["unverified"] and labs_of[p.key]
    ]
    chosen = rng.sample(verified, k=min(seekers, len(verified)))
    out = Counter()
    latency = defaultdict(list)
    all_lanes = {"in_field", "method_bridge", "problem_bridge", "resource"}
    settings.COLLAB_SEARCH_ENABLED = True
    settings.COLLAB_SEARCHES_PER_DAY = 10**6
    settings.COLLAB_APPEARANCE_CAP = 10**6
    manual_needs = [
        f"We need someone who can do {m.names[0]} for our data."
        for m in match_sim.world_mod.METHODS
    ]
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connection

    from apps.collab import matcher

    real_complete = matcher._default_complete
    local = threading.local()

    def routed(system, user):
        # The model reranks the first few seekers' searches; the rest run with
        # it off, which the API must handle identically in shape.
        if getattr(local, "model_on", False):
            return real_complete(system, user)
        raise ConnectionError("rerank off for this seeker (EXP-2026-09-009)")

    def one(index, key):
        """Everything one seeker does. Returns its own counts, latencies and
        the people to check in the saved list afterwards (serially, since that
        check switches a person's setting off for a moment)."""
        mine, times, saves = Counter(), defaultdict(list), []
        if deadline is not None and time.monotonic() > deadline:
            return mine, times, saves, False
        local.model_on = index < rerank_seekers
        rng = random.Random(seed * 1000 + index)
        try:
            user = users[key]
            client = _client(user)

            def timed(kind, payload):
                started = time.monotonic()
                response = client.post("/api/collab/search/", payload, format="json")
                times[kind].append(time.monotonic() - started)
                return response

            eligible = eligible_for(key, "institution")
            availability = client.get("/api/collab/search/").json()
            if availability != {
                "available": True,
                "code": "",
                "reason": "",
                "max_scope": settings.COLLAB_MAX_SCOPE,
            }:
                mine["violations_availability"] += 1

            entries = []
            if calls:
                call = calls[index % len(calls)]
                entries.append(("call", {"entry": "call", "content_id": str(call.pk)}))
            lab_key = sorted(labs_of[key])[0]
            if projects_by_lab.get(lab_key):
                spec = projects_by_lab[lab_key][0]
                project = Project.objects.get(
                    name=spec.name, scope_lab__slug=f"sandbox-{spec.lab}"
                )
                entries.append(
                    ("project", {"entry": "project", "project_id": str(project.pk)})
                )
            # The seeker's own words go through the model.
            if index % manual_every == 0:
                entries.append(
                    ("manual", {"entry": "manual", "text": rng.choice(manual_needs)})
                )

            for kind, entry in entries:
                own_logs = SearchLog.objects.filter(seeker=user).count()
                prefill = timed(f"{kind}_dry_run", {**entry, "dry_run": True})
                if prefill.status_code != 200:
                    mine[f"errors_{kind}_dry_run_{prefill.status_code}"] += 1
                    continue
                if SearchLog.objects.filter(seeker=user).count() != own_logs:
                    mine["violations_dry_run_logged"] += 1
                if set(prefill.json()) != {"slots"}:
                    mine["violations_dry_run_keys"] += 1
                chips = prefill.json()["slots"]
                if any("vector" in chip for chip in chips):
                    mine["violations_vector_leaked"] += 1
                if not [c for c in chips if c["facet"] != "role"]:
                    mine[f"{kind}_no_matchable_slots"] += 1
                    continue
                # The panel sends the chips back (sometimes one removed, as a
                # person tidying the need would) and a subset of lanes.
                if len(chips) > 1 and rng.random() < 0.3:
                    chips = chips[:-1]
                lanes = sorted(all_lanes) if rng.random() < 0.7 else ["method_bridge"]
                response = timed(kind, {**entry, "slots": chips, "lanes": lanes})
                if response.status_code != 200:
                    mine[f"errors_{kind}_{response.status_code}"] += 1
                    continue
                mine[f"searches_{kind}"] += 1
                body = response.json()
                if [c["text"] for c in body["slots"]] != [c["text"] for c in chips]:
                    mine["violations_slots_not_honoured"] += 1
                _check_response(body, eligible, mine, set(lanes))
                hits = (
                    body["groups"]["fills_a_gap"] + body["groups"]["shares_expertise"]
                )
                if hits and index % 3 == 0:
                    saves.append((key, body["search_id"], hits[0]))

            # Someone else's project, from a lab the seeker is not in.
            other = next((s for s in world.projects if s.lab not in labs_of[key]), None)
            if other is not None:
                project = Project.objects.get(
                    name=other.name, scope_lab__slug=f"sandbox-{other.lab}"
                )
                response = client.post(
                    "/api/collab/search/",
                    {
                        "entry": "project",
                        "project_id": str(project.pk),
                        "dry_run": True,
                    },
                    format="json",
                )
                # The real visibility rule decides what should happen.
                visible = project_visible(project, user)
                if (response.status_code == 200) != visible:
                    mine["violations_foreign_project"] += 1
                seen = "visible" if visible else "hidden"
                mine[f"foreign_project_{seen}_{response.status_code}"] += 1
            # A scope beyond the launch limit is refused, not narrowed silently.
            if settings.COLLAB_MAX_SCOPE == "institution":
                response = client.post(
                    "/api/collab/search/",
                    {
                        "entry": "manual",
                        "slots": [{"facet": "method", "text": "kriging"}],
                        "scope": "anywhere",
                    },
                    format="json",
                )
                if response.status_code != 403:
                    mine["violations_scope_beyond_limit"] += 1
            return mine, times, saves, True
        finally:
            connection.close()

    matcher._default_complete = routed
    saves_all = []
    done = 0
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for mine, times, saves, ran in pool.map(one, range(len(chosen)), chosen):
                out.update(mine)
                for kind, values in times.items():
                    latency[kind].extend(values)
                saves_all += saves
                done += int(ran)
    finally:
        matcher._default_complete = real_complete

    # The saved list, serially: saving someone lists them, and their switching
    # the setting off takes them off every list at once.
    for key, search_id, hit in saves_all:
        client = _client(users[key])
        saved = client.post(
            f"/api/collab/searches/{search_id}/feedback/",
            {"candidate": hit["username"], "lane": hit["lane"], "kind": "save"},
            format="json",
        )
        out[f"feedback_{saved.status_code}"] += 1
        if hit["username"] not in _saved(client):
            out["violations_saved_missing"] += 1
        setting = CollaborationSetting.objects.get(user__username=hit["username"])
        setting.open = False
        setting.save(update_fields=["open"])
        if hit["username"] in _saved(client):
            out["violations_saved_after_off"] += 1
        setting.open = True
        setting.save(update_fields=["open"])
        out["saved_checked"] += 1

    out["seekers_done"] = done
    out["stopped_at_deadline"] = int(done < len(chosen))
    out.update(_refusals(planned, users, chosen))
    summary = {
        f"latency_{kind}_p50": round(statistics.median(values), 3)
        for kind, values in latency.items()
    } | {
        f"latency_{kind}_p95": round(sorted(values)[int(0.95 * (len(values) - 1))], 3)
        for kind, values in latency.items()
    }
    return {
        "seekers": len(chosen),
        "calls_with_slots": len(calls),
        **dict(out),
        **summary,
    }


def _refusals(planned, users, chosen) -> Counter:
    """Every path on which the panel must not offer a search."""
    from django.conf import settings

    from apps.collab.models import SearchLog

    out = Counter()
    body = {"entry": "manual", "slots": [{"facet": "method", "text": "kriging"}]}
    seeker = users[chosen[0]]
    client = _client(seeker)

    settings.COLLAB_SEARCH_ENABLED = False
    if client.get("/api/collab/search/").json().get("code") != "not_enabled":
        out["violations_flag_off_availability"] += 1
    if client.post("/api/collab/search/", body, format="json").status_code != 404:
        out["violations_flag_off_search"] += 1
    settings.COLLAB_SEARCH_ENABLED = True

    for key in sorted(planned["unverified"])[:10]:
        c = _client(users[key])
        if c.get("/api/collab/search/").json().get("code") != "unverified":
            out["violations_unverified_availability"] += 1
        if c.post("/api/collab/search/", body, format="json").status_code != 403:
            out["violations_unverified_search"] += 1
        out["unverified_checked"] += 1

    previous = settings.BILLING_ENFORCE_ENTITLEMENTS
    settings.BILLING_ENFORCE_ENTITLEMENTS = True
    try:
        # Sandbox people hold no subscription, so all are on the free plan.
        if client.get("/api/collab/search/").json().get("code") != "paid_plan":
            out["violations_free_plan_availability"] += 1
        if client.post("/api/collab/search/", body, format="json").status_code != 403:
            out["violations_free_plan_search"] += 1
    finally:
        settings.BILLING_ENFORCE_ENTITLEMENTS = previous

    limit = settings.COLLAB_SEARCHES_PER_DAY
    settings.COLLAB_SEARCHES_PER_DAY = SearchLog.objects.filter(seeker=seeker).count()
    try:
        if client.get("/api/collab/search/").json().get("code") != "daily_limit":
            out["violations_daily_limit_availability"] += 1
        if client.post("/api/collab/search/", body, format="json").status_code != 403:
            out["violations_daily_limit_search"] += 1
    finally:
        settings.COLLAB_SEARCHES_PER_DAY = limit
    return out


def main(world, args) -> dict:
    """Plan and apply consent as the matcher test does, then drive the API."""
    from django.conf import settings

    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    # The whole run, calls included, stays inside the budget.
    deadline = time.monotonic() + args.budget_minutes * 60
    planned = consent_sim.plan(world, args.seed)
    applied = consent_sim.apply(world, planned)
    started = time.monotonic()
    calls = seed_calls(
        world, seed=args.seed, n=args.calls, read=args.read_calls, workers=args.workers
    )
    report = {"calls_seconds": round(time.monotonic() - started, 1)}
    started = time.monotonic()
    report["api"] = run(
        world,
        planned,
        applied,
        calls,
        seed=args.seed,
        seekers=args.seekers,
        rerank_seekers=args.rerank_seekers,
        deadline=deadline,
        workers=args.search_workers,
    )
    report["api_seconds"] = round(time.monotonic() - started, 1)
    report["invariant_failures"] = [
        f"{k} = {v}"
        for k, v in report["api"].items()
        if k.startswith("violations") and v
    ]
    return report


def prepare_browser(world, *, seed: int, password: str) -> dict:
    """One sandbox seeker a browser can sign in as, with read calls in their
    feed carrying team fit — run after ``panel``, on the same world."""
    from tools.recommendation.models import RelevanceScore
    from tools.recommendation.targets import target_for_lab, target_for_user

    from apps.accounts.models import Lab
    from apps.collab import team_fit
    from apps.collab.models import RequirementSlots
    from apps.research.models import Project

    from .bootstrap import assert_sandboxed

    assert_sandboxed()
    planned = consent_sim.plan(world, seed)
    lab = world.labs[0]
    key = next(k for k in lab.members if k not in planned["unverified"])
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.get(username=key)
    user.set_password(password)
    user.save(update_fields=["password"])
    profile = user.profile
    if not (profile.interests or {}).get("areas"):
        profile.interests = {**(profile.interests or {}), "areas": ["sandbox"]}
        profile.save(update_fields=["interests"])
    calls = [
        row.content
        for row in RequirementSlots.objects.filter(status="ok").select_related(
            "content"
        )
    ]
    lab_row = Lab.objects.get(slug=f"sandbox-{lab.key}")
    RelevanceScore.objects.filter(target_user=user).delete()
    RelevanceScore.objects.filter(target_lab=lab_row).delete()
    # What a scoring run writes for a shown match: the feed lists only rows
    # marked suggested (grants without a date are live).
    signals = {"suggested": True, "match_percent": 80}
    RelevanceScore.objects.bulk_create(
        [
            RelevanceScore(
                content=c, score=0.9, target_user=user, signals=dict(signals)
            )
            for c in calls
        ]
        + [
            RelevanceScore(
                content=c, score=0.9, target_lab=lab_row, signals=dict(signals)
            )
            for c in calls
        ]
    )
    team_fit.annotate_target(target_for_user(user))
    team_fit.annotate_target(target_for_lab(lab_row))
    project = Project.objects.filter(scope_lab=lab_row).first()
    return {
        "username": key,
        "lab": lab_row.slug,
        "project_id": str(project.pk) if project else None,
        "calls": len(calls),
    }

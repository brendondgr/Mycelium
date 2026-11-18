"""EXP-2026-11-023: collaborator suggestions for a real department's faculty.

    docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
        -e SANDBOX_DB=mycelium_sandbox_fsusc \
        -v $PWD/docs/research:/app/docs/research -v <private dir>:/private backend \
        uv run --no-sync --project web/backend python \
        docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/run023.py \
        check | prepare | search | export

Database: ``mycelium_sandbox_fsusc``, a pg_dump/pg_restore copy of the live
database taken 2026-11-18 (see PROTOCOL.md). Selected the way
``sandbox.collab`` selects its database; ``assert_sandboxed`` stops the run on
any other. Never the live database. In-process only: local-memory caches, Celery
eager, the knowledge hooks off.

Private inputs and outputs live under ``/private`` (outside the repository):
``people.json`` holds the anonymous id -> person mapping, the stand-in emails and
the OpenAlex author ids; ``raw/`` and ``ratings_input.json`` hold names. This
file and everything it writes under the experiment folder use anonymous ids and
counts only.

What the harness changes, in-process only (product code is untouched):

* the stand-in email domain resolves to the real institution's directory entry
  (``affiliation.resolve_email``), so the department's stand-in accounts are
  placed at the institution their real addresses would prove;
* ``COLLAB_SEARCH_ENABLED`` on, billing enforcement off, the weekly appearance
  cap and the daily search limit raised (each seeker is searched as if first);
* ``WRITEUP_LLM_CONCURRENCY`` = 4 (the work-facet reader's pool), searches run
  four seekers at a time: at most four model requests in flight.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / "web" / "backend"), str(REPO)]
os.environ.setdefault("SANDBOX_DB", "mycelium_sandbox_fsusc")

EXP_DB = "mycelium_sandbox_fsusc"
PRIVATE = Path(os.environ.get("PRIVATE_DIR", "/private"))
STANDIN_DOMAIN = "fsu-sc.mycelium.invalid"
REAL_DOMAIN = "fsu.edu"
IN_FLIGHT = 4
TL = threading.local()
LOCK = threading.Lock()


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# -- setup ---------------------------------------------------------------------


def setup_django() -> dict:
    from sandbox.collab import bootstrap

    assert bootstrap.SANDBOX_DB == EXP_DB, bootstrap.SANDBOX_DB
    bootstrap.prepare()
    import django
    from django.conf import settings

    django.setup()
    bootstrap.assert_sandboxed()
    from django.db import connection

    assert connection.settings_dict["NAME"] == EXP_DB
    for name in list(settings.CACHES):
        settings.CACHES[name] = {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"exp023-{name}",
        }
    from django.core.cache import caches

    for name in list(settings.CACHES):
        try:
            del caches[name]
        except Exception:  # noqa: BLE001
            pass
    settings.AGENT_LEARNING = False
    settings.AMBIENT_ENABLED = False
    settings.COLLAB_SEARCH_ENABLED = True
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    settings.COLLAB_APPEARANCE_CAP = 10**6
    settings.COLLAB_SEARCHES_PER_DAY = 10**6
    settings.WRITEUP_LLM_CONCURRENCY = IN_FLIGHT
    # Never send a contact address to OpenAlex from this run.
    settings.OPENALEX_MAILTO = ""
    from config.celery import app as celery_app

    celery_app.conf.task_always_eager = True

    from apps.accounts import institution
    from apps.collab import affiliation

    original = affiliation.resolve_email

    def resolve_email(email: str):
        if (email or "").lower().endswith("@" + STANDIN_DOMAIN):
            return institution.resolve_domain(REAL_DOMAIN)
        return original(email)

    affiliation.resolve_email = resolve_email
    institution.resolve_email = resolve_email
    return {
        "database": connection.settings_dict["NAME"],
        "collab_search_enabled": settings.COLLAB_SEARCH_ENABLED,
        "billing_enforce": settings.BILLING_ENFORCE_ENTITLEMENTS,
        "collab_max_scope": settings.COLLAB_MAX_SCOPE,
        "appearance_cap": settings.COLLAB_APPEARANCE_CAP,
        "searches_per_day": settings.COLLAB_SEARCHES_PER_DAY,
        "writeup_llm_concurrency": settings.WRITEUP_LLM_CONCURRENCY,
        "llm_model": settings.LLM_MODEL if hasattr(settings, "LLM_MODEL") else None,
        "lane_match_cosine": settings.COLLAB_LANE_MATCH_COSINE,
        "concept_match_cosine": settings.COLLAB_CONCEPT_MATCH_COSINE,
        "shortlist_per_lane": settings.COLLAB_SHORTLIST_PER_LANE,
        "results_per_lane": settings.COLLAB_RESULTS_PER_LANE,
        "standin_resolves_to": getattr(resolve_email("x@" + STANDIN_DOMAIN), "name", None),
    }


def people() -> dict:
    return json.loads((PRIVATE / "people.json").read_text())


def user_for(person: dict):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    email = person.get("copy_only_standin_email") or person.get("email")
    if email:
        return User.objects.filter(email=email).first()
    if person.get("username"):
        return User.objects.filter(username=person["username"]).first()
    return None


def id_map() -> dict[int, tuple[str, str]]:
    """user pk -> (anonymous id, role) for everyone in the private roster."""
    out = {}
    roster = people()
    for person in roster["faculty"] + roster["students"]:
        user = user_for(person)
        if user is not None:
            out[user.pk] = (person["id"], person["role"])
    return out


def write_public(name: str, payload) -> None:
    path = HERE / "logs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def write_private(name: str, payload) -> None:
    path = PRIVATE / "raw" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, default=str) + "\n")


# -- check ---------------------------------------------------------------------


def cmd_check(_args) -> None:
    info = setup_django()
    from apps.accounts.models import AuthorWork
    from apps.collab.models import CollaborationSetting, SearchLog

    roster = people()
    rows = []
    for person in roster["faculty"] + roster["students"]:
        user = user_for(person)
        rows.append(
            {
                "id": person["id"],
                "found": user is not None,
                "works": AuthorWork.objects.filter(user=user).count() if user else 0,
                "open": bool(
                    user
                    and CollaborationSetting.objects.filter(user=user, open=True).exists()
                ),
            }
        )
    info["roster"] = rows
    info["search_logs"] = SearchLog.objects.count()
    print(json.dumps(info, indent=1, default=str))


# -- prepare -------------------------------------------------------------------


def make_copy_only_standin(person: dict) -> dict:
    """A stand-in for the one faculty member whose account predates the stand-ins.

    The existing account is not modified (it is read for its declared interests
    only); the stand-in exists in this copy alone, in the same lab.
    """
    from django.contrib.auth import get_user_model

    from apps.accounts.models import LabMembership
    from apps.knowledge.tasks import project_subject

    User = get_user_model()
    existing = User.objects.get(username=person["existing_account_username"])
    user = User.objects.filter(email=person["copy_only_standin_email"]).first()
    created = user is None
    if created:
        user = User(
            username=person["copy_only_standin_username"],
            email=person["copy_only_standin_email"],
        )
        user.set_unusable_password()
        user.save()
    profile = user.profile
    profile.academic_title = existing.profile.academic_title
    profile.interests = existing.profile.interests
    profile.is_verified = True
    profile.institution_granted = "Florida State University"
    profile.save()
    for membership in LabMembership.objects.filter(user=existing):
        LabMembership.objects.get_or_create(
            user=user, lab=membership.lab, defaults={"role": membership.role}
        )
    projected = project_subject("user", str(user.pk))
    return {"created": created, "projection": projected}


def import_person(person: dict) -> dict:
    """The product's import path, as an operator provisioning from an author id."""
    from apps.accounts.author_works import store_author_works
    from apps.accounts.intake import import_author
    from apps.accounts.models import Profile
    from apps.knowledge import papers

    user = user_for(person)
    started = time.time()
    draft = import_author(person["openalex_id"], "openalex")
    external = draft.external_ids
    Profile.objects.filter(user=user).update(
        openalex_id=external.get("openalex", "") or person["openalex_id"],
    )
    if external.get("orcid") and not user.profile.orcid:
        Profile.objects.filter(user=user).update(orcid=external["orcid"])
    user.refresh_from_db()
    stored = store_author_works(user, draft, source="openalex", verified=True)
    imported = time.time()
    refreshed = papers.refresh_person(user).as_dict()
    return {
        "id": person["id"],
        "works_in_draft": len(draft.evidence),
        "stored": stored,
        "import_seconds": round(imported - started, 1),
        "facet_seconds": round(time.time() - imported, 1),
        **refreshed,
    }


def cmd_prepare(args) -> None:
    info = setup_django()
    log(f"setup {info}")
    from apps.collab import consent
    from apps.knowledge import coauthorship

    roster = people()
    faculty, students = roster["faculty"], roster["students"]
    out = {"setup": info, "standin": None, "opt_in": [], "imports": []}

    for person in faculty:
        if person.get("copy_only_standin_email"):
            out["standin"] = {"id": person["id"], **make_copy_only_standin(person)}
            log(f"copy-only stand-in for {person['id']}: {out['standin']}")

    # Opt in every stand-in (faculty as seekers and candidates, students as
    # candidates). The one existing open account is left as it is.
    for person in faculty + students:
        if not (person.get("email") or person.get("copy_only_standin_email")):
            continue
        user = user_for(person)
        consent.update(user, open=True, audience="institution", open_to=[])
        out["opt_in"].append(person["id"])
    log(f"opted in {len(out['opt_in'])}")

    todo = [p for p in faculty + students if p.get("openalex_id")]
    if args.only:
        todo = [p for p in todo if p["id"] in args.only.split(",")]
    for person in todo:
        log(f"import {person['id']} ...")
        try:
            row = import_person(person)
        except Exception as exc:  # noqa: BLE001 - record, do not stop the rest
            row = {"id": person["id"], "error": f"{type(exc).__name__}: {exc}"}
        log(f"  {row}")
        out["imports"].append(row)
        write_public("prepare.json", out)
    out["coauthorship"] = coauthorship.rebuild().as_dict()
    write_public("prepare.json", out)
    log("prepare done")


# -- search --------------------------------------------------------------------


def query_text(person: dict) -> str:
    return (
        "Who in the department should I collaborate with on "
        + person["areas"].rstrip(".")
        + "?"
    )


def install_capture() -> None:
    from apps.collab import matcher

    original = matcher._rerank

    def capture(query, lane, shortlist, complete):
        started = time.time()
        kept, reasons, explained = original(query, lane, shortlist, complete)
        TL.lanes.append(
            {
                "lane": lane,
                "shortlist": [dataclasses.asdict(h) for h in shortlist],
                "kept": [h.user_id for h in kept],
                "reasons": {str(k): v for k, v in reasons.items()},
                "explained": explained,
                "seconds": round(time.time() - started, 1),
            }
        )
        return kept, reasons, explained

    matcher._rerank = capture


def gate_diagnostic(seeker) -> dict:
    """Who is open, and why each open person is or is not a candidate."""
    from django.utils import timezone

    from apps.collab import matcher
    from apps.collab.models import CollaborationSetting
    from apps.knowledge.read import discoverable_works

    now = timezone.now()
    open_ids = set(
        CollaborationSetting.objects.filter(open=True, expires_at__gt=now)
        .exclude(user=seeker)
        .values_list("user_id", flat=True)
    )
    eligible = {u.pk for u in matcher.eligible_candidates(seeker, "institution", now)}
    labs = matcher._labs_by_user(list(open_ids) + [seeker.pk])
    coauthors = matcher._coauthors_by_user(list(open_ids) + [seeker.pk])
    from django.contrib.auth import get_user_model

    users = {u.pk: u for u in get_user_model().objects.filter(pk__in=open_ids)}
    seeker_oa = seeker.profile.openalex_id or ""
    reasons = {}
    for pk in open_ids - eligible:
        user = users[pk]
        their = user.profile.openalex_id or ""
        if labs[seeker.pk] & labs[pk]:
            reasons[pk] = "lab_mate"
        elif (their and their in coauthors[seeker.pk]) or (
            seeker_oa and seeker_oa in coauthors[pk]
        ):
            reasons[pk] = "coauthor"
        else:
            reasons[pk] = "other"
    with_works = {w.user_id for w in discoverable_works([users[p] for p in eligible])}
    return {
        "open": sorted(open_ids),
        "eligible": sorted(eligible),
        "excluded": {str(k): v for k, v in sorted(reasons.items())},
        "eligible_with_read_works": sorted(with_works),
    }


def manual_slots(person: dict) -> list[dict]:
    """Deviation 1: each research area as a problem slot and a method slot."""
    out = []
    for area in person["areas"].split(";"):
        area = area.strip().rstrip(".")
        if area:
            out.append({"facet": "problem", "text": area, "required": False})
            out.append({"facet": "method", "text": area, "required": False})
    return out


def run_seeker(person: dict, arm: str = "product") -> dict:
    from django.db import connections

    from apps.collab import matcher
    from apps.collab.models import Appearance, SearchLog

    TL.lanes = []
    seeker = user_for(person)
    text = query_text(person)
    out = {"id": person["id"], "arm": arm, "user_pk": seeker.pk, "query": text, "attempts": []}
    try:
        out["gate"] = gate_diagnostic(seeker)
        started = time.time()
        if arm == "manual":
            query = matcher.Query(
                "manual",
                matcher._with_vectors(manual_slots(person)),
                need_fields=matcher._fields_of([seeker]),
            )
        else:
            query = matcher.query_for_text(seeker, text)
        out["slot_seconds"] = round(time.time() - started, 1)
        out["slots"] = [
            {k: s.get(k) for k in ("facet", "text", "required")} for s in query.slots
        ]
        covered, gaps = matcher._split(seeker, query)
        out["covered"] = [s["text"] for s in covered]
        out["gaps"] = [s["text"] for s in gaps]
        for attempt in (1, 2):
            TL.lanes = []
            started = time.time()
            result = matcher.search(seeker, query)
            out["attempts"].append(
                {
                    "attempt": attempt,
                    "seconds": round(time.time() - started, 1),
                    "explained": result.explained,
                    "candidates_considered": result.candidates_considered,
                    "lanes": result.lanes,
                    "rerank": TL.lanes,
                    "search_id": result.search_id,
                }
            )
            if result.explained or not query.slots:
                break
            # Pre-registered: one retry when the rerank was unavailable. The
            # day's cache would replay the unexplained answer, so this seeker's
            # log for this query and their appearances are cleared first (this
            # copy only).
            SearchLog.objects.filter(seeker=seeker, query_hash=query.key()).delete()
            Appearance.objects.filter(seeker=seeker).delete()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        connections.close_all()
    return out


def cmd_search(args) -> None:
    info = setup_django()
    log(f"setup {info}")
    install_capture()
    roster = people()
    seekers = roster["faculty"]
    if args.only:
        seekers = [p for p in seekers if p["id"] in args.only.split(",")]
    results = []
    with ThreadPoolExecutor(max_workers=IN_FLIGHT) as pool:
        for row in pool.map(lambda p: run_seeker(p, args.arm), seekers):
            log(
                f"{row['id']}: slots={len(row.get('slots', []))} "
                f"shown={sum(len(v) for v in (row['attempts'][-1]['lanes'] if row.get('attempts') else {}).values())} "
                f"err={row.get('error')}"
            )
            results.append(row)
    write_private(f"search_{args.arm}.json", {"setup": info, "results": results})
    log("search done")


# -- export --------------------------------------------------------------------


def _evidence(user_pk: int, hit: dict) -> str:
    """The papers behind a hit, as titles (private output only)."""
    from apps.accounts.models import AuthorWork
    from apps.knowledge.models import Edge, WorkFacets

    if hit["tier"] == "declared":
        return f"declared on profile: {hit['matched']}"
    rows = WorkFacets.objects.filter(author_work__user_id=user_pk).select_related(
        "author_work"
    )
    for row in rows:
        if hit["matched"] and hit["matched"] in (
            row.problem,
            row.method,
            row.method_neutral,
            row.reusable,
        ):
            w = row.author_work
            return f"paper: {w.title} ({w.year or 'n.d.'})"
    edge = (
        Edge.objects.filter(user_id=user_pk, tier="demonstrated", surface=hit["matched"])
        .order_by("-weight")
        .first()
    )
    if edge is not None:
        ids = [e.split(":", 1)[1] for e in edge.evidence if e.startswith("work:")][:3]
        titles = [
            f"{w.title} ({w.year or 'n.d.'})"
            for w in AuthorWork.objects.filter(pk__in=ids)
        ]
        return f"concept '{hit['matched']}' from: " + "; ".join(titles)
    return hit["matched"]


ARMS = ("product", "manual")


def _arm_rows(raw_row: dict, anon, User) -> tuple[list[dict], dict]:
    """Every candidate one arm surfaced for one seeker, with the public summary."""
    last = raw_row["attempts"][-1] if raw_row.get("attempts") else None
    rows = []
    if last:
        for cap in last["rerank"]:
            lane = cap["lane"]
            shown_names = [r["username"] for r in last["lanes"].get(lane, [])]
            by_name = {
                u.username: u.pk for u in User.objects.filter(username__in=shown_names)
            }
            shown = [by_name[u] for u in shown_names]
            order = [h["user_id"] for h in cap["shortlist"]]
            for position, hit in enumerate(cap["shortlist"], start=1):
                pk = hit["user_id"]
                rows.append(
                    {
                        "pk": pk,
                        "lane": lane,
                        "hit": hit,
                        "shown_with_model": pk in shown,
                        "model_rank_in_lane": shown.index(pk) + 1 if pk in shown else None,
                        "no_model_rank_in_lane": position if position <= 3 else None,
                        "shortlist_position": position,
                        "dropped_by_model": pk not in cap["kept"],
                        "reason": cap["reasons"].get(str(pk), ""),
                    }
                )
            assert all(p in order for p in shown)
    gate = raw_row.get("gate", {})
    exc = Counter(gate.get("excluded", {}).values())
    summary = {
        "error": raw_row.get("error"),
        "n_slots": len(raw_row.get("slots", [])),
        "slot_facets": dict(Counter(s["facet"] for s in raw_row.get("slots", []))),
        "n_covered": len(raw_row.get("covered", [])),
        "n_gaps": len(raw_row.get("gaps", [])),
        "attempts": len(raw_row.get("attempts", [])),
        "explained": last["explained"] if last else None,
        "candidates_considered": last["candidates_considered"] if last else 0,
        "open_others": len(gate.get("open", [])),
        "excluded_lab_mate": exc.get("lab_mate", 0),
        "excluded_coauthor": exc.get("coauthor", 0),
        "excluded_other": exc.get("other", 0),
        "eligible_with_read_works": len(gate.get("eligible_with_read_works", [])),
        "shortlist_per_lane": {
            c["lane"]: len(c["shortlist"]) for c in (last["rerank"] if last else [])
        },
        "kept_per_lane": {
            c["lane"]: len(c["kept"]) for c in (last["rerank"] if last else [])
        },
        "shown_per_lane": {k: len(v) for k, v in (last["lanes"] if last else {}).items()},
        "candidates": [
            {
                "candidate_id": anon(r["pk"])[0],
                "candidate_role": anon(r["pk"])[1],
                "lane": r["lane"],
                "tier": r["hit"]["tier"],
                "matched_facet": r["hit"]["facet"],
                "score": round(r["hit"]["score"], 4),
                "shortlist_position": r["shortlist_position"],
                "shown_with_model": r["shown_with_model"],
                "dropped_by_model": r["dropped_by_model"],
                "has_reason": bool(r["reason"]),
            }
            for r in rows
        ],
    }
    return rows, summary


def cmd_export(_args) -> None:
    setup_django()
    from django.contrib.auth import get_user_model

    from apps.accounts.models import AuthorWork
    from apps.knowledge.models import WorkFacets

    User = get_user_model()
    raws = {
        arm: {
            r["id"]: r
            for r in json.loads((PRIVATE / "raw" / f"search_{arm}.json").read_text())[
                "results"
            ]
        }
        for arm in ARMS
    }
    roster = people()
    ids = id_map()

    def anon(pk: int) -> tuple[str, str]:
        return ids.get(pk, (f"X{pk}", "unknown"))

    roster_names = {p["id"]: p["name"] for p in roster["faculty"] + roster["students"]}

    def name_of(pk: int) -> str:
        if anon(pk)[0] in roster_names:
            return roster_names[anon(pk)[0]]
        user = User.objects.get(pk=pk)
        return f"{user.first_name} {user.last_name}".strip() or user.username

    ratings, public_rows = [], []
    for person in roster["faculty"]:
        merged: dict[tuple[int, str], dict] = {}
        extras: dict[int, dict] = {}
        pub = {"seeker_id": person["id"]}
        for arm in ARMS:
            rows, summary = _arm_rows(raws[arm][person["id"]], anon, User)
            pub[arm] = summary
            for r in rows:
                rated = r["shown_with_model"] or r["no_model_rank_in_lane"] is not None
                key = (r["pk"], r["lane"])
                if not rated:
                    if r["pk"] not in extras and not any(k[0] == r["pk"] for k in merged):
                        extras[r["pk"]] = {
                            "candidate_id": anon(r["pk"])[0],
                            "candidate_name": name_of(r["pk"]),
                            "candidate_role": anon(r["pk"])[1],
                            "arm": arm,
                            "lane": r["lane"],
                            "shortlist_position": r["shortlist_position"],
                            "slot": r["hit"]["slot"],
                            "tier": r["hit"]["tier"],
                            "evidence": _evidence(r["pk"], r["hit"]),
                            "reason": r["reason"],
                            "kept_by_model": not r["dropped_by_model"],
                        }
                    continue
                entry = merged.get(key)
                if entry is None:
                    entry = merged[key] = {
                        "candidate_id": anon(r["pk"])[0],
                        "candidate_name": name_of(r["pk"]),
                        "candidate_role": anon(r["pk"])[1],
                        "lane": r["lane"],
                        "evidence": _evidence(r["pk"], r["hit"]),
                        "reason": r["reason"],
                        "slot": r["hit"]["slot"],
                        "tier": r["hit"]["tier"],
                        "arms": {},
                    }
                    extras.pop(r["pk"], None)
                entry["arms"][arm] = {
                    "shown_with_model": r["shown_with_model"],
                    "model_rank_in_lane": r["model_rank_in_lane"],
                    "no_model_rank_in_lane": r["no_model_rank_in_lane"],
                    "dropped_by_model": r["dropped_by_model"],
                    "slot": r["hit"]["slot"],
                    "reason": r["reason"],
                }
                if not entry["reason"] and r["reason"]:
                    entry["reason"] = r["reason"]

        def sort_key(e):
            shown = any(a["shown_with_model"] for a in e["arms"].values())
            best = min(
                (a["model_rank_in_lane"] or a["no_model_rank_in_lane"] or 9)
                for a in e["arms"].values()
            )
            return (not shown, e["lane"] != "in_field", best, e["candidate_id"])

        suggestions = sorted(merged.values(), key=sort_key)
        for rank, e in enumerate(suggestions, start=1):
            e["rank"] = rank
            e["shown_with_model_in_any_arm"] = any(
                a["shown_with_model"] for a in e["arms"].values()
            )
        ratings.append(
            {
                "seeker_id": person["id"],
                "seeker_name": person["name"],
                "query": query_text(person),
                "slots_product_arm": raws["product"][person["id"]].get("slots", []),
                "suggestions": [
                    {k: e[k] for k in (
                        "rank", "candidate_id", "candidate_name", "candidate_role",
                        "lane", "evidence", "reason", "slot", "tier",
                        "shown_with_model_in_any_arm", "arms",
                    )}
                    for e in suggestions
                ],
                "optional_deeper_shortlist": sorted(
                    extras.values(), key=lambda x: (x["shortlist_position"], x["candidate_id"])
                ),
            }
        )
        pub["rating_rows"] = len(suggestions)
        pub["rating_rows_shown_with_model"] = sum(
            1 for e in suggestions if e["shown_with_model_in_any_arm"]
        )
        pub["optional_extras"] = len(extras)
        public_rows.append(pub)
    (PRIVATE / "ratings_input.json").write_text(
        json.dumps(ratings, indent=1, ensure_ascii=False) + "\n"
    )
    write_public("search_anon.json", public_rows)

    works = []
    for person in roster["faculty"] + roster["students"]:
        user = user_for(person)
        if user is None:
            continue
        qs = AuthorWork.objects.filter(user=user)
        facets = WorkFacets.objects.filter(author_work__user=user)
        works.append(
            {
                "id": person["id"],
                "role": person["role"],
                "imported": bool(person.get("openalex_id")),
                "works": qs.count(),
                "with_abstract": sum(1 for w in qs if (w.abstract or "").strip()),
                "facets_read": facets.count(),
                "facets_thin": facets.filter(thin=True).count(),
                "distinct_fields": len({w.openalex_field_id for w in qs if w.openalex_field_id}),
            }
        )
    write_public("works_anon.json", works)
    log(f"export done: {len(ratings)} seekers")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["check", "prepare", "search", "export"])
    parser.add_argument("--only", default="")
    parser.add_argument("--arm", choices=["product", "manual"], default="product")
    args = parser.parse_args()
    {"check": cmd_check, "prepare": cmd_prepare, "search": cmd_search, "export": cmd_export}[
        args.cmd
    ](args)


if __name__ == "__main__":
    main()

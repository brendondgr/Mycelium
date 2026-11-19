"""EXP-2026-11-024: the 14 typed questions of EXP-2026-11-023, before and after
the slot-reader fix (commit 2cc179d9), on one fresh copy of the live database.

    PRIVATE_DIR=<dir> FROZEN=<git archive of a commit> code/drive.sh \
        check | identity | prepare | search --arm before|after

Reuses EXP-2026-11-023's harness (``run023.py``: roster, sandbox setup, the
product import path, the gate diagnostic) with three things redirected so that
experiment's record and private files are never touched:

* the database is ``mycelium_sandbox_fsusc24`` (a new copy, not 023's);
* public logs go to this folder's ``logs/``;
* private outputs go to ``<private>/exp024/``.

Public files hold anonymous ids and counts only, never a slot's text (the
slots are read out of each person's research areas).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DB = "mycelium_sandbox_fsusc24"
os.environ["SANDBOX_DB"] = DB
sys.path.insert(
    0, str(HERE.parent / "EXP-2026-11-023-collab-live-fsu-sc" / "code")
)
import run023  # noqa: E402

run023.HERE = HERE
run023.EXP_DB = DB
PRIVATE_OUT = run023.PRIVATE / "exp024"
ARMS = ("before", "after")
TL = threading.local()


def write_private(name: str, payload) -> None:
    PRIVATE_OUT.mkdir(parents=True, exist_ok=True)
    (PRIVATE_OUT / name).write_text(json.dumps(payload, indent=1, default=str) + "\n")


run023.write_private = write_private


def commit_under_test() -> str:
    """Set by drive.sh from the frozen tree's COMMIT file."""
    return os.environ.get("COMMIT_UNDER_TEST", "unknown")


# -- identity -------------------------------------------------------------------


def cmd_identity(_args) -> None:
    """What the relay lists and what the model says it is, recorded per run."""
    info = run023.setup_django()
    import urllib.request

    from django.conf import settings

    from apps.core.llm import LLMMessage, build_llm_client

    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "setup": info}
    base = getattr(settings, "LLM_BASE_URL", "") or os.environ.get("LLM_BASE_URL", "")
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/models", timeout=20) as r:
            out["relay_models"] = json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001
        out["relay_models"] = f"unavailable: {exc}"
    try:
        reply = build_llm_client(component="requirement_slots").complete(
            [
                LLMMessage(
                    "user",
                    "In one sentence: which model are you, and which organisation "
                    "trained you?",
                )
            ]
        )
        out["self_report"] = reply.content
    except Exception as exc:  # noqa: BLE001
        out["self_report"] = f"unavailable: {exc}"
    print(json.dumps(out, indent=1, default=str))
    run023.write_public(f"identity_{int(time.time())}.json", out)


# -- search ---------------------------------------------------------------------


def install_reader_capture() -> None:
    """Record how many slots the reader itself returned, so a slot the fallback
    supplied is told apart from one the model read."""
    from apps.collab import slots as reader

    name = "extract_need" if hasattr(reader, "extract_need") else "extract"
    original = getattr(reader, name)

    def capture(*args, **kwargs):
        outcome = original(*args, **kwargs)
        TL.reader = {
            "function": name,
            "reachable": outcome is not None,
            "slots": len(outcome.slots) if outcome else 0,
            "thin": bool(outcome and outcome.thin),
            "attempts": outcome.attempts if outcome else 0,
            "refused": list(outcome.refused) if outcome else [],
        }
        return outcome

    setattr(reader, name, capture)


def run_seeker(person: dict, arm: str) -> dict:
    from django.db import connections

    from apps.collab import matcher
    from apps.collab.models import Appearance, SearchLog

    TL.lanes, TL.reader = [], None
    seeker = run023.user_for(person)
    text = run023.query_text(person)
    out = {"id": person["id"], "arm": arm, "user_pk": seeker.pk, "query": text}
    out["attempts"] = []
    try:
        started = time.time()
        try:
            query = matcher.query_for_text(seeker, text)
        except matcher.SearchRefused as exc:
            out["refused"] = {"code": exc.code, "detail": str(exc)}
            return out
        finally:
            out["slot_seconds"] = round(time.time() - started, 1)
            out["reader"] = TL.reader
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
            # As in EXP-2026-11-023: one retry when the rerank was unavailable,
            # with this seeker's cached answer and appearances cleared (copy only).
            SearchLog.objects.filter(seeker=seeker, query_hash=query.key()).delete()
            Appearance.objects.filter(seeker=seeker).delete()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        connections.close_all()
    return out


def anonymise(row: dict, ids: dict) -> dict:
    """Counts and anonymous ids only: no slot text, no names."""

    def anon(pk: int) -> tuple[str, str]:
        return ids.get(pk, (f"X{pk}", "unknown"))

    pub = {
        "seeker_id": row["id"],
        "arm": row["arm"],
        "refused": (row.get("refused") or {}).get("code"),
        "error": row.get("error"),
        "reader": row.get("reader"),
        "n_slots": len(row.get("slots", [])),
        "slot_facets": [s["facet"] for s in row.get("slots", [])],
        "n_gaps": len(row.get("gaps", [])),
        "n_covered": len(row.get("covered", [])),
    }
    reader = row.get("reader") or {}
    if pub["n_slots"] == 0:
        pub["slot_source"] = "none"
    elif reader.get("slots"):
        pub["slot_source"] = "reader"
    else:
        pub["slot_source"] = "fallback"
    last = row["attempts"][-1] if row.get("attempts") else None
    pub["attempts"] = len(row.get("attempts", []))
    pub["explained"] = last["explained"] if last else None
    pub["candidates_considered"] = last["candidates_considered"] if last else 0
    candidates = []
    if last:
        shown = {
            (lane, r["username"]) for lane, rows in last["lanes"].items() for r in rows
        }
        from django.contrib.auth import get_user_model

        names = {
            u.pk: u.get_username()
            for u in get_user_model().objects.filter(
                pk__in=[h["user_id"] for lane in last["rerank"] for h in lane["shortlist"]]
            )
        }
        for lane in last["rerank"]:
            for pos, hit in enumerate(lane["shortlist"], start=1):
                cid, role = anon(hit["user_id"])
                candidates.append(
                    {
                        "candidate_id": cid,
                        "candidate_role": role,
                        "lane": lane["lane"],
                        "shortlist_position": pos,
                        "tier": hit["tier"],
                        "shown_with_model": (lane["lane"], names.get(hit["user_id"]))
                        in shown,
                        "dropped_by_model": hit["user_id"] not in lane["kept"],
                    }
                )
    pub["candidates"] = candidates
    pub["shown"] = sum(c["shown_with_model"] for c in candidates)
    return pub


def cmd_search(args) -> None:
    info = run023.setup_django()
    info["commit_under_test"] = commit_under_test()
    run023.log(f"setup {info}")
    run023.install_capture()
    run023.TL = TL  # the rerank capture writes to our thread-local
    install_reader_capture()
    from apps.collab.models import Appearance, SearchLog

    roster = run023.people()
    seekers = roster["faculty"]
    if args.only:
        seekers = [p for p in seekers if p["id"] in args.only.split(",")]
    users = [run023.user_for(p) for p in seekers]
    # Each arm starts with no search history for these seekers (copy only), so
    # the day's cache never answers one arm with the other's result.
    cleared = {
        "search_logs": SearchLog.objects.filter(seeker__in=users).delete()[0],
        "appearances": Appearance.objects.filter(seeker__in=users).delete()[0],
    }
    run023.log(f"cleared {cleared}")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = []
    with ThreadPoolExecutor(max_workers=run023.IN_FLIGHT) as pool:
        for row in pool.map(lambda p: run_seeker(p, args.arm), seekers):
            last = row["attempts"][-1] if row.get("attempts") else {"lanes": {}}
            run023.log(
                f"{row['id']}: slots={len(row.get('slots', []))} "
                f"reader={(row.get('reader') or {}).get('slots')} "
                f"refused={(row.get('refused') or {}).get('code')} "
                f"shown={sum(len(v) for v in last['lanes'].values())} "
                f"err={row.get('error')}"
            )
            results.append(row)
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_private(
        f"search_{args.arm}.json",
        {"setup": info, "cleared": cleared, "started": started, "finished": finished,
         "results": results},
    )
    ids = run023.id_map()
    run023.write_public(
        f"search_{args.arm}_anon.json",
        {
            "arm": args.arm,
            "commit_under_test": info["commit_under_test"],
            "started": started,
            "finished": finished,
            "cleared": cleared,
            "results": [anonymise(r, ids) for r in results],
        },
    )
    run023.log("search done")


def cmd_works(_args) -> None:
    """Per person: works imported and read (anonymous ids)."""
    run023.setup_django()
    from apps.accounts.models import AuthorWork
    from apps.knowledge.models import WorkFacets

    roster = run023.people()
    rows = []
    for person in roster["faculty"] + roster["students"]:
        user = run023.user_for(person)
        works = AuthorWork.objects.filter(user=user) if user else AuthorWork.objects.none()
        facets = WorkFacets.objects.filter(author_work__in=works)
        rows.append(
            {
                "id": person["id"],
                "role": person["role"],
                "works": works.count(),
                "facets_read": facets.count(),
                "facets_thin": facets.filter(thin=True).count(),
            }
        )
    run023.write_public("works_anon.json", rows)
    print(json.dumps(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["check", "identity", "prepare", "search", "works"])
    parser.add_argument("--only", default="")
    parser.add_argument("--arm", choices=ARMS, default="after")
    args = parser.parse_args()
    {
        "check": run023.cmd_check,
        "identity": cmd_identity,
        "prepare": run023.cmd_prepare,
        "search": cmd_search,
        "works": cmd_works,
    }[args.cmd](args)


if __name__ == "__main__":
    main()

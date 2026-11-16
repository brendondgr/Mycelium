"""EXP-2026-11-021: does Mylo work on the model that was just loaded?

One run of the frozen suite (``code/suite.json``) in two parts, each in its own
one-off backend container (the two worlds live in different databases):

    R="docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
       -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME=… -v $PWD/docs/research:/app/docs/research \
       backend uv run --no-sync --project web/backend python"
    E=docs/research/experiments/EXP-2026-11-021-agent-model-check
    $R $E/code/check.py --part demo --tag <tag>     # 20 questions, demo lab, live DB
    $R $E/code/check.py --part gate --tag <tag>     # 5 probes + 2 controls x 3, seed 101
    python3 $E/code/check.py --summarise --tag <tag>  # host, standard library only

``--model second`` routes the agent to ``EVAL2_LLM_MODEL`` (the second endpoint)
in this process only, as EXP-2026-11-016 did.

Nothing here changes product behaviour. The demo part asks through
EXP-2026-11-013's ``mylo_turn.run_question`` (fresh demo thread per question,
``demo_visitor`` = this experiment's id; deleted by ``--cleanup``). The gate
part rebuilds EXP-2026-11-016's seeded world 101 in its own database
(``mycelium_agent_eval_check_101_<model>``) and asks through round one's
``run_v2.run_plain``; grading is ``run_v2.grade_v2`` with the answer taken as
the reply the reader sees (final text + clarifying questions, EXP-2026-11-016
Amendment 1).

Each turn gets exactly one outcome class (PROTOCOL.md): ``answered`` (final
text that is not a give-up line), ``question`` (no final text, a clarifying
question shown), ``fallback`` (the loop's give-up line), ``failed`` (no final
text, a ``turn_failed`` error shown; Amendment 1), ``blank`` (none of these).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CODE = Path(__file__).resolve().parent
EXP = CODE.parent
ROOT = EXP.parent
VISITOR = "EXP-2026-11-021"
SEED = 101
LOCK = threading.Lock()


# -- shared -------------------------------------------------------------------------


def model_record(second: bool) -> dict:
    """The three names PROTOCOL.md asks for: the relay's list, the self-report,
    and the operator's statement. Called at the start and the end of a part."""
    import httpx

    base = os.environ.get("EVAL2_LLM_BASE_URL" if second else "LLM_BASE_URL") or os.environ["LLM_BASE_URL"]
    key = os.environ.get("EVAL2_LLM_API_KEY" if second else "LLM_API_KEY") or os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("EVAL2_LLM_MODEL" if second else "LLM_MODEL", "default-model")
    head = {"Authorization": f"Bearer {key}"} if key else {}
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "relay_model": model,
           "stated": os.environ.get("EVAL2_MODEL_NAME" if second else "EVAL_MODEL_NAME")
           or "not stated by the operator"}
    try:
        r = httpx.get(f"{base.rstrip('/')}/models", headers=head, timeout=30)
        listing = r.json().get("data", [])
        rec["relay_listing"] = [{"id": m.get("id"), "relay": m.get("relay")} for m in listing]
    except Exception as exc:  # noqa: BLE001
        rec["relay_listing"] = f"error: {type(exc).__name__}: {exc}"[:300]
    try:
        r = httpx.post(f"{base.rstrip('/')}/chat/completions", headers=head, timeout=300, json={
            "model": model, "max_tokens": 4000,
            "messages": [{"role": "user", "content":
                          "Which model are you, and who trained you? Answer in one sentence."}]})
        body = r.json()
        msg = (body.get("choices") or [{}])[0].get("message") or {}
        rec["self_report"] = {"content": msg.get("content"),
                              "reasoning": (msg.get("reasoning") or msg.get("reasoning_content") or "")[:600],
                              "server": body.get("system_fingerprint"), "status": r.status_code,
                              "error": body.get("error")}
    except Exception as exc:  # noqa: BLE001
        rec["self_report"] = f"error: {type(exc).__name__}: {exc}"[:300]
    return rec


def classify(text: str, questions: list[str]) -> str:
    from tools.agent.loop import EMPTY_GIVE_UP, RUNAWAY_GIVE_UP

    t = (text or "").strip()
    if t in (EMPTY_GIVE_UP.strip(), RUNAWAY_GIVE_UP.strip()):
        return "fallback"
    if t:
        return "answered"
    if any(q.strip() for q in questions):
        return "question"
    return "blank"


def thread_facts(thread_id: str) -> dict:
    """Questions shown, failed function results, empty retries — from the event log."""
    from tools.agent import store
    from tools.agent.models import AgentThread

    thread = AgentThread.objects.get(pk=thread_id)
    events = store.events(thread)
    questions = [str(e.payload.get("question") or "") for e in events if e.type == "question"]
    failed = [e.payload.get("name") for e in events if e.type == "tool_result"
              and ((e.payload.get("error") or {}).get("code") == "failed")]
    statuses = [(e.payload.get("status") or "ok") for e in events if e.type == "tool_result"]
    verdicts = [e.payload.get("action") for e in events if e.type == "verdict"]
    return {"questions": questions, "failed_inside": failed,
            "tool_results": len(statuses), "denied": statuses.count("denied"),
            "empty_retry_loop": verdicts.count("empty_retry"),
            "length_retry": verdicts.count("length_retry"),
            "runaway_retry": verdicts.count("runaway_retry")}


def write(path: Path, row: dict):
    with LOCK, path.open("a") as fh:
        fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")


def route_second():
    from tools.agent import llmcall

    name = os.environ["EVAL2_LLM_MODEL"]
    llmcall.model_name = lambda current=None: name
    return name


# -- part 1: the demo lab -----------------------------------------------------------


def part_demo(args, suite):
    sys.path[:0] = [str(ROOT / "EXP-2026-11-013-agent-answers-human-judged" / "code")]
    import mylo_turn

    mylo_turn.setup()
    from django.db import connection

    if args.model == "second":
        route_second()
    ctx = mylo_turn.demo_context()
    log = EXP / "logs" / f"demo_{args.tag}.jsonl"
    write(log, {"marker": "start", "model": model_record(args.model == "second")})

    def one(q):
        t0 = time.monotonic()
        try:
            row = mylo_turn.run_question(ctx, q, visitor=VISITOR)
            facts = thread_facts(row["thread"])
            row.update(facts)
            row["outcome"] = classify(row.get("final_text", ""), facts["questions"])
        except Exception as exc:  # noqa: BLE001
            row = {"id": q["id"], "error": f"{type(exc).__name__}: {exc}"[:400], "outcome": "error"}
        finally:
            connection.close()
        row.update({"id": q["id"], "group": q["group"], "source": q["source"],
                    "kind": q.get("kind"), "part": "demo", "model_arm": args.model,
                    "elapsed_s": round(time.monotonic() - t0, 3),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        write(log, row)
        print("demo", q["id"], row["outcome"], row.get("wall_s"), flush=True)

    qs = suite["demo"]
    if args.only:
        qs = [q for q in qs if q["id"] in args.only.split(",")]
    with ThreadPoolExecutor(max_workers=args.conc) as pool:
        list(pool.map(one, qs))
    write(log, {"marker": "end", "model": model_record(args.model == "second")})


# -- part 2: the seeded world -------------------------------------------------------


def part_gate(args, suite):
    g016 = ROOT / "EXP-2026-11-016-agent-gate-replication" / "code"
    r1 = ROOT / "EXP-2026-11-011-mylo-agent-baseline" / "code"
    sys.path[:0] = [str(g016), str(r1)]
    import run_v2  # noqa: E402  (inserts web/backend on sys.path)

    sys.path.insert(0, str(g016))
    import probes as P
    import world_seeded

    spec = world_seeded.spec(SEED)
    tasks = {t["id"]: t for t in P.probes(spec)}  # asserts no secret in any question
    db = f"mycelium_agent_eval_check_{SEED}_{args.model}"
    import psycopg

    url = re.sub(r"/[^/]+$", f"/{db}", os.environ["DATABASE_URL"])
    admin = re.sub(r"/[^/]+$", "/postgres", url)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{db}"')
    os.environ["DATABASE_URL"] = url
    import django
    from django.conf import settings

    django.setup()
    assert settings.DATABASES["default"]["NAME"] == db
    settings.CACHES["ambient"] = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                                  "LOCATION": "eval-ambient"}
    from django.core.cache import caches

    try:
        del caches["ambient"]
    except Exception:  # noqa: BLE001
        pass
    settings.AGENT_LEARNING = True
    settings.AMBIENT_ENABLED = False
    from config.celery import app as celery_app

    celery_app.conf.task_always_eager = True
    from django.core.management import call_command

    call_command("migrate", verbosity=0)
    import tasks as _r1_tasks  # noqa: F401  (loads the files tool, as round one did)
    from django.db import connection

    from tools.agent import llmcall, refs, stream

    refs.common_ref = run_v2.refs_token
    stream.use_memory_bus()
    w = world_seeded.build(spec)
    if args.model == "second":
        route_second()
    base = llmcall.default_port()
    log = EXP / "logs" / f"gate_{args.tag}.jsonl"
    write(log, {"marker": "start", "db": db, "model": model_record(args.model == "second")})

    def one(job):
        tid, rep = job
        task = tasks[tid]
        try:
            out = run_v2.run_plain(task, w, base)
            facts = thread_facts(out["thread"]) if out.get("thread") else {"questions": []}
            seen = "\n".join(x for x in [out.get("text") or "", *facts["questions"]] if x.strip())
            graded = dict(out, text=seen)  # the reply the reader sees (016 Amendment 1)
            passed, checks, points = run_v2.grade_v2(task, graded, w)
            outcome = classify(out.get("text", ""), facts["questions"])
        except Exception as exc:  # noqa: BLE001
            out, facts, passed, checks, points, outcome = (
                {"error": f"{type(exc).__name__}: {exc}"[:400]}, {}, False, {"error": True}, {}, "error")
        finally:
            connection.close()
        keep = {k: v for k, v in out.items() if not k.startswith("_")}
        write(log, {"id": tid, "rep": rep, "probe": task["probe"], "part": "gate",
                    "model_arm": args.model, "outcome": outcome, "passed": passed,
                    "checks": checks, "leaks": points, "seconds": out.get("seconds"),
                    "tokens": out.get("tokens"), **{k: v for k, v in facts.items()},
                    "output": keep, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        print("gate", tid, rep, outcome, passed, {k: v for k, v in points.items() if v}, flush=True)

    jobs = [(t["id"], r) for t in suite["gate"] for r in range(t["reps"])]
    if args.only:
        jobs = [j for j in jobs if j[0] in args.only.split(",")]
    with ThreadPoolExecutor(max_workers=args.conc) as pool:
        list(pool.map(one, jobs))
    write(log, {"marker": "end", "db": db, "model": model_record(args.model == "second")})


# -- summary (host, standard library) -----------------------------------------------


def _rows(path: Path):
    if not path.exists():
        return [], []
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    return [r for r in rows if "marker" not in r], [r for r in rows if "marker" in r]


def grade_demo(rows):
    """EXP-2026-11-018's grader, unchanged, on the questions that carry gold."""
    sys.path.insert(0, str(ROOT / "EXP-2026-11-018-agent-answers-gold" / "code"))
    import grade as G

    gold = {q["id"]: q for q in json.loads(
        (ROOT / "EXP-2026-11-018-agent-answers-gold" / "data" / "gold.json").read_text())["questions"]}
    out = {}
    for r in rows:
        src = r.get("source", "")
        if not src.startswith("EXP-2026-11-018:"):
            continue
        qid = src.split(":", 1)[1]
        q = gold.get(qid)
        if not q or "gold" not in q:
            continue
        r = dict(r, arm="a")
        out[r["id"]] = G.grade_answerable(r.get("final_text") or "", r, q["gold"], False)
    return out


def _turn_failed(t) -> bool:
    errs = t.get("errors") or (t.get("output") or {}).get("errors") or []
    return any((e.get("code") if isinstance(e, dict) else e) == "turn_failed" for e in errs)


def summarise(args):
    demo, dm = _rows(EXP / "logs" / f"demo_{args.tag}.jsonl")
    gate, gm = _rows(EXP / "logs" / f"gate_{args.tag}.jsonl")
    turns = demo + gate
    if not turns:
        print("no rows for", args.tag)
        return 1
    markers = dm + gm
    stated = sorted({(m.get("model") or {}).get("stated", "") for m in markers} - {""})
    selfr = []
    for m in markers:
        s = (m.get("model") or {}).get("self_report")
        if isinstance(s, dict):
            selfr.append((s.get("content") or s.get("reasoning") or "")[:120])
    for t in turns:  # Amendment 1: a turn that failed with turn_failed is not blank
        t["outcome_registered"] = t.get("outcome")
        if t.get("outcome") == "blank" and _turn_failed(t):
            t["outcome"] = "failed"
    count = {k: sum(1 for t in turns if t.get("outcome") == k)
             for k in ("answered", "question", "fallback", "blank", "failed", "error")}
    count["blank_as_registered"] = sum(1 for t in turns if t["outcome_registered"] == "blank")
    graded = grade_demo(demo)
    secs = [t.get("wall_s") or t.get("seconds") for t in turns]
    secs = [s for s in secs if isinstance(s, (int, float))]
    probes = [t for t in gate if t.get("probe")]
    controls = [t for t in gate if not t.get("probe")]
    leaks = sum(1 for t in probes if any((t.get("leaks") or {}).values()))
    ctrl_ok = sum(1 for t in controls if (t.get("checks") or {}).get("must_contain"))
    row = {
        "tag": args.tag,
        "model_stated": "; ".join(stated) or "not stated by the operator",
        "self_report": " | ".join(sorted(set(selfr)))[:300],
        "turns": len(turns),
        **count,
        "failed_inside": sum(len(t.get("failed_inside") or []) for t in turns),
        "gate_probe_turns": len(probes),
        "gate_leaks": leaks,
        "controls_passed": ctrl_ok,
        "controls_run": len(controls),
        "graded": len(graded),
        "graded_full": sum(g["full"] for g in graded.values()),
        "median_s": round(statistics.median(secs), 1) if secs else None,
        "worst_s": round(max(secs), 1) if secs else None,
        "started": min((m.get("model") or {}).get("at", "") for m in markers) if markers else "",
        "ended": max((m.get("model") or {}).get("at", "") for m in markers) if markers else "",
    }
    data = EXP / "data"
    data.mkdir(exist_ok=True)
    jpath = data / "metrics.json"
    doc = json.loads(jpath.read_text()) if jpath.exists() else {"rows": []}
    doc["rows"] = [r for r in doc["rows"] if r["tag"] != args.tag] + [row]
    doc["graded_by_question"] = {**doc.get("graded_by_question", {}), args.tag: graded}
    jpath.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    cpath = data / "metrics.csv"
    with cpath.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(row))
        wr.writeheader()
        for r in doc["rows"]:
            wr.writerow({k: r.get(k) for k in row})
    cols = [("tag", "Run"), ("model_stated", "Model (operator)"), ("turns", "Turns"),
            ("answered", "Answered"), ("question", "Question"), ("fallback", "Give-up line"),
            ("failed", "Failed (server)"), ("blank", "Blank"), ("blank_as_registered", "Blank as registered"),
            ("failed_inside", "Failed inside Mycelium"), ("gate_leaks", "Gate leaks / probes"),
            ("controls_passed", "Controls passed / run"), ("graded_full", "Full credit / graded"),
            ("median_s", "Median s"), ("worst_s", "Worst s")]
    pair = {"gate_leaks": "gate_probe_turns", "controls_passed": "controls_run", "graded_full": "graded"}
    lines = ["| " + " | ".join(c[1] for c in cols) + " |", "|" + "---|" * len(cols)]
    for r in doc["rows"]:
        cells = [f"{r.get(k)} / {r.get(pair[k])}" if k in pair else str(r.get(k)) for k, _ in cols]
        lines.append("| " + " | ".join(cells) + " |")
    (EXP / "tables").mkdir(exist_ok=True)
    (EXP / "tables" / "summary.md").write_text(
        "Generated by `code/check.py --summarise` from `data/metrics.json`.\n\n" + "\n".join(lines) + "\n")
    print(json.dumps(row, indent=1, ensure_ascii=False))
    return 0


def cleanup():
    sys.path[:0] = [str(ROOT / "EXP-2026-11-013-agent-answers-human-judged" / "code")]
    import mylo_turn

    mylo_turn.setup()
    from tools.agent.models import AgentThread

    qs = AgentThread.objects.filter(demo_visitor=VISITOR)
    n = qs.count()
    qs.delete()
    print(f"deleted {n} demo threads ({VISITOR})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["demo", "gate"])
    ap.add_argument("--summarise", action="store_true")
    ap.add_argument("--cleanup", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--model", choices=["instance", "second"], default="instance")
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--record-model", default="",
                    help="append one model record (relay list, self-report, operator's name) "
                         "to this JSONL path and exit; used by other round-three phases")
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    if args.record_model:
        rec = model_record(args.model == "second")
        with open(args.record_model, "a") as fh:
            fh.write(json.dumps({"label": args.label, **rec}, default=str) + "\n")
        print(json.dumps(rec, default=str)[:600])
        return 0
    assert args.conc <= 64, "at most 64 Mylo turns in flight (Amendment 3, second server)"
    if args.cleanup:
        cleanup()
        return 0
    if args.summarise:
        return summarise(args)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("AGENT_PARALLEL_CALLS", "0")
    (EXP / "logs").mkdir(exist_ok=True)
    suite = json.loads((CODE / "suite.json").read_text())
    if args.part == "demo":
        part_demo(args, suite)
    else:
        part_gate(args, suite)
    return 0


if __name__ == "__main__":
    sys.exit(main())

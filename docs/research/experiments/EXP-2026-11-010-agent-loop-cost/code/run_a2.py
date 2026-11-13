"""EXP-2026-11-010 A2: real questions through the web chat's turn path.

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-010-agent-loop-cost/code/run_a2.py [--reps 3] [--tag a2]

One turn at a time. Writes data/a2_<tag>.jsonl (one row per turn, appended as
it goes so a stopped run keeps what it measured) and logs/a2_<tag>_health.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mylo_turn  # noqa: E402

HERE = Path(__file__).resolve().parent.parent


def relay_health():
    import os
    base = os.environ.get("LLM_BASE_URL", "")
    req = urllib.request.Request(base.rstrip("/") + "/models",
                                 headers={"Authorization": f"Bearer {os.environ.get('LLM_API_KEY', '')}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        return [{"id": m.get("id"), "health": (m.get("relay") or {}).get("health"),
                 "upstream": (m.get("relay") or {}).get("upstream_model")} for m in data.get("data", [])]
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}


def run_concurrent(args, ctx, qs, out, health):
    """A3: the twelve questions of a repetition run with ``conc`` turns in
    flight; each row records the in-flight level."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connection

    lock = threading.Lock()

    def one(job):
        rep, q = job
        try:
            row = mylo_turn.run_question(ctx, q, visitor="EXP-2026-11-010")
        except Exception as exc:  # noqa: BLE001
            row = {"id": q["id"], "group": q["group"], "error": f"{type(exc).__name__}: {exc}"[:400]}
        finally:
            connection.close()
        row.update(rep=rep, conc=args.conc, at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        with lock, out.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        print(q["id"], rep, row.get("wall_s"), row.get("error", ""), flush=True)

    for rep in range(args.reps):
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.conc) as pool:
            list(pool.map(one, [(rep, q) for q in qs]))
        print("rep", rep, "wall", round(time.monotonic() - t0, 1), flush=True)
    health["after"] = relay_health()
    health["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (HERE / "logs").mkdir(exist_ok=True)
    (HERE / "logs" / f"a2_{args.tag}_health.json").write_text(json.dumps(health, indent=1))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--tag", default="a2")
    p.add_argument("--only", default="")
    p.add_argument("--stop-at", default="", help="local HH:MM; no new turn starts after it")
    p.add_argument("--conc", type=int, default=1,
                   help="Amendment 2 (A3): turns in flight at once (all questions of a repetition together)")
    args = p.parse_args()
    mylo_turn.setup()
    ctx = mylo_turn.demo_context()
    qs = json.loads((HERE / "code" / "questions_a2.json").read_text())["questions"]
    if args.only:
        qs = [q for q in qs if q["id"] in args.only.split(",")]
    out = HERE / "data" / f"a2_{args.tag}.jsonl"
    out.parent.mkdir(exist_ok=True)
    health = {"before": relay_health(), "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    if args.conc > 1:
        return run_concurrent(args, ctx, qs, out, health)
    with out.open("a") as fh:
        for rep in range(args.reps):
            for q in qs:
                if args.stop_at and time.strftime("%H:%M") >= args.stop_at and time.strftime("%H:%M") < "12:00":
                    print("stop-at reached", flush=True)
                    break
                try:
                    row = mylo_turn.run_question(ctx, q, visitor="EXP-2026-11-010")
                except Exception as exc:  # noqa: BLE001
                    row = {"id": q["id"], "group": q["group"], "error": f"{type(exc).__name__}: {exc}"[:400]}
                row["rep"] = rep
                row["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                fh.write(json.dumps(row, default=str) + "\n")
                fh.flush()
                print(q["id"], rep, row.get("wall_s"), row.get("model_calls"),
                      row.get("function_calls"), row.get("error", ""), flush=True)
    health["after"] = relay_health()
    health["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (HERE / "logs").mkdir(exist_ok=True)
    (HERE / "logs" / f"a2_{args.tag}_health.json").write_text(json.dumps(health, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

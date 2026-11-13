"""EXP-2026-11-014: load test of the local decision server (protocol v3).

    python3 docs/research/experiments/EXP-2026-11-014-decider-flash-load/code/bench.py \
        --states <scratch>/states.json --tag r1 [--url http://127.0.0.1:7500] \
        [--levels 1,2,4,8,12,16,24,32,48,64] [--runs 3]

Standard library only, run on the host. ``states.json`` is the output of
EXP-2026-11-007's ``extract.py`` (real production rerank states; it holds
profile text, so it stays in scratch). ``data/questions.json`` holds the
production questions (``dump_questions.py``).

Shapes (one request = one state):
- ``joint``: all of a pair's production questions in one request, native types
  (yes/no -> ``noul``, ordered scale -> ``score``) — what a port client sends;
- ``single``: one question per request (no batching of questions);
- ``choice``: all questions as ``choice`` with criteria, the documented form;
- ``synthetic``: one fixed ~400-character state with the joint questions, for
  comparison with EXP-2026-11-012's synthetic arm.

Per level: 20 untimed warm-up requests, then ``--runs`` timed passes over the
whole request list with ``c`` requests in flight. A level stops early (and no
higher level runs) when more than 5% of its requests fail or /health stops
answering. Never more than 64 in flight. Writes data/bench_<tag>.json: per
request latency, status, input tokens, and answers (keyed by pair id, never
state text).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MAX_IN_FLIGHT = 64
SYNTHETIC = {
    "researcher": "Career stage: postdoc. Works on marine heatwave forecasting with "
                  "machine learning and ocean reanalysis data.",
    "strand": "Marine heatwave early warning: seasonal prediction, sea surface "
              "temperature, deep learning, ensemble forecasting.",
    "item": "Paper: Evaluation of 1-14-day machine-learning forecasts of marine "
            "heatwaves in the North Atlantic, comparing deep learning to persistence.",
}


def convert(spec, form):
    ins = spec.get("instructions", "")
    if spec["type"] == "yesno":
        if form == "choice":
            return {"type": "choice", "instructions": ins,
                    "criteria": {"yes": spec.get("true") or "yes", "no": spec.get("false") or "no"}}
        q = {"type": "noul", "instructions": ins}
        if spec.get("true") or spec.get("false"):
            q["criteria"] = {"true": spec.get("true") or "", "false": spec.get("false") or ""}
        return q
    if spec["type"] == "score":
        if form == "choice":
            return {"type": "choice", "instructions": ins,
                    "criteria": {str(i): lvl for i, lvl in enumerate(spec["levels"])}}
        return {"type": "score", "instructions": ins, "criteria": list(spec["levels"])}
    raise ValueError(spec["type"])


def requests_for(shape, pairs, questions):
    out = []
    for i, p in enumerate(pairs):
        qs = questions[p["content_type"]]
        pid = f"{i}:{p['content_id'][:8]}:{p['cluster_id']}"
        if shape == "joint":
            out.append((pid, {"state": p["state"],
                              "questions": {k: convert(v, "native") for k, v in qs.items()}}))
        elif shape == "choice":
            out.append((pid, {"state": p["state"],
                              "questions": {k: convert(v, "choice") for k, v in qs.items()}}))
        elif shape == "single":
            for k, v in qs.items():
                out.append((f"{pid}#{k}", {"state": p["state"], "questions": {k: convert(v, "native")}}))
    if shape == "synthetic":
        qs = questions["paper"]
        body = {"state": SYNTHETIC, "questions": {k: convert(v, "native") for k, v in qs.items()}}
        out = [(f"syn:{i}", body) for i in range(len(pairs))]
    return out


def post(url, body, timeout=120):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url + "/v1/decisions", data=data,
                                 headers={"content-type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.load(r)
        return time.perf_counter() - t0, 200, payload
    except urllib.error.HTTPError as exc:
        return time.perf_counter() - t0, exc.code, {"error": exc.read()[:200].decode("utf8", "replace")}
    except Exception as exc:  # noqa: BLE001
        return time.perf_counter() - t0, 0, {"error": f"{type(exc).__name__}: {exc}"[:200]}


def health(url):
    try:
        with urllib.request.urlopen(url + "/health", timeout=10) as r:
            h = json.load(r)
        return {k: h.get(k) for k in ("status", "requests", "errors", "uptime_s", "served_model_name")}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": str(exc)[:200]}


def answers_of(payload):
    out = {}
    for k, a in (payload.get("answers") or {}).items():
        if "noul" in a:
            out[k] = {"yes": a["noul"]}
        elif "probabilities" in a:
            out[k] = a["probabilities"]
    return out


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def run_level(url, reqs, c, keep_answers):
    rows = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=c) as pool:
        for (pid, body), (lat, status, payload) in zip(
                reqs, pool.map(lambda r: post(url, r[1]), reqs)):
            row = {"id": pid, "lat": round(lat, 4), "status": status,
                   "tok": (payload.get("usage") or {}).get("input_tokens"),
                   "nq": len(body["questions"])}
            if keep_answers and status == 200:
                row["ans"] = answers_of(payload)
            if status != 200:
                row["err"] = payload.get("error")
            rows.append(row)
    wall = time.perf_counter() - t0
    ok = [r for r in rows if r["status"] == 200]
    lats = [r["lat"] for r in ok]
    return rows, {
        "wall_s": round(wall, 3), "requests": len(rows), "ok": len(ok),
        "error_rate": round(1 - len(ok) / len(rows), 4) if rows else None,
        "req_per_s": round(len(ok) / wall, 3),
        "decisions_per_s": round(sum(r["nq"] for r in ok) / wall, 3),
        "input_tok_per_s": round(sum(r["tok"] or 0 for r in ok) / wall, 1),
        "lat_p50": round(pct(lats, 0.5), 4) if lats else None,
        "lat_p95": round(pct(lats, 0.95), 4) if lats else None,
        "lat_p99": round(pct(lats, 0.99), 4) if lats else None,
        "lat_mean": round(statistics.mean(lats), 4) if lats else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:7500")
    ap.add_argument("--tag", default="r1")
    ap.add_argument("--levels", default="1,2,4,8,12,16,24,32,48,64")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--shapes", default="joint,single,choice,synthetic")
    args = ap.parse_args()
    raw = Path(args.states).read_bytes()
    pairs = json.loads(raw)["pairs"]
    questions = json.loads((HERE / "data" / "questions.json").read_text())["by_type"]
    levels = [int(x) for x in args.levels.split(",")]
    assert max(levels) <= MAX_IN_FLIGHT
    result = {"tag": args.tag, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "host": platform.node(), "python": platform.python_version(),
              "states_sha256": hashlib.sha256(raw).hexdigest(), "n_pairs": len(pairs),
              "health_before": health(args.url), "shapes": {}}
    out = HERE / "data" / f"bench_{args.tag}.json"
    stopped = False
    for shape in args.shapes.split(","):
        reqs = requests_for(shape, pairs, questions)
        result["shapes"][shape] = {"n_requests": len(reqs), "levels": {}}
        for c in levels:
            if stopped:
                break
            run_level(args.url, reqs[:20], min(c, 20), False)  # warm-up
            runs = []
            for k in range(args.runs):
                h0 = health(args.url)
                keep = c in (1, max(levels)) and k == 0
                rows, summary = run_level(args.url, reqs, c, keep)
                h1 = health(args.url)
                summary["health_requests_delta"] = (h1.get("requests") or 0) - (h0.get("requests") or 0)
                summary["health_errors_delta"] = (h1.get("errors") or 0) - (h0.get("errors") or 0)
                entry = {"summary": summary}
                if keep:
                    entry["rows"] = rows
                else:
                    entry["lat"] = [r["lat"] for r in rows]
                    entry["errors"] = [r for r in rows if r["status"] != 200][:20]
                runs.append(entry)
                print(shape, c, k, json.dumps(summary), flush=True)
                if summary["error_rate"] > 0.05 or h1.get("status") != "ok":
                    stopped = True
                    result["stopped"] = {"shape": shape, "level": c, "run": k, "health": h1}
                    break
            result["shapes"][shape]["levels"][str(c)] = runs
            out.write_text(json.dumps(result))
    result["health_after"] = health(args.url)
    result["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out.write_text(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

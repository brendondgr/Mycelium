"""EXP-2026-11-012 — d3-lite with K pairs per forward pass, outside GAIFA's server.

    GAIFA/services/decide/.venv/bin/python -I code/bench.py \
        --bodies <scratch>/bodies.json --out data/bench.json

Loads d3-lite with its own runtime (the folder GAIFA's decide serves), converts
every /v1/decide body with GAIFA's own ``to_d3``, and times:

- ``seq``: ``system_one`` one pair at a time (the server's model call, without
  HTTP, the engine lock or the GPU lease);
- ``batch K``: K pairs' token sequences in one ``D3.probabilities`` call.

Every configuration runs once untimed (Triton autotunes per shape), then once
timed. Writes only timings, per-pair answer probabilities and ids: no state
text.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

#: A checkout of the GAIFA repository (default: a sibling of this one).
GAIFA = Path(
    os.environ.get("GAIFA_DIR") or Path(__file__).resolve().parents[5].parent / "GAIFA"
)
MODEL = GAIFA / "data" / "models" / "decide" / "d3-lite"
SCRATCH = Path(os.environ.get("BENCH_SCRATCH", "/tmp"))
os.environ.setdefault("TRITON_CACHE_DIR", str(SCRATCH / "triton"))
os.environ.setdefault("TRITON_CACHE_AUTOTUNING", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(MODEL))
sys.path.insert(0, str(GAIFA / "services" / "decide"))

import torch  # noqa: E402
from d3_runtime import D3  # noqa: E402

from decide.models.d3_lite import D3Lite, to_d3  # noqa: E402

SYNTH_CALLS = 48
KS = (1, 4, 8)


def d3_questions(body):
    return {q["id"]: to_d3(q) for q in body["questions"]}


def probs_of(answer):
    """Every probability of one d3 answer, in a fixed order."""
    if "noul" in answer and "probabilities" not in answer:
        return [float(answer["noul"])]
    p = answer["probabilities"]
    return [float(p[k]) for k in sorted(p, key=str)]


def run_seq(model, bodies):
    out = []
    for b in bodies:
        res = model.system_one(state=b["input"], questions=d3_questions(b))
        out.append(res["answers"])
    return out


def run_batched(model, bodies, k):
    out = []
    for start in range(0, len(bodies), k):
        group = bodies[start : start + k]
        prepared = [model.prepare(b["input"], d3_questions(b)) for b in group]
        seqs, counts, owners = [], [], []
        for i, pr in enumerate(prepared):
            assert not pr.errors, pr.errors
            for key in pr.runnable:
                seqs.append(pr.sequences[key])
                counts.append(len(pr.questions[key].keys))
                owners.append((i, key))
        probs = model.probabilities(seqs, counts)
        per = [{} for _ in group]
        for (i, key), row in zip(owners, probs, strict=True):
            per[i][key] = row
        for pr, p in zip(prepared, per, strict=True):
            tokens = sum(len(pr.sequences[k]) for k in pr.runnable)
            out.append(model.respond(pr, p, tokens)["answers"])
    return out


def timed(fn, *a):
    fn(*a)  # untimed: Triton autotunes each new shape
    torch.cuda.synchronize()
    started = time.perf_counter()
    answers = fn(*a)
    torch.cuda.synchronize()
    return answers, time.perf_counter() - started


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bodies", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    src = json.loads(Path(args.bodies).read_text())

    torch.backends.cudnn.enabled = False  # as GAIFA's adapter does (MIOpen search)
    problems = D3Lite.check(MODEL)
    assert not problems, problems
    t0 = time.perf_counter()
    model = D3.from_pretrained(str(MODEL), device="cuda:0", batch_size=32, verify="fast")
    load_s = time.perf_counter() - t0

    results = {"synthetic": {}, "real": {}}
    synth = [src["synthetic"]] * SYNTH_CALLS
    real = [r["body"] for r in src["real"]]

    for name, bodies in (("synthetic", synth), ("real", real)):
        ans, wall = timed(run_seq, model, bodies)
        results[name]["seq"] = {"pairs": len(bodies), "wall_s": round(wall, 4)}
        seq_answers = ans
        for k in KS:
            ans, wall = timed(run_batched, model, bodies, k)
            results[name][f"batch_{k}"] = {"pairs": len(bodies), "wall_s": round(wall, 4)}
            diffs = [
                abs(x - y)
                for a, b in zip(seq_answers, ans, strict=True)
                for q in a
                for x, y in zip(probs_of(a[q]), probs_of(b[q]), strict=True)
            ]
            results[name][f"batch_{k}"]["max_abs_diff_vs_seq"] = max(diffs)
            print(f"{name} batch {k}: {len(bodies) / wall:.2f} pairs/s", flush=True)
        print(f"{name} seq: {len(bodies) / results[name]['seq']['wall_s']:.2f} pairs/s",
              flush=True)
        if name == "real":
            results["real_answers_seq"] = [
                {"content_id": r["content_id"], "cluster_id": r["cluster_id"],
                 "control": r["control"], "answers": {q: probs_of(a[q]) for q in a}}
                for r, a in zip(src["real"], seq_answers, strict=True)
            ]

    payload = {
        "meta": {
            "experiment": "EXP-2026-11-012",
            "model": f"vllm-sr/d3-lite@{D3Lite.REVISION}",
            "device": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "python": platform.python_version(),
            "batch_size": 32,
            "load_s": round(load_s, 2),
            "synthetic_calls": SYNTH_CALLS,
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        "results": results,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

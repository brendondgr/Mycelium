"""EXP-2026-11-012, arm B — Qwen3-4B on llama.cpp, real states, 1/4/8 in flight.

    uv run --no-sync --project web/backend python code/qwen_real.py \
        --states <scratch>/states.json --url http://127.0.0.1:5180 \
        --out data/qwen_real.json

Added after arm A ran (see PROTOCOL.md, Amendment): EXP-2026-11-009 measured
llama.cpp concurrency only on the short synthetic state, so the real-state
comparison with d3-lite had no concurrent llama.cpp number. Same 165 states,
same production questions, same client as EXP-2026-11-009. Each concurrency
level is preceded by an untimed pass over the first 8 pairs. Writes timings
only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "web" / "backend"))
sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.core.decisions import PortConfig, PortDecisionClient  # noqa: E402

from tools.recommendation.typesafe_rerank import questions_for  # noqa: E402

LEVELS = (1, 4, 8)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--states", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    pairs = json.loads(Path(args.states).read_text())["pairs"]
    client = PortDecisionClient(PortConfig(url=args.url, timeout=300))

    def one(pair):
        started = time.perf_counter()
        try:
            client.ask(pair["state"], questions_for(pair["content_type"]))
            ok = True
        except Exception:  # noqa: BLE001 — counted
            ok = False
        return ok, (time.perf_counter() - started) * 1000

    out = {"meta": {"url": args.url, "protocol": client.protocol,
                    "model": client.model, "pairs": len(pairs)}, "levels": {}}
    for c in LEVELS:
        with ThreadPoolExecutor(max_workers=c) as pool:
            list(pool.map(one, pairs[:8]))  # untimed warm-up
            started = time.perf_counter()
            res = list(pool.map(one, pairs))
            wall = time.perf_counter() - started
        lat = sorted(ms for _ok, ms in res)
        out["levels"][str(c)] = {
            "pairs": len(pairs),
            "failures": sum(not ok for ok, _ in res),
            "wall_s": round(wall, 3),
            "pairs_per_s": round(len(pairs) / wall, 3),
            "latency_ms_p50": round(lat[len(lat) // 2], 1),
            "latency_ms_p95": round(lat[min(len(lat) - 1, round(0.95 * (len(lat) - 1)))], 1),
        }
        print(c, out["levels"][str(c)], flush=True)
    Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

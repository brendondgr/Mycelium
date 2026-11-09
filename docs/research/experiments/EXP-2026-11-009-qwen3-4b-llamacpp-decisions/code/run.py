"""EXP-2026-11-009 — EXP-2026-11-007's states through a model on a port.

    uv run --no-sync --project web/backend python code/run.py \
        --states <scratch>/states.json --url http://127.0.0.1:5180

Asks the production rerank questions (``typesafe_rerank.questions_for``)
through Mycelium's own port client (``apps.core.decisions``), one call per
pair, sequentially, then repeats five pairs three times. Writes
``data/pairs.json`` with the answers in the shared decision shape and the
reader's profile reduced to its SHA-256 and length.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO / "web" / "backend"))
sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from apps.core.decisions import PortConfig, PortDecisionClient  # noqa: E402

from tools.recommendation.typesafe_rerank import questions_for  # noqa: E402


def ask(client, pair):
    started = time.perf_counter()
    try:
        result = client.ask(pair["state"], questions_for(pair["content_type"]))
    except Exception as exc:  # noqa: BLE001 — a failed pair is a recorded pair
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    return {
        "ok": True,
        "model": result.model,
        "answers": result.answers_as_dicts(),
        "usage": dict(result.usage),
        "wall_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    src = json.loads(Path(args.states).read_text())
    pairs = src["pairs"]
    client = PortDecisionClient(
        PortConfig(url=args.url, model=args.model, timeout=120)
    )
    protocol, model = client.protocol, client.model
    print(f"{len(pairs)} pairs -> {args.url} ({protocol}, {model})", flush=True)

    started = time.time()
    results = []
    for i, pair in enumerate(pairs, 1):
        results.append(ask(client, pair))
        if i % 25 == 0:
            print(f"  {i}/{len(pairs)}", flush=True)
    wall = time.time() - started

    determinism = []
    on_theme = [p for p in pairs if not p["control"]]
    for pair in on_theme[:: max(1, len(on_theme) // 5)][:5]:
        reps = [ask(client, pair) for _ in range(3)]
        determinism.append(
            {
                "content_id": pair["content_id"],
                "cluster_id": pair["cluster_id"],
                "worth": [
                    (r.get("answers") or {}).get("worth", {}).get("noul") for r in reps
                ],
            }
        )

    records = []
    for pair, result in zip(pairs, results, strict=True):
        rec = {k: v for k, v in pair.items() if k != "state"}
        rec["port"] = result
        records.append(rec)
    profile = pairs[0]["state"]["researcher"] if pairs else ""
    payload = {
        "meta": {
            "experiment": "EXP-2026-11-009",
            "states_from": "EXP-2026-11-007 extract.py, 2026-11-09",
            "user": src["user"],
            "question_version": src["question_version"],
            "url": args.url,
            "protocol": protocol,
            "model": model,
            "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "researcher": {
                "sha256": hashlib.sha256(profile.encode()).hexdigest(),
                "chars": len(profile),
            },
        },
        "totals": {
            "calls": len(pairs) + 3 * len(determinism),
            "failures": sum(1 for r in results if not r["ok"]),
            "wall_seconds_main": round(wall, 2),
            "input_tokens_main": sum(
                (r.get("usage") or {}).get("input_tokens", 0) for r in results
            ),
        },
        "pairs": records,
        "determinism": determinism,
    }
    out = EXP_DIR / "data" / "pairs.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(
        f"{len(pairs)} pairs, {payload['totals']['failures']} failed, "
        f"{wall:.1f}s -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

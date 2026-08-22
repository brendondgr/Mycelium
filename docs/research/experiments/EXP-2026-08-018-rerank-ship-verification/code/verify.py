"""Ship verification for the cross-encoder rerank stage (`EXP-2026-08-018`).

    docker compose up -d postgres
    uv run --directory web/backend python .../code/verify.py

Two things, and the first matters more than the second.

1. **Flag off changes nothing.** The stage is wired into the tail of the shared
   fusion path, which the eval harness's profile arms also call. If turning it off
   is not *identical* to the code before it existed, every historical number in
   this record is in doubt. So the same target is fused twice and the surfaced
   ids, the scores and the persist-row signals are compared field by field.
2. **What it costs and how much it moves**, on the real store with the real model.

No verdict about quality is computed or implied — that is `EXP-2026-08-015` …
`-017`, and it is a preference. Writes `data/metrics.json`.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_URL"] = os.environ.get(
    "MYCELIUM_DATABASE_URL", "postgres://mycelium:mycelium@127.0.0.1:11450/mycelium"
)
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH", str(REPO_ROOT / "data" / "eval-cache" / "fastembed")
)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

#: Two declared interests from the store's richest real profile, so the
#: multi-interest merge is actually exercised rather than the n=1 degenerate case.
INTERESTS = ["agentic healthcare systems", "knowledge graph construction"]


def main() -> int:
    import django

    django.setup()
    from apps.content import reranking
    from apps.content.interests_query import SearchInterest
    from apps.content.models import ContentItem
    from apps.content.pipeline import fuse_interests_pool
    from django.test import override_settings

    search_ints = [
        SearchInterest(label=text, query_text=text, embed_text=text)
        for text in INTERESTS
    ]

    def run(**flags):
        reranking.reset_rerank_cache()
        with override_settings(**flags):
            started = time.perf_counter()
            pairs, rows, pool = fuse_interests_pool(
                search_ints,
                content_type=ContentItem.Type.PAPER,
                surface_limit=250,
                pool_per_interest=100,
                beta=0.15,
                emit=lambda message: None,
                created_on=None,
                match_threshold=0.5,
            )
            return {
                "seconds": time.perf_counter() - started,
                "pool": pool,
                "ids": [str(item.id) for item, _score in pairs],
                "scores": [round(score, 8) for _item, score in pairs],
                "signals": [dict(extra) for _i, _s, extra in rows],
            }

    off = run(RERANK_ENABLED=False)
    on = run(RERANK_ENABLED=True, RERANK_CONTENT_TYPES=["paper"])

    moved = sum(1 for a, b in zip(off["ids"], on["ids"], strict=True) if a != b)
    off_signal_keys = sorted({k for s in off["signals"] for k in s})
    metrics = {
        "interests": INTERESTS,
        "pool": off["pool"],
        "surfaced": len(off["ids"]),
        # --- the invariant -------------------------------------------------
        "flag_off_signals_carry_no_rerank_key": "rerank_rank" not in off_signal_keys,
        "flag_off_signal_keys": off_signal_keys,
        "same_candidate_set": sorted(off["ids"]) == sorted(on["ids"]),
        "same_pool_size": off["pool"] == on["pool"],
        "scores_unchanged_by_the_stage": sorted(off["scores"])
        == sorted(on["scores"]),
        # --- what it does and costs -----------------------------------------
        "positions_moved": moved,
        "positions_moved_share": round(moved / max(len(off["ids"]), 1), 4),
        "flag_on_records_rerank_rank": any("rerank_rank" in s for s in on["signals"]),
        "seconds_off": round(off["seconds"], 3),
        "seconds_on": round(on["seconds"], 3),
        "rerank_overhead_seconds": round(on["seconds"] - off["seconds"], 3),
        "device": list(reranking.resolve_device()),
        "model": reranking.DEFAULT_MODEL,
        "depth": reranking.rerank_depth(),
        "max_pairs": reranking.max_pairs(),
    }

    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(metrics, indent=2, sort_keys=True))

    ok = (
        metrics["flag_off_signals_carry_no_rerank_key"]
        and metrics["same_candidate_set"]
        and metrics["same_pool_size"]
        and metrics["scores_unchanged_by_the_stage"]
    )
    print("\nINVARIANT:", "HOLDS" if ok else "VIOLATED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

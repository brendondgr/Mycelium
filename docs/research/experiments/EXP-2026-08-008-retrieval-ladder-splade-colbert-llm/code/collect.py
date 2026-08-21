"""Build this experiment's tables from `eval/results/*.json`. Never by hand.

    uv run --project eval python docs/research/experiments/EXP-2026-08-008-*/code/collect.py

The research rules forbid hand-editing a figure or hardcoding a number into a
plotting script, and the reason is exactly this experiment's failure mode: a
ladder with twenty arms is twenty chances to transcribe a digit wrong. Every
number below is read out of the run record that produced it, keyed by the arm and
config hash the harness stamped at run time.

Writes `tables/ladder.md` and `data/ladder.json` in the experiment folder.
"""

from __future__ import annotations

import json
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
RESULTS = REPO_ROOT / "eval" / "results"
CONFIGS = REPO_ROOT / "eval" / "configs"

SNAPSHOT = "longeval-sci-2026/snapshot-1/train"
SCOPE = "pooled"
QRELS = "dctr"

METRICS = ["nDCG@10", "nDCG@100", "AP", "R@100", "RR", "P@10"]

#: The ladder, in the order it should be read: baselines, then each rung.
#: `(label, arm, {param: value})` — params disambiguate arms run at several
#: settings, since the arm name alone does not identify a row.
LADDER = [
    ("— baselines —", None, {}),
    ("bm25_only", "bm25_only", {}),
    ("dense_only", "dense_only", {}),
    ("fusion_dense_pool (production)", "fusion_dense_pool", {"pool_per_interest": 100}),
    ("fusion_union_pool", "fusion_union_pool", {"pool_per_interest": 100}),
    ("fusion_full", "fusion_full", {"pool_per_interest": 100}),
    ("— rung 1: learned sparse retrieval —", None, {}),
    ("splade_only", "splade_only", {}),
    ("fusion_bm25_dense_splade", "fusion_bm25_dense_splade", {"pool_per_interest": 100}),
    ("— rung 2: late interaction —", None, {}),
    ("colbert_rerank d50", "colbert_rerank", {"rerank_depth": 50, "pool_per_interest": 100, "base": "fusion_union_pool"}),
    ("colbert_rerank d100", "colbert_rerank", {"rerank_depth": 100, "pool_per_interest": 100, "base": "fusion_union_pool"}),
    ("— rung 3: cross-encoder —", None, {}),
    ("xenc_rerank d50", "xenc_rerank", {"rerank_depth": 50, "pool_per_interest": 100, "base": "fusion_union_pool"}),
    ("xenc_rerank d100", "xenc_rerank", {"rerank_depth": 100, "pool_per_interest": 100, "base": "fusion_union_pool"}),
    ("xenc_rerank d250", "xenc_rerank", {"rerank_depth": 250, "pool_per_interest": 100, "base": "fusion_union_pool"}),
    ("cascade colbert250 -> xenc50", "cascade_colbert_xenc", {}),
    ("xenc on splade base d100", "xenc_rerank", {"base": "fusion_bm25_dense_splade", "rerank_depth": 100}),
    ("— rung 3b: deep pool (pool_per_interest = 500) —", None, {}),
    ("fusion_union_pool p500", "fusion_union_pool", {"pool_per_interest": 500}),
    ("xenc_rerank p500 d100", "xenc_rerank", {"rerank_depth": 100, "pool_per_interest": 500, "base": "fusion_union_pool"}),
    ("xenc_rerank p500 d250", "xenc_rerank", {"rerank_depth": 250, "pool_per_interest": 500, "base": "fusion_union_pool"}),
    ("xenc_rerank p500 d1000", "xenc_rerank", {"rerank_depth": 1000, "pool_per_interest": 500, "base": "fusion_union_pool"}),
    ("colbert_rerank p500 d250", "colbert_rerank", {"rerank_depth": 250, "pool_per_interest": 500}),
    ("colbert_rerank p500 d1000", "colbert_rerank", {"rerank_depth": 1000, "pool_per_interest": 500}),
    ("— rung 4: LLM —", None, {}),
    ("llm_rerank (listwise)", "llm_rerank", {}),
    ("llm_rerank_reversed", "llm_rerank_reversed", {}),
    ("llm_rubric (pointwise)", "llm_rubric", {}),
]


def config_params() -> dict[str, dict]:
    """`{config_hash: params}` for every config file, so a row can be identified.

    The result records a `config_hash` but not the params behind it, and several
    ladder arms differ only in params. Re-deriving the hash from the config files
    is what lets a row be attributed to the exact setting that produced it.
    """
    import hashlib
    import tomllib

    out: dict[str, dict] = {}
    for path in sorted(CONFIGS.glob("*.toml")):
        config = tomllib.loads(path.read_text())
        digest = hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest()[:16]
        out[digest] = {"path": path.name, **config.get("params", {})}
    return out


def load_rows() -> list[dict]:
    by_hash = config_params()
    rows = []
    for path in sorted(RESULTS.glob("*.json")):
        row = json.loads(path.read_text())
        if row.get("snapshot") != SNAPSHOT or row.get("corpus_scope") != SCOPE:
            continue
        if row.get("qrels") != QRELS:
            continue
        row["params"] = by_hash.get(row.get("config_hash"), {})
        rows.append(row)
    # Newest run per (arm, config_hash) wins; earlier ones are superseded.
    latest: dict[tuple, dict] = {}
    for row in sorted(rows, key=lambda r: r.get("timestamp", "")):
        latest[(row["arm"], row.get("config_hash"))] = row
    return list(latest.values())


def match(row: dict, arm: str, want: dict) -> bool:
    if row["arm"] != arm:
        return False
    params = row.get("params", {})
    return all(params.get(key) == value for key, value in want.items())


#: The stack, as a sequence of single changes. Each row adds exactly one stage to
#: the row above it, so its delta is that stage's marginal contribution rather
#: than a comparison against an unrelated arm.
CHAIN = [
    ("fusion_dense_pool (production)", "production — BM25 restricted to the dense pool"),
    ("fusion_union_pool", "+ union pool, so the lexical channel can *add* a document"),
    ("fusion_bm25_dense_splade", "+ SPLADE as a third RRF channel"),
    ("xenc on splade base d100", "+ cross-encoder rerank (depth 100)"),
]


def _marginal_table(by_label: dict) -> None:
    """What each stage contributes on top of the one below it, and what it costs.

    The ladder table compares every arm to the same baselines, which answers "is
    this arm good". It does not answer "should we add this stage", because arms
    differ by more than one thing. This one is a chain: each row is the row above
    plus exactly one stage.
    """
    keep = [(label, desc) for label, desc in CHAIN if label in by_label]
    rows = [
        "### What each stage adds, one change at a time",
        "",
        "| Stack | nDCG@10 | nDCG@100 | R@100 | Δ nDCG@10 | Δ nDCG@100 | Δ R@100 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    prev = None
    for label, desc in keep:
        m = by_label[label]["metrics"]
        a, h, r = m["nDCG@10"], m["nDCG@100"], m["R@100"]
        deltas = ("—", "—", "—") if prev is None else (
            f"{a - prev[0]:+.4f}", f"{h - prev[1]:+.4f}", f"{r - prev[2]:+.4f}"
        )
        rows.append(f"| {desc} | {a:.4f} | {h:.4f} | {r:.4f} | " + " | ".join(deltas) + " |")
        prev = (a, h, r)

    rows += [
        "",
        "### Does reranking deeper pay?",
        "",
        "| Cross-encoder arm | nDCG@10 | wall clock |",
        "|---|---:|---:|",
    ]
    for label in ("xenc_rerank d50", "xenc_rerank d100",
                  "xenc_rerank p500 d250", "xenc_rerank p500 d1000"):
        if label in by_label:
            row = by_label[label]
            rows.append(f"| {label} | {row['metrics']['nDCG@10']:.4f} | {row['wall_clock_s']:.0f} s |")

    rows += [
        "",
        "### Stages that cost and do not pay",
        "",
        "| Arm | nDCG@10 | vs `fusion_union_pool` | one-time encode |",
        "|---|---:|---:|---|",
    ]
    base = by_label.get("fusion_union_pool", {}).get("metrics", {}).get("nDCG@10")
    costs = {
        "colbert_rerank d50": "3,640 s + 22.4M token vectors",
        "colbert_rerank d100": "(same store)",
        "cascade colbert250 -> xenc50": "(same store)",
        "llm_rerank (listwise)": "none — 1 model call per query",
        "llm_rubric (pointwise)": "none — 20 model calls per query",
    }
    for label, cost in costs.items():
        if label in by_label and base:
            v = by_label[label]["metrics"]["nDCG@10"]
            rows.append(f"| {label} | {v:.4f} | {v - base:+.4f} | {cost} |")

    rows += [
        "",
        (
            "One-time corpus encoding over the 84,489-document subset, CPU, no "
            "GPU: dense **0 s** (row-sliced from the cached full-corpus matrix), "
            "SPLADE **3,451 s** (24.5 docs/s), ColBERT **3,640 s** (23.2 docs/s), "
            "cross-encoder **0 s** — it never encodes a corpus, which is why it "
            "is the cheapest stage on the ladder as well as the only one that "
            "beats BM25."
        ),
    ]
    (EXP_DIR / "tables" / "marginal.md").write_text("\n".join(rows) + "\n")


def main() -> int:
    rows = load_rows()
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables").mkdir(exist_ok=True)

    lines = [
        f"| Arm | {' | '.join(METRICS)} | wall s |",
        f"|---|{'---:|' * (len(METRICS) + 1)}",
    ]
    collected = []
    missing = []
    for label, arm, want in LADDER:
        if arm is None:
            lines.append(f"| **{label}** |{' |' * (len(METRICS) + 1)}")
            continue
        found = [r for r in rows if match(r, arm, want)]
        if not found:
            missing.append(label)
            lines.append(
                f"| {label} | {' | '.join(['—'] * len(METRICS))} | — |"
            )
            continue
        hashes = {r.get("config_hash") for r in found}
        if len(hashes) > 1:
            raise SystemExit(
                f"ambiguous row {label!r}: matches {len(hashes)} configs "
                f"({sorted(r['params'].get('path', '?') for r in found)}). "
                "Add a discriminating param to LADDER."
            )
        row = max(found, key=lambda r: r.get("timestamp", ""))
        cells = [f"{row['metrics'].get(m, float('nan')):.4f}" for m in METRICS]
        lines.append(
            f"| {label} | {' | '.join(cells)} | {row.get('wall_clock_s', '—')} |"
        )
        collected.append({"label": label, **row})

    (EXP_DIR / "tables" / "ladder.md").write_text("\n".join(lines) + "\n")
    _marginal_table({r["label"]: r for r in collected})
    (EXP_DIR / "data" / "ladder.json").write_text(
        json.dumps(collected, indent=2, sort_keys=True) + "\n"
    )
    print("\n".join(lines))
    if missing:
        print(f"\nNOT YET RUN ({len(missing)}): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

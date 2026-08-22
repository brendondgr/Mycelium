"""Intervals, curves and the deployed-gate invariant for `EXP-2026-08-013`.

`code/run.py` produces the per-interest and per-target rows; this reads them and
answers the three questions `PROTOCOL.md` fixed in advance, in that order:

1. **Is the mechanism live?** `bm25_reachability@100` against the pre-registered
   0.90 / 0.50 decision thresholds, with a paired bootstrap from
   `harness.stats` — the same bootstrap, seed and rule as every interval since
   `EXP-2026-08-009` — and the pre-registered real-target sensitivity split.
2. **Does it scale the way the arithmetic says?** Reachability against scope
   size across the 17 gather days plus the corpus-wide and opportunity regimes.
3. **Does anything reach the reader?** Entrants through the deployed surfacing
   gate, split into union-only and reordered-in.

Writes `tables/*.md` and `data/analysis.json`. No LLM, no network, no database —
it is a pass over the two CSVs, so it is cheap to re-run.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))

from harness import stats

ARMS = ("a2_union_harness", "a2p_union_prod", "a3_union_fts", "a4_union_fts_or")
ARM_LABELS = {
    "a2_union_harness": "A2 union (harness arm)",
    "a2p_union_prod": "A2p union (shippable)",
    "a3_union_fts": "A3 union via FTS (`websearch`)",
    "a4_union_fts_or": "A4 union via FTS (OR)",
}
#: Deployed regimes — the ones the pre-registered decision rule is about. R2 is
#: the corpus-wide paper scope, which the feed does not use.
DEPLOYED = ("R1:", "R3:")


def read(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def f(row, key):
    value = row.get(key, "")
    return float(value) if value not in ("", "None") else None


def main() -> int:
    per_interest = read(EXP_DIR / "data" / "per_interest.csv")
    per_target = read(EXP_DIR / "data" / "metrics.csv")

    out: dict = {}
    lines: list[str] = []

    # ---------------------------------------------------------------- (1)
    def reach(rows, key="bm25_reachability"):
        return [f(r, key) for r in rows if f(r, key) is not None]

    # `paired_bootstrap` is used here on a **level**, not on a paired contrast:
    # reachability has no baseline arm to be paired against, because there are no
    # relevance judgments on this corpus (PROTOCOL.md §2). Only `mean`, `ci_low`
    # and `ci_high` are read; the win/loss/sign fields of the returned `Paired`
    # are meaningless for a one-sample resample and are deliberately not shown.

    deployed_rows = [r for r in per_interest if r["regime"].startswith(DEPLOYED)]
    real_rows = [r for r in deployed_rows if r["real_target"] == "True"]

    groups = {
        "all regimes, all targets": per_interest,
        "deployed regimes (R1+R3), all targets": deployed_rows,
        "deployed regimes, real targets only": real_rows,
        "R1 papers (day-scoped, deployed)": [
            r for r in per_interest if r["regime"].startswith("R1:")
        ],
        "R3 opportunities (corpus-scoped, deployed)": [
            r for r in per_interest if r["regime"].startswith("R3:")
        ],
        "R2 papers corpus-wide (not deployed)": [
            r for r in per_interest if r["regime"].startswith("R2:")
        ],
    }

    lines += [
        "### 1. `bm25_reachability@100` — is there anything for a wider pool to reach?",
        "",
        (
            "*Of the corpus-wide BM25 top-100 for one declared interest, the "
            "fraction already inside the dense pool the deployed builder would "
            "have used. `1.0` ⇒ the union pool can add nothing and the C-008 fix "
            "is inert; `0.0` ⇒ everything lexically strong is unreachable today. "
            "The pre-registered thresholds are **≥ 0.90 inert** and **≤ 0.50 "
            "live**.*"
        ),
        "",
        "| Group | n | median | mean | 95% CI (bootstrap) | p10 | p90 | verdict |",
        "|---|---:|---:|---:|---|---:|---:|:--:|",
    ]
    out["reachability"] = {}
    for name, rows in groups.items():
        values = reach(rows)
        if not values:
            continue
        result = stats.paired_bootstrap(values)
        median = statistics.median(values)
        ordered = sorted(values)
        verdict = (
            "**inert**" if median >= 0.90 else "**live**" if median <= 0.50 else "between"
        )
        lines.append(
            f"| {name} | {len(values)} | **{median:.3f}** | {result.mean:.3f} | "
            f"[{result.ci_low:.3f}, {result.ci_high:.3f}] | "
            f"{ordered[len(ordered) // 10]:.2f} | "
            f"{ordered[(len(ordered) * 9) // 10]:.2f} | {verdict} |"
        )
        out["reachability"][name] = {
            "n": len(values),
            "median": median,
            "mean": result.mean,
            "ci": [result.ci_low, result.ci_high],
            "verdict": verdict.replace("*", ""),
        }

    # ---------------------------------------------------------------- (2)
    by_regime: dict[str, list[dict]] = defaultdict(list)
    for row in per_interest:
        by_regime[row["regime"]].append(row)

    lines += [
        "",
        "### 2. Reachability against corpus size",
        "",
        (
            "*The deficit is arithmetic before it is anything else: a dense pool "
            "of 100 per interest covers a small gather batch and cannot cover a "
            "corpus. Every row is the same 38 declared interests.*"
        ),
        "",
        (
            "| Regime | corpus | BM25 reach (median) | FTS-OR reach | "
            "emitted after the 0.15 floor |"
        ),
        "|---|---:|---:|---:|---:|",
    ]
    curve = []
    for regime, rows in sorted(
        by_regime.items(), key=lambda kv: int(kv[1][0]["scope_size"])
    ):
        size = int(rows[0]["scope_size"])
        bm25 = statistics.median(reach(rows))
        fts_or = reach(rows, "fts_or_reachability")
        emitted = [f(r, "emitted_after_floor") for r in rows]
        lines.append(
            f"| `{regime}` | {size:,} | {bm25:.3f} | "
            f"{statistics.median(fts_or):.3f} | "
            f"{statistics.median(emitted):.0f} |"
        )
        curve.append({"regime": regime, "corpus": size, "bm25_reachability": bm25})
    out["curve"] = curve

    # ---------------------------------------------------------------- (3)
    lines += [
        "",
        "### 3. Does any of it reach the reader?",
        "",
        (
            "*Entrants are documents in the union arm's surfaced list that the "
            "deployed arm never surfaced, over all 126 (regime, target) pairs. "
            "**Deployed gate** is the code as it stands, where `best_cosine` is "
            "populated only by the dense channel. **Completed gate** additionally "
            "computes the cosine for union-only candidates, which any real fix "
            "must do.*"
        ),
        "",
        (
            "| Arm | entrants, deployed gate | of which union-only | entrants, "
            "completed gate | of which union-only | pairs with ≥1 union-only "
            "entrant |"
        ),
        "|---|---:|---:|---:|---:|---:|",
    ]
    out["entrants"] = {}
    for arm in ARMS:
        deployed = sum(int(r[f"{arm}__entrants_deployed_gate"]) for r in per_target)
        deployed_union = sum(
            int(r[f"{arm}__entrants_deployed_union_only"]) for r in per_target
        )
        completed = sum(int(r[f"{arm}__entrants_completed_gate"]) for r in per_target)
        union_only = sum(int(r[f"{arm}__entrants_union_only"]) for r in per_target)
        pairs = sum(1 for r in per_target if int(r[f"{arm}__entrants_union_only"]) > 0)
        lines.append(
            f"| {ARM_LABELS[arm]} | {deployed:,} | **{deployed_union}** | "
            f"{completed:,} | {union_only:,} | {pairs}/{len(per_target)} |"
        )
        out["entrants"][arm] = {
            "deployed_gate": deployed,
            "deployed_gate_union_only": deployed_union,
            "completed_gate": completed,
            "completed_gate_union_only": union_only,
            "pairs_with_union_only": pairs,
            "pairs": len(per_target),
        }

    # ---------------------------------------------------------------- Q-018
    # "How many candidates does `fuse_interest` emit per target, and is the 0.15
    # floor the binding cut?" — answerable for free from the same rows. The pool
    # is shared across a target's interests, so the survival rate is emitted per
    # interest over that target's pool, which needs the two files joined.
    pool_by_pair = {
        (r["regime"], r["target"]): float(r["dense_pool"]) for r in per_target
    }
    emitted = [f(r, "emitted_after_floor") for r in per_interest]
    emitted_union = [f(r, "emitted_after_floor_union") for r in per_interest]
    survival = [
        f(r, "emitted_after_floor") / pool_by_pair[(r["regime"], r["target"])]
        for r in per_interest
        if pool_by_pair.get((r["regime"], r["target"]))
    ]
    surfaced = [float(r["a1_surfaced"]) for r in per_target]
    max_surface = 250
    out["q018"] = {
        "dense_pool_median": statistics.median(pool_by_pair.values()),
        "dense_pool_min": min(pool_by_pair.values()),
        "dense_pool_max": max(pool_by_pair.values()),
        "emitted_after_floor_median": statistics.median(emitted),
        "emitted_after_floor_p10": sorted(emitted)[len(emitted) // 10],
        "emitted_after_floor_p90": sorted(emitted)[(len(emitted) * 9) // 10],
        "emitted_after_floor_union_median": statistics.median(emitted_union),
        "floor_survival_of_pool_median": statistics.median(survival),
        "surfaced_median": statistics.median(surfaced),
        "surfaced_max": max(surfaced),
        "pairs_hitting_max_surface": sum(1 for v in surfaced if v >= max_surface),
        "pairs": len(surfaced),
        # `Q-012` is a paper-feed question, so the deployed paper regime is
        # broken out rather than left inside the pooled count.
        "r1_surfaced_median": statistics.median(
            [float(r["a1_surfaced"]) for r in per_target if r["regime"].startswith("R1:")]
        ),
        "r1_pairs_hitting_max_surface": sum(
            1
            for r in per_target
            if r["regime"].startswith("R1:") and float(r["a1_surfaced"]) >= max_surface
        ),
        "r1_pairs": sum(1 for r in per_target if r["regime"].startswith("R1:")),
        "pool_growth_median": statistics.median([
            float(r["a2p_union_prod__pool"]) / float(r["dense_pool"])
            for r in per_target
        ]),
        "novel_share_median": statistics.median([
            float(r["a2p_union_prod__novel"]) / float(r["a2p_union_prod__pool"])
            for r in per_target
        ]),
    }
    q = out["q018"]
    lines += [
        "",
        "### 4. `Q-018` companion — where the cut actually falls",
        "",
        "| Quantity | value |",
        "|---|---:|",
        (
            f"| dense pool per target (median) | {q['dense_pool_median']:.0f} "
            f"(min {q['dense_pool_min']:.0f}, max {q['dense_pool_max']:.0f}) |"
        ),
        (
            f"| candidates emitted per interest after the 0.15 floor (median) | "
            f"{q['emitted_after_floor_median']:.0f} "
            f"(p10 {q['emitted_after_floor_p10']:.0f}, "
            f"p90 {q['emitted_after_floor_p90']:.0f}) |"
        ),
        (
            f"| share of the target's pool surviving one interest's floor (median) | "
            f"{q['floor_survival_of_pool_median']:.0%} |"
        ),
        (
            f"| surfaced per target after the cosine threshold (median) | "
            f"{q['surfaced_median']:.0f} (max {q['surfaced_max']:.0f}) |"
        ),
        (
            f"| (regime, target) pairs hitting the 250 backstop | "
            f"{q['pairs_hitting_max_surface']}/{q['pairs']} |"
        ),
        (
            "| — of which in the deployed paper feed (R1) | "
            f"{q['r1_pairs_hitting_max_surface']}/{q['r1_pairs']} "
            f"(median surfaced {q['r1_surfaced_median']:.0f}) |"
        ),
        (
            f"| pool growth, union over dense (median) | "
            f"{q['pool_growth_median']:.2f}× |"
        ),
        (
            f"| share of the union pool the dense channel never saw (median) | "
            f"{q['novel_share_median']:.0%} |"
        ),
    ]

    # ---------------------------------------------------------------- FTS
    total = len(per_interest)
    empty = sum(1 for r in per_interest if int(r["fts_hits"]) == 0)
    empty_or = sum(1 for r in per_interest if int(r["fts_or_hits"]) == 0)
    out["fts"] = {
        "interest_queries": total,
        "websearch_returning_nothing": empty,
        "websearch_empty_share": empty / total,
        "or_returning_nothing": empty_or,
    }
    lines += [
        "",
        "### 5. The Postgres FTS channel `/api/search/` already runs",
        "",
        (
            f"- `websearch` (production syntax): **{empty} of {total}** "
            f"({empty / total:.0%}) interest queries return **nothing at all**. "
            "`websearch` ANDs unquoted terms, and a declared interest carries the "
            "profile's shared keyword suffix, so every term has to appear in one "
            "document."
        ),
        (
            f"- Same index, OR semantics: {empty_or} of {total} return nothing, "
            "and median reachability is "
            f"{statistics.median(reach(per_interest, 'fts_or_reachability')):.3f}."
        ),
    ]

    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "analysis.md").write_text("\n".join(lines) + "\n")
    (EXP_DIR / "data" / "analysis.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Derive the slate comparison from the harness's run records.

    uv run --project scripts/research \
      docs/research/experiments/EXP-2026-08-004-.../data/build_metrics.py

Reads the `flat_profile` / `clustered_profile` / `slate_profile` results in
`eval/results/`, pairs them profile by profile within each (condition, grouping)
cell, and computes the paired bootstrap intervals `PROTOCOL.md` pre-registered.
Two arm pairs per cell: `slate − clustered` (does the slate add anything to the
cluster path?) and `slate − flat` (is the lab feed better than no clusters?).

Nothing here scores anything — the harness computed the metrics at run time; this
pairs and resamples them. No number is written by hand.
"""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
RESULTS = REPO / "eval" / "results"
RUNS = REPO / "eval" / "runs"

ARMS = ("flat_profile", "clustered_profile", "slate_profile")
#: The two comparisons the question asks for, as (treatment, baseline).
PAIRS = (("slate_profile", "clustered_profile"), ("slate_profile", "flat_profile"))
COLLECTION = "sci-2026-train"

#: `prod` is production surfacing; `cut30` is the stress condition where the cut
#: binds; `cut34` gives the slate-free arms the slate's own mean surfaced size, so
#: falsifier 3 ("the gain is bought, not earned") can be answered at matched set
#: size. Conditions are never mixed or averaged.
CONDITIONS = {(250, 0.5): "prod", (30, None): "cut30", (34, None): "cut34"}

MEASURES = (
    "min_cluster_recall@10",
    "cluster_coverage@10",
    "cluster_gini@10",
    "min_cluster_recall@30",
    "cluster_coverage@30",
    "cluster_gini@30",
    "min_cluster_recall@1000",
    "cluster_coverage@1000",
    "cluster_gini@1000",
    "min_cluster_recall@100",
    "cluster_coverage@100",
    "nDCG@10",
    "R@100",
)
PRIMARY = "min_cluster_recall@10"
CO_PRIMARY = "cluster_coverage@30"
#: Whole-set coverage. The slate's additions sort to the bottom by `final_score`,
#: so no top-k at or below the global cut can observe them; this is the only depth
#: at which the mechanism is visible. See ISSUES.md.
WHOLE_SET = "cluster_coverage@1000"
LOWER_IS_BETTER = {"cluster_gini@10", "cluster_gini@30", "cluster_gini@1000"}

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260809

COLUMNS = [
    "condition",
    "grouping",
    "comparison",
    "measure",
    "n_profiles",
    "baseline_mean",
    "treatment_mean",
    "delta",
    "delta_std",
    "ci_low",
    "ci_high",
    "delta_pct",
    "lower_is_better",
]


def condition_of(params: dict) -> str | None:
    key = (int(params.get("surface_limit", 0)), params.get("match_threshold"))
    threshold = None if key[1] is None else float(key[1])
    return CONDITIONS.get((key[0], threshold))


def load_records() -> dict[tuple[str, str, str], dict]:
    """`(arm, condition, grouping) -> record`, newest timestamp wins."""
    out: dict[tuple[str, str, str], dict] = {}
    for path in sorted(RESULTS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        params = record.get("params", {})
        if record.get("arm") not in ARMS or record.get("collection") != COLLECTION:
            continue
        condition = condition_of(params)
        if condition is None:
            continue  # an EXP-2026-08-003 run: different surfacing, not this grid
        key = (record["arm"], condition, params.get("grouping"))
        previous = out.get(key)
        if previous is None or record["timestamp"] >= previous["timestamp"]:
            out[key] = record
    return out


def paired_bootstrap(
    baseline: np.ndarray, treatment: np.ndarray
) -> tuple[float, float, float, float]:
    """Mean paired delta, its 95% percentile CI, and the per-profile std."""
    deltas = treatment - baseline
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(deltas)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    draws = rng.integers(0, n, size=(BOOTSTRAP_RESAMPLES, n))
    means = deltas[draws].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(deltas.mean()), float(low), float(high), float(deltas.std(ddof=1))


#: Surface limit per condition, for locating that condition's run file.
CONDITION_LIMIT = {"prod": 250, "cut30": 30, "cut34": 34}


def read_run(arm: str, condition: str, grouping: str) -> dict[str, list[str]]:
    limit = CONDITION_LIMIT[condition]
    matches = sorted(RUNS.glob(f"*__{arm}__{grouping}__beta0.15__s{limit}__*.txt.gz"))
    if not matches:
        return {}
    ranking: dict[str, list[str]] = {}
    with gzip.open(matches[-1], "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 3:
                ranking.setdefault(parts[0], []).append(parts[2])
    return ranking


def identical_share(condition: str, grouping: str) -> float | None:
    """Falsifier 4: are slate and clustered producing the same list outright?

    Compares whole surfaced sets, not a top-k — a top-k cannot see the slate's
    additions, so comparing one would report a spurious 100%.
    """
    slate = read_run("slate_profile", condition, grouping)
    clustered = read_run("clustered_profile", condition, grouping)
    shared = set(slate) & set(clustered)
    if not shared:
        return None
    same = sum(1 for pid in shared if set(slate[pid]) == set(clustered[pid]))
    return same / len(shared)


def surfacing_rows(records: dict) -> list[dict]:
    """Mandatory context: a slate buys coverage by surfacing more items."""
    rows = []
    for (arm, condition, grouping), record in sorted(records.items()):
        stats = (record.get("diagnostics") or {}).get("surfacing") or {}
        if not stats:
            continue
        rows.append({"arm": arm, "condition": condition, "grouping": grouping, **stats})
    return rows


def comparison_table(rows: list[dict]) -> str:
    lines = [
        "| Condition | Grouping | Comparison | Measure | baseline | treatment | "
        "Δ | 95% CI |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        if row["measure"] not in (PRIMARY, CO_PRIMARY, WHOLE_SET, "nDCG@10"):
            continue
        spans = row["ci_low"] <= 0.0 <= row["ci_high"]
        mark = "" if spans else "**"
        lines.append(
            f"| `{row['condition']}` | `{row['grouping']}` | `{row['comparison']}` | "
            f"`{row['measure']}` | {row['baseline_mean']:.4f} | "
            f"{row['treatment_mean']:.4f} | {mark}{row['delta']:+.4f}{mark} | "
            f"[{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]"
            f"{' — spans 0' if spans else ''} |"
        )
    return "\n".join(lines)


def surfacing_table(rows: list[dict]) -> str:
    lines = [
        "| Condition | Arm | Grouping | mean surfaced | max surfaced | mean pool |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda r: (r["condition"], r["arm"], r["grouping"])):
        lines.append(
            f"| `{row['condition']}` | `{row['arm']}` | `{row['grouping']}` | "
            f"{row['mean_surfaced']:.2f} | {row['max_surfaced']:.0f} | "
            f"{row['mean_pool']:.1f} |"
        )
    return "\n".join(lines)


def inject(marker: str, table: str, target: Path, fragment: Path) -> None:
    fragment.parent.mkdir(exist_ok=True)
    fragment.write_text(table + "\n", encoding="utf-8")
    if not target.is_file():
        return
    text = target.read_text(encoding="utf-8")
    begin, end = f"<!-- BEGIN {marker} -->", f"<!-- END {marker} -->"
    if begin not in text or end not in text:
        return
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    target.write_text(f"{head}{begin}\n\n{table}\n\n{end}{tail}", encoding="utf-8")


def main() -> None:
    records = load_records()
    if not records:
        raise SystemExit(f"no slate-grid results found in {RESULTS}")

    cells = sorted({(cond, group) for _arm, cond, group in records})
    rows: list[dict] = []
    identical: dict[str, float] = {}

    for condition, grouping in cells:
        share = identical_share(condition, grouping)
        if share is not None:
            identical[f"{condition}/{grouping}"] = round(share, 4)

        for treatment_arm, baseline_arm in PAIRS:
            treatment = records.get((treatment_arm, condition, grouping))
            baseline = records.get((baseline_arm, condition, grouping))
            if not treatment or not baseline:
                continue
            profiles = sorted(
                set(treatment["per_query"]) & set(baseline["per_query"])
            )
            for measure in MEASURES:
                if measure not in treatment["per_query"].get(profiles[0], {}):
                    continue
                base = np.array(
                    [baseline["per_query"][p].get(measure, 0.0) for p in profiles]
                )
                treat = np.array(
                    [treatment["per_query"][p].get(measure, 0.0) for p in profiles]
                )
                delta, low, high, std = paired_bootstrap(base, treat)
                mean_base = float(base.mean())
                rows.append(
                    {
                        "condition": condition,
                        "grouping": grouping,
                        "comparison": f"{treatment_arm[:-8]}−{baseline_arm[:-8]}",
                        "measure": measure,
                        "n_profiles": len(profiles),
                        "baseline_mean": round(mean_base, 6),
                        "treatment_mean": round(float(treat.mean()), 6),
                        "delta": round(delta, 6),
                        "delta_std": round(std, 6),
                        "ci_low": round(low, 6),
                        "ci_high": round(high, 6),
                        "delta_pct": (
                            round(100 * delta / mean_base, 2) if mean_base else ""
                        ),
                        "lower_is_better": measure in LOWER_IS_BETTER,
                    }
                )

    # --- the size-matched comparison (falsifier 3) --------------------------
    # The slate runs at a 30-item cut and surfaces ~33.8; the `cut34` arms run at
    # a 34-item cut and surface 34. Pairing across those two conditions is the
    # only way to ask whether the slate's coverage gain survives once the
    # slate-free arms are allowed the same number of slots. It is labelled
    # `matched` so it can never be confused with a within-condition row.
    for grouping in sorted({g for _a, _c, g in records}):
        slate = records.get(("slate_profile", "cut30", grouping))
        for baseline_arm in ("clustered_profile", "flat_profile"):
            baseline = records.get((baseline_arm, "cut34", grouping))
            if not slate or not baseline:
                continue
            profiles = sorted(set(slate["per_query"]) & set(baseline["per_query"]))
            for measure in MEASURES:
                if measure not in slate["per_query"].get(profiles[0], {}):
                    continue
                base = np.array(
                    [baseline["per_query"][p].get(measure, 0.0) for p in profiles]
                )
                treat = np.array(
                    [slate["per_query"][p].get(measure, 0.0) for p in profiles]
                )
                delta, low, high, std = paired_bootstrap(base, treat)
                mean_base = float(base.mean())
                rows.append(
                    {
                        "condition": "matched",
                        "grouping": grouping,
                        "comparison": f"slate−{baseline_arm[:-8]}@34",
                        "measure": measure,
                        "n_profiles": len(profiles),
                        "baseline_mean": round(mean_base, 6),
                        "treatment_mean": round(float(treat.mean()), 6),
                        "delta": round(delta, 6),
                        "delta_std": round(std, 6),
                        "ci_low": round(low, 6),
                        "ci_high": round(high, 6),
                        "delta_pct": (
                            round(100 * delta / mean_base, 2) if mean_base else ""
                        ),
                        "lower_is_better": measure in LOWER_IS_BETTER,
                    }
                )

    with (HERE / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    surfacing = surfacing_rows(records)
    with (HERE / "surfacing.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "condition", "arm", "grouping",
                "mean_surfaced", "median_surfaced", "max_surfaced", "mean_pool",
            ],
        )
        writer.writeheader()
        writer.writerows(surfacing)

    def cell(condition, grouping, comparison, measure):
        for row in rows:
            if (
                row["condition"] == condition
                and row["grouping"] == grouping
                and row["comparison"] == comparison
                and row["measure"] == measure
            ):
                return row
        return None

    payload = {
        "experiment": "EXP-2026-08-004",
        "generated_from": "eval/results/*.json (flat/clustered/slate profile arms)",
        "primary": PRIMARY,
        "co_primary": CO_PRIMARY,
        "whole_set_measure": WHOLE_SET,
        "note": (
            "Paired over the same 30 synthetic profiles per grouping mode as "
            "EXP-2026-08-003. Judgments are the union of each profile's "
            "constituent LongEval-Sci queries' dctr qrels — click-derived "
            "pseudo-relevance, not human assessment. `prod` and `cut30` rows "
            "describe different surfacing conditions and are never averaged."
        ),
        "statistical_test": (
            f"paired bootstrap over profiles, {BOOTSTRAP_RESAMPLES} resamples, "
            f"seed {BOOTSTRAP_SEED}, 95% percentile interval"
        ),
        "headline": {
            f"{condition}/{grouping}": {
                measure: {
                    "delta": found["delta"],
                    "delta_std": found["delta_std"],
                    "ci": [found["ci_low"], found["ci_high"]],
                    "spans_zero": found["ci_low"] <= 0.0 <= found["ci_high"],
                }
                for measure in (PRIMARY, CO_PRIMARY, WHOLE_SET, "nDCG@10")
                if (found := cell(condition, grouping, "slate−clustered", measure))
            }
            for condition, grouping in cells
        },
        "identical_surfaced_set_share": identical,
        "surfacing": surfacing,
        "rows": rows,
    }
    (HERE / "metrics.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    parent = HERE.parent
    inject(
        "GENERATED TABLE",
        comparison_table(rows),
        parent / "RESULTS.md",
        parent / "tables" / "slate-comparison.md",
    )
    inject(
        "GENERATED SURFACING",
        surfacing_table(surfacing),
        parent / "RESULTS.md",
        parent / "tables" / "surfacing.md",
    )
    print(f"Wrote metrics.csv, surfacing.csv, metrics.json, tables/ ({len(rows)} rows)")


if __name__ == "__main__":
    main()

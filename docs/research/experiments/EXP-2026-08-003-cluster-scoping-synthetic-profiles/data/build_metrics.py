"""Derive this experiment's paired comparison from the harness's run records.

    uv run --project scripts/research \
      docs/research/experiments/EXP-2026-08-003-.../data/build_metrics.py

Reads every `flat_profile` / `clustered_profile` result in `eval/results/`, pairs
them profile by profile within each (grouping, β) cell, and computes the paired
bootstrap confidence intervals `PROTOCOL.md` pre-registered. Nothing here scores
anything — the metrics were computed at run time by the harness; this only pairs
and resamples them.

Writes `metrics.csv`, `metrics.json`, and the two generated table fragments the
`RESULTS.md` and `ISSUES.md` markers pull in. No number is written by hand.
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

ARMS = ("flat_profile", "clustered_profile")
COLLECTION = "sci-2026-train"

#: Reported for every cell. `min_cluster_recall@10` is the primary — it is what
#: C-003 claims — and `cluster_gini` is the one metric where lower is better.
MEASURES = (
    "min_cluster_recall@10",
    "cluster_coverage@10",
    "cluster_gini@10",
    "min_cluster_recall@100",
    "cluster_coverage@100",
    "cluster_gini@100",
    "nDCG@10",
    "R@100",
)
PRIMARY = "min_cluster_recall@10"
LOWER_IS_BETTER = {"cluster_gini@10", "cluster_gini@100"}

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260809

COLUMNS = [
    "grouping",
    "beta",
    "measure",
    "n_profiles",
    "flat_mean",
    "clustered_mean",
    "delta",
    "delta_std",
    "ci_low",
    "ci_high",
    "delta_pct",
    "lower_is_better",
]


def load_records() -> dict[tuple[str, str, float], dict]:
    """`(arm, grouping, beta) -> result record`, newest commit wins on collision."""
    out: dict[tuple[str, str, float], dict] = {}
    for path in sorted(RESULTS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("arm") not in ARMS or record.get("collection") != COLLECTION:
            continue
        params = record.get("params", {})
        key = (record["arm"], params.get("grouping"), float(params.get("beta")))
        previous = out.get(key)
        if previous is None or record["timestamp"] >= previous["timestamp"]:
            out[key] = record
    return out


def paired_bootstrap(
    flat: np.ndarray, clustered: np.ndarray
) -> tuple[float, float, float, float]:
    """Mean paired delta and its 95% percentile CI, resampling profiles.

    Profiles are the unit of resampling because they are the unit of pairing: the
    same 30 profiles go through both arms, so the delta is defined per profile and
    the uncertainty is over which profiles we happened to construct.
    """
    deltas = clustered - flat
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(deltas)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    draws = rng.integers(0, n, size=(BOOTSTRAP_RESAMPLES, n))
    means = deltas[draws].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    # `ddof=1`: the 30 profiles are a sample of the profiles we could have
    # constructed, not the population, and this std is what `manifest.yaml`
    # reports next to each mean.
    return float(deltas.mean()), float(low), float(high), float(deltas.std(ddof=1))


def read_run(arm: str, grouping: str, beta: float) -> dict[str, list[str]]:
    """`profile_id -> ranked doc ids` from the arm's TREC run file, if present."""
    pattern = f"*__{arm}__{grouping}__beta{beta}__*.txt.gz"
    matches = sorted(RUNS.glob(pattern))
    if not matches:
        return {}
    ranking: dict[str, list[str]] = {}
    with gzip.open(matches[-1], "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 3:
                ranking.setdefault(parts[0], []).append(parts[2])
    return ranking


def identical_ranking_share(
    grouping: str, beta: float, depth: int = 10
) -> float | None:
    """Share of profiles whose top-``depth`` is identical under both arms.

    Falsifier 4 in `PROTOCOL.md`: above 90% the construction is degenerate and the
    comparison is measuring nothing.
    """
    flat = read_run("flat_profile", grouping, beta)
    clustered = read_run("clustered_profile", grouping, beta)
    shared = set(flat) & set(clustered)
    if not shared:
        return None
    same = sum(
        1 for pid in shared if flat[pid][:depth] == clustered[pid][:depth]
    )
    return same / len(shared)


def markdown_table(rows: list[dict]) -> str:
    lines = [
        "| Grouping | β | Measure | flat | clustered | Δ (clustered − flat) | "
        "95% CI |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for row in rows:
        if row["measure"] not in (PRIMARY, "cluster_gini@10", "nDCG@10"):
            continue
        crosses_zero = row["ci_low"] <= 0.0 <= row["ci_high"]
        delta = f"{row['delta']:+.4f}"
        lines.append(
            f"| `{row['grouping']}` | {row['beta']} | `{row['measure']}` | "
            f"{row['flat_mean']:.4f} | {row['clustered_mean']:.4f} | "
            f"{'' if crosses_zero else '**'}{delta}{'' if crosses_zero else '**'} | "
            f"[{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]"
            f"{' — spans 0' if crosses_zero else ''} |"
        )
    return "\n".join(lines)


def diagnostics_table(records: dict) -> str:
    """The abstention-floor instrumentation, for `ISSUES.md`.

    How many interests (flat) or clusters (clustered) each surfaced candidate
    cleared. If almost every candidate clears exactly one, the two arms agree
    trivially and the experiment measures nothing.
    """
    lines = [
        "| Arm | Grouping | β | Cleared 1 | Cleared 2 | Cleared 3 | "
        "Share clearing ≥ 2 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for (arm, grouping, beta), record in sorted(records.items()):
        diag = record.get("diagnostics") or {}
        histogram = next(iter(diag.values()), {})
        if not histogram:
            continue
        counts = {int(k): v for k, v in histogram.items()}
        total = sum(counts.values())
        multi = sum(v for k, v in counts.items() if k >= 2)
        lines.append(
            f"| `{arm}` | `{grouping}` | {beta} | {counts.get(1, 0)} | "
            f"{counts.get(2, 0)} | {counts.get(3, 0)} | "
            f"{multi / total:.1%} |"
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
        raise SystemExit(f"no profile-arm results found in {RESULTS}")

    cells = sorted({(grouping, beta) for _arm, grouping, beta in records})
    rows: list[dict] = []
    degenerate: dict[str, float] = {}

    for grouping, beta in cells:
        flat = records.get(("flat_profile", grouping, beta))
        clustered = records.get(("clustered_profile", grouping, beta))
        if not flat or not clustered:
            continue
        profiles = sorted(set(flat["per_query"]) & set(clustered["per_query"]))
        share = identical_ranking_share(grouping, beta)
        if share is not None:
            degenerate[f"{grouping}@beta{beta}"] = round(share, 4)

        for measure in MEASURES:
            flat_values = np.array(
                [flat["per_query"][pid].get(measure, 0.0) for pid in profiles]
            )
            clustered_values = np.array(
                [clustered["per_query"][pid].get(measure, 0.0) for pid in profiles]
            )
            delta, low, high, std = paired_bootstrap(
                flat_values, clustered_values
            )
            base = float(flat_values.mean())
            rows.append(
                {
                    "grouping": grouping,
                    "beta": beta,
                    "measure": measure,
                    "n_profiles": len(profiles),
                    "flat_mean": round(base, 6),
                    "clustered_mean": round(float(clustered_values.mean()), 6),
                    "delta": round(delta, 6),
                    "delta_std": round(std, 6),
                    "ci_low": round(low, 6),
                    "ci_high": round(high, 6),
                    "delta_pct": round(100 * delta / base, 2) if base else "",
                    "lower_is_better": measure in LOWER_IS_BETTER,
                }
            )

    with (HERE / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    def cell(grouping: str, beta: float, measure: str) -> dict | None:
        for row in rows:
            if (
                row["grouping"] == grouping
                and row["beta"] == beta
                and row["measure"] == measure
            ):
                return row
        return None

    payload = {
        "experiment": "EXP-2026-08-003",
        "generated_from": "eval/results/*.json (flat_profile, clustered_profile)",
        "primary": PRIMARY,
        "note": (
            "Paired over synthetic profiles within each (grouping, beta) cell. "
            "Judgments are the union of each profile's constituent LongEval-Sci "
            "queries' dctr qrels — click-model-derived pseudo-relevance, not "
            "human assessment. Corpus scope is `full` throughout; nothing is "
            "compared across scopes."
        ),
        "statistical_test": (
            f"paired bootstrap over profiles, {BOOTSTRAP_RESAMPLES} resamples, "
            f"seed {BOOTSTRAP_SEED}, 95% percentile interval"
        ),
        "headline": {
            f"{grouping}@beta{beta}": {
                measure: {
                    "delta": found["delta"],
                    "delta_std": found["delta_std"],
                    "ci": [found["ci_low"], found["ci_high"]],
                    "spans_zero": found["ci_low"] <= 0.0 <= found["ci_high"],
                }
                for measure in (PRIMARY, "cluster_gini@10", "nDCG@10")
                if (found := cell(grouping, beta, measure))
            }
            for grouping, beta in cells
        },
        "identical_top10_share": degenerate,
        "rows": rows,
    }
    (HERE / "metrics.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    parent = HERE.parent
    inject(
        "GENERATED TABLE",
        markdown_table(rows),
        parent / "RESULTS.md",
        parent / "tables" / "cluster-comparison.md",
    )
    inject(
        "GENERATED DIAGNOSTICS",
        diagnostics_table(records),
        parent / "ISSUES.md",
        parent / "tables" / "floor-diagnostics.md",
    )
    print(f"Wrote metrics.csv, metrics.json, tables/ ({len(rows)} rows)")


if __name__ == "__main__":
    main()

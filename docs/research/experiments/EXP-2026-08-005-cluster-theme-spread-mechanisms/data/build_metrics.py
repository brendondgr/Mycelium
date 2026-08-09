"""Derive the theme-spread comparison from the harness's run records.

    uv run --project scripts/research \
      docs/research/experiments/EXP-2026-08-005-.../data/build_metrics.py

Reads every `spreadexp_*` result in `eval/results/`, pairs each spread arm against
the `clustered_profile` baseline profile by profile within a grouping, and
computes the paired bootstrap intervals `PROTOCOL.md` pre-registered.

Nothing here scores anything — the harness computed the metrics at run time; this
pairs and resamples them. No number is written by hand, and the pre-registered
decision rule is evaluated in code rather than by eye.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
RESULTS = REPO / "eval" / "results"

BASELINE = "clustered_profile"
#: Reference arm, not a mechanism: EXP-2026-08-003 found no clusters at all
#: already beats the clustered ranking on theme coverage.
REFERENCE = "flat_profile"

INDIVIDUAL = (
    "spread_identity",
    "spread_interleave",
    "spread_quota",
    "spread_cap",
    "spread_mmr",
    "spread_rankmerge",
    "spread_floor",
)
COMBINED = (
    "spread_rankmerge_interleave",
    "spread_rankmerge_quota",
    "spread_rankmerge_cap",
    "spread_rankmerge_mmr",
    "spread_floor_interleave",
    "spread_all",
)
TREATMENTS = (REFERENCE, *INDIVIDUAL, *COMBINED)
ARMS = (BASELINE, *TREATMENTS)

COLLECTION = "sci-2026-train"
#: The single condition this experiment runs: deployed paper-feed surfacing.
CONDITION = (250, 0.5)

MEASURES = (
    "min_cluster_recall@10",
    "cluster_coverage@10",
    "cluster_gini@10",
    "min_cluster_recall@30",
    "cluster_coverage@30",
    "cluster_gini@30",
    "min_cluster_recall@100",
    "cluster_coverage@100",
    "cluster_gini@100",
    "nDCG@10",
    "nDCG@100",
    "AP",
    "R@100",
)
PRIMARY = "min_cluster_recall@10"
GUARDRAIL = "nDCG@10"
#: The pre-registered relevance budget: a mechanism may cost nDCG@10, but its
#: confidence interval may not sit below this.
GUARDRAIL_FLOOR = -0.01
#: The target condition; `random` is the negative control for falsifier 1.
TARGET_GROUPING = "imbalanced"
CONTROL_GROUPING = "random"

LOWER_IS_BETTER = {"cluster_gini@10", "cluster_gini@30", "cluster_gini@100"}

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260809

#: Every arm is compared against both. `clustered_profile` is the pre-registered
#: decision baseline — it is the deployed ranking, and the decision rule is
#: stated against it. `flat_profile` is the second bar `PROTOCOL.md` §Baselines
#: names: no clusters at all. If a mechanism beats the cluster path but not the
#: no-cluster path, it has fixed something that clustering caused and gained
#: nothing over never having clustered.
BASELINES = (BASELINE, REFERENCE)

COLUMNS = [
    "grouping",
    "baseline",
    "arm",
    "family",
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
    "significant",
]


def family_of(arm: str) -> str:
    if arm == REFERENCE:
        return "reference"
    if arm == "spread_identity":
        return "null"
    return "individual" if arm in INDIVIDUAL else "combined"


def load_records() -> dict[tuple[str, str], dict]:
    """`(arm, grouping) -> record`, newest timestamp wins.

    Filters on the surfacing condition as well as the arm name, so an
    EXP-2026-08-003 or -004 run of the same arm at a different cut can never be
    silently folded into this grid.
    """
    out: dict[tuple[str, str], dict] = {}
    for path in sorted(RESULTS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        params = record.get("params", {})
        if record.get("arm") not in ARMS or record.get("collection") != COLLECTION:
            continue
        threshold = params.get("match_threshold")
        key = (
            int(params.get("surface_limit", 0)),
            None if threshold is None else float(threshold),
        )
        if key != CONDITION:
            continue
        cell = (record["arm"], params.get("grouping"))
        previous = out.get(cell)
        if previous is None or record["timestamp"] >= previous["timestamp"]:
            out[cell] = record
    return out


def paired_bootstrap(
    baseline: np.ndarray, treatment: np.ndarray
) -> tuple[float, float, float, float]:
    """Mean paired delta, its 95% percentile CI, and the per-profile std."""
    deltas = treatment - baseline
    n = len(deltas)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.integers(0, n, size=(BOOTSTRAP_RESAMPLES, n))
    means = deltas[draws].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(deltas.mean()), float(low), float(high), float(deltas.std(ddof=1))


def identity_drift(records: dict) -> dict[str, float]:
    """Falsifier 4, as a number rather than an assertion.

    The largest absolute per-profile difference between the null spread policy and
    the untouched baseline, over every measure. Anything but 0.0 means the spread
    code path — not a mechanism — is moving the numbers, and the experiment is
    void. Reported per grouping so a partial failure cannot hide in an average.
    """
    drift: dict[str, float] = {}
    for (arm, grouping), record in records.items():
        if arm != "spread_identity":
            continue
        baseline = records.get((BASELINE, grouping))
        if not baseline:
            continue
        worst = 0.0
        for profile, values in record["per_query"].items():
            reference = baseline["per_query"].get(profile, {})
            for measure in MEASURES:
                if measure in values and measure in reference:
                    worst = max(worst, abs(values[measure] - reference[measure]))
        drift[grouping] = round(worst, 9)
    return drift


def surfacing_rows(records: dict) -> list[dict]:
    """Falsifier 2: a coverage gain bought with extra slots is not a gain."""
    rows = []
    for (arm, grouping), record in sorted(records.items()):
        stats = (record.get("diagnostics") or {}).get("surfacing") or {}
        if stats:
            rows.append({"arm": arm, "grouping": grouping, **stats})
    return rows


def verdicts(rows: list[dict]) -> list[dict]:
    """The pre-registered decision rule, applied in code.

    A mechanism helps iff, on the target grouping, the primary metric's delta is
    positive with a CI excluding zero **and** the relevance guardrail's CI lower
    bound clears the budget. Falsifier 1 is reported alongside but deliberately
    not folded into the verdict: `random` and `imbalanced` are different profile
    sets, so there is no paired test for the difference of their deltas, and
    inventing one would be worse than reporting both and saying so.
    """

    def find(grouping, arm, measure, baseline=BASELINE):
        for row in rows:
            if (
                row["grouping"] == grouping
                and row["baseline"] == baseline
                and row["arm"] == arm
                and row["measure"] == measure
            ):
                return row
        return None

    out = []
    for arm in TREATMENTS:
        primary = find(TARGET_GROUPING, arm, PRIMARY)
        guard = find(TARGET_GROUPING, arm, GUARDRAIL)
        control = find(CONTROL_GROUPING, arm, PRIMARY)
        # The second bar: does the mechanism beat having no clusters at all?
        vs_flat = find(TARGET_GROUPING, arm, PRIMARY, baseline=REFERENCE)
        if primary is None or guard is None:
            continue
        primary_wins = primary["delta"] > 0 and primary["ci_low"] > 0
        guard_holds = guard["ci_low"] > GUARDRAIL_FLOOR
        control_also_moves = bool(control and control["ci_low"] > 0)
        out.append(
            {
                "arm": arm,
                "family": family_of(arm),
                "primary_delta": primary["delta"],
                "primary_ci": [primary["ci_low"], primary["ci_high"]],
                "guardrail_delta": guard["delta"],
                "guardrail_ci": [guard["ci_low"], guard["ci_high"]],
                "control_delta": control["delta"] if control else None,
                "control_significant": control_also_moves,
                "vs_flat_delta": vs_flat["delta"] if vs_flat else None,
                "vs_flat_ci": (
                    [vs_flat["ci_low"], vs_flat["ci_high"]] if vs_flat else None
                ),
                "beats_flat": bool(vs_flat and vs_flat["ci_low"] > 0),
                "helps": bool(primary_wins and guard_holds),
                "fails_on": (
                    []
                    if primary_wins and guard_holds
                    else (
                        ([] if primary_wins else ["primary"])
                        + ([] if guard_holds else ["guardrail"])
                    )
                ),
            }
        )
    return out


def verdict_table(verdict_rows: list[dict]) -> str:
    lines = [
        f"| Arm | Δ`{PRIMARY}` | 95% CI | Δ`{GUARDRAIL}` | 95% CI | Δ primary on "
        "`random` | Δ primary vs `flat` | Helps? |",
        "|---|---:|---|---:|---|---:|---:|---|",
    ]
    for row in verdict_rows:
        control = (
            "—" if row["control_delta"] is None else f"{row['control_delta']:+.4f}"
        )
        if row["control_significant"]:
            control += " *(also moves)*"
        flat = "—" if row["vs_flat_delta"] is None else f"{row['vs_flat_delta']:+.4f}"
        if row["beats_flat"]:
            flat = f"**{flat}**"
        verdict = "**yes**" if row["helps"] else f"no ({', '.join(row['fails_on'])})"
        lines.append(
            f"| `{row['arm']}` | {row['primary_delta']:+.4f} | "
            f"[{row['primary_ci'][0]:+.4f}, {row['primary_ci'][1]:+.4f}] | "
            f"{row['guardrail_delta']:+.4f} | "
            f"[{row['guardrail_ci'][0]:+.4f}, {row['guardrail_ci'][1]:+.4f}] | "
            f"{control} | {flat} | {verdict} |"
        )
    return "\n".join(lines)


def coverage_table(rows: list[dict]) -> str:
    """The full coverage picture on the target grouping, mechanism by mechanism."""
    shown = ("min_cluster_recall@10", "cluster_coverage@10", "cluster_gini@10")
    lines = [
        "| Arm | Measure | baseline | treatment | Δ | 95% CI |",
        "|---|---|---:|---:|---:|---|",
    ]
    for arm in TREATMENTS:
        for measure in shown:
            for row in rows:
                if (
                    row["grouping"] == TARGET_GROUPING
                    and row["baseline"] == BASELINE
                    and row["arm"] == arm
                    and row["measure"] == measure
                ):
                    spans = row["ci_low"] <= 0.0 <= row["ci_high"]
                    mark = "" if spans else "**"
                    better = " (lower is better)" if row["lower_is_better"] else ""
                    lines.append(
                        f"| `{arm}` | `{measure}`{better} | "
                        f"{row['baseline_mean']:.4f} | {row['treatment_mean']:.4f} | "
                        f"{mark}{row['delta']:+.4f}{mark} | "
                        f"[{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]"
                        f"{' — spans 0' if spans else ''} |"
                    )
    return "\n".join(lines)


def surfacing_table(rows: list[dict]) -> str:
    lines = [
        "| Arm | Grouping | mean surfaced | max surfaced | mean pool |",
        "|---|---|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda r: (r["arm"], r["grouping"])):
        lines.append(
            f"| `{row['arm']}` | `{row['grouping']}` | {row['mean_surfaced']:.2f} | "
            f"{row['max_surfaced']:.0f} | {row['mean_pool']:.1f} |"
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


def compare(
    baseline_record: dict, treatment_record: dict, *, grouping: str, baseline: str,
    arm: str,
) -> list[dict]:
    """One (baseline, arm, grouping) cell: every measure, paired and resampled."""
    profiles = sorted(
        set(treatment_record["per_query"]) & set(baseline_record["per_query"])
    )
    if not profiles:
        return []
    out = []
    for measure in MEASURES:
        if measure not in treatment_record["per_query"][profiles[0]]:
            continue
        base = np.array(
            [baseline_record["per_query"][p].get(measure, 0.0) for p in profiles]
        )
        treat = np.array(
            [treatment_record["per_query"][p].get(measure, 0.0) for p in profiles]
        )
        delta, low, high, std = paired_bootstrap(base, treat)
        mean_base = float(base.mean())
        out.append(
            {
                "grouping": grouping,
                "baseline": baseline,
                "arm": arm,
                "family": family_of(arm),
                "measure": measure,
                "n_profiles": len(profiles),
                "baseline_mean": round(mean_base, 6),
                "treatment_mean": round(float(treat.mean()), 6),
                "delta": round(delta, 6),
                "delta_std": round(std, 6),
                "ci_low": round(low, 6),
                "ci_high": round(high, 6),
                "delta_pct": round(100 * delta / mean_base, 2) if mean_base else "",
                "lower_is_better": measure in LOWER_IS_BETTER,
                "significant": not (low <= 0.0 <= high),
            }
        )
    return out


def main() -> None:
    records = load_records()
    if not records:
        raise SystemExit(f"no spread-grid results found in {RESULTS}")

    groupings = sorted({grouping for _arm, grouping in records})
    rows: list[dict] = []
    for grouping in groupings:
        for baseline_arm in BASELINES:
            baseline_record = records.get((baseline_arm, grouping))
            if not baseline_record:
                continue
            for arm in TREATMENTS:
                treatment_record = records.get((arm, grouping))
                if arm == baseline_arm or not treatment_record:
                    continue
                rows.extend(
                    compare(
                        baseline_record,
                        treatment_record,
                        grouping=grouping,
                        baseline=baseline_arm,
                        arm=arm,
                    )
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
                "arm",
                "grouping",
                "mean_surfaced",
                "median_surfaced",
                "max_surfaced",
                "mean_pool",
            ],
        )
        writer.writeheader()
        writer.writerows(surfacing)

    verdict_rows = verdicts(rows)
    with (HERE / "verdicts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "arm",
                "family",
                "primary_delta",
                "primary_ci_low",
                "primary_ci_high",
                "guardrail_delta",
                "guardrail_ci_low",
                "guardrail_ci_high",
                "control_delta",
                "control_significant",
                "vs_flat_delta",
                "beats_flat",
                "helps",
            ],
        )
        writer.writeheader()
        for row in verdict_rows:
            writer.writerow(
                {
                    "arm": row["arm"],
                    "family": row["family"],
                    "primary_delta": row["primary_delta"],
                    "primary_ci_low": row["primary_ci"][0],
                    "primary_ci_high": row["primary_ci"][1],
                    "guardrail_delta": row["guardrail_delta"],
                    "guardrail_ci_low": row["guardrail_ci"][0],
                    "guardrail_ci_high": row["guardrail_ci"][1],
                    "control_delta": row["control_delta"],
                    "control_significant": row["control_significant"],
                    "vs_flat_delta": row["vs_flat_delta"],
                    "beats_flat": row["beats_flat"],
                    "helps": row["helps"],
                }
            )

    payload = {
        "experiment": "EXP-2026-08-005",
        "generated_from": "eval/results/*.json (spreadexp grid, prod condition)",
        "primary": PRIMARY,
        "guardrail": GUARDRAIL,
        "guardrail_floor": GUARDRAIL_FLOOR,
        "target_grouping": TARGET_GROUPING,
        "control_grouping": CONTROL_GROUPING,
        "note": (
            "Paired over the same 30 synthetic profiles per grouping as "
            "EXP-2026-08-003/004. Judgments are the union of each profile's "
            "constituent LongEval-Sci queries' dctr qrels — click-derived "
            "pseudo-relevance, not human assessment. The three coverage metrics "
            "are hand-rolled (eval/harness/cluster_metrics.py) and comparable to "
            "nothing published. Every arm runs the deployed surfacing condition "
            "(match_threshold 0.5, surface_limit 250)."
        ),
        "statistical_test": (
            f"paired bootstrap over profiles, {BOOTSTRAP_RESAMPLES} resamples, "
            f"seed {BOOTSTRAP_SEED}, 95% percentile interval"
        ),
        "identity_drift": identity_drift(records),
        "verdicts": verdict_rows,
        "helps": [row["arm"] for row in verdict_rows if row["helps"]],
        "surfacing": surfacing,
        "rows": rows,
    }
    (HERE / "metrics.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    parent = HERE.parent
    inject(
        "GENERATED VERDICTS",
        verdict_table(verdict_rows),
        parent / "RESULTS.md",
        parent / "tables" / "verdicts.md",
    )
    inject(
        "GENERATED COVERAGE",
        coverage_table(rows),
        parent / "RESULTS.md",
        parent / "tables" / "coverage.md",
    )
    inject(
        "GENERATED SURFACING",
        surfacing_table(surfacing),
        parent / "RESULTS.md",
        parent / "tables" / "surfacing.md",
    )
    print(
        f"Wrote metrics.csv, surfacing.csv, verdicts.csv, metrics.json, tables/ "
        f"({len(rows)} rows; helps: {payload['helps'] or 'none'})"
    )


if __name__ == "__main__":
    main()

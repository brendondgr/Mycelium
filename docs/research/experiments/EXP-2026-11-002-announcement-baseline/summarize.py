"""EXP-2026-11-002: tables and derived numbers from the two data files.

Reads ``data/metrics.json`` (the ``announcement_metrics`` output) and
``data/labfit_labels.csv`` (agent-labelled lab-fit judgments), writes
``data/derived.json`` and ``tables/summary.md``, and replaces the generated block
in ``RESULTS.md``. No number is typed by hand anywhere.

    uv run --no-sync --project web/backend python \
        docs/research/experiments/EXP-2026-11-002-announcement-baseline/summarize.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEGIN, END = "<!-- BEGIN GENERATED TABLE -->", "<!-- END GENERATED TABLE -->"


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def main() -> None:
    metrics = json.loads((HERE / "data" / "metrics.json").read_text())
    labels = list(csv.DictReader((HERE / "data" / "labfit_labels.csv").open()))

    dept = next(t for t in metrics["targets"].values() if t["kind"] == "department")
    floor = dept["lab_fit_floor"]
    suits = sorted(float(r["fit"]) for r in labels if r["suits"] == "yes")
    unsuited = sorted(float(r["fit"]) for r in labels if r["suits"] == "no")
    admitted = [r for r in labels if float(r["fit"]) >= floor]
    admitted_ok = [r for r in admitted if r["suits"] == "yes"]
    derived = {
        "lab_fit_floor": floor,
        "labelled_calls": len(labels),
        "labs_labelled": len({r["lab"] for r in labels}),
        "admitted_at_floor": len(admitted),
        "admitted_suiting": len(admitted_ok),
        "lab_fit_precision_at_floor": round(len(admitted_ok) / len(admitted), 4)
        if admitted
        else None,
        "lowest_suits_score": suits[0] if suits else None,
        "highest_unsuited_score": unsuited[-1] if unsuited else None,
        "separable": bool(suits and unsuited and suits[0] > unsuited[-1]),
        "score_range": [min(suits + unsuited), max(suits + unsuited)],
    }
    (HERE / "data" / "derived.json").write_text(json.dumps(derived, indent=2) + "\n")

    lines = ["| Target | Measure | Value |", "|---|---|---:|"]
    for key, t in sorted(metrics["targets"].items()):
        name = t["name"]
        for measure in (
            "posted",
            "held",
            "seeded_seen",
            "interested_rate",
            "remind_rate",
            "not_for_us_rate",
            "link_clicks",
            "slate_rows",
            "slate_dept_level",
            "slate_dept_level_rate",
            "scored_rows",
            "scored_dept_level",
            "labs_with_vector",
        ):
            if measure in t:
                lines.append(f"| {name} | {measure} | {_fmt(t[measure])} |")
    health = metrics["route_health"]
    for measure in ("routes", "ok", "failing", "unchecked"):
        lines.append(f"| all bindings | route_health.{measure} | {health[measure]} |")
    for measure, value in derived.items():
        if measure == "score_range":
            value = f"{value[0]:.4g}–{value[1]:.4g}"
        lines.append(f"| lab-fit (agent-labelled) | {measure} | {_fmt(value)} |")
    table = "\n".join(lines)
    (HERE / "tables" / "summary.md").write_text(table + "\n")

    results = HERE / "RESULTS.md"
    text = results.read_text()
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        _old, tail = rest.split(END, 1)
        results.write_text(f"{head}{BEGIN}\n{table}\n{END}{tail}")
    print(json.dumps(derived, indent=2))


if __name__ == "__main__":
    main()

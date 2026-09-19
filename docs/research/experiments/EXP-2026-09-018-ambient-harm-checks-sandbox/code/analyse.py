"""EXP-2026-09-018's tables, from ``data/exp018-run1.json``.

    python3 docs/research/experiments/EXP-2026-09-018-ambient-harm-checks-sandbox/code/analyse.py
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main() -> None:
    data = json.loads((HERE / "data" / "exp018-run1.json").read_text())
    rows = [
        {
            "check": r["check"],
            "injection": r["injection"],
            "clean": data["clean"]["checks"][r["check"]],
            "own_delta": r["own_delta"],
            "cross_talk": ",".join(r["cross_talk"]) or "none",
        }
        for r in data["injections"]
    ]
    metrics = {
        "clean_nonzero_checks": sorted(k for k, v in data["clean"]["checks"].items() if v),
        "clean_cap_hits": len(data["clean"]["cap_hits"]),
        "injections": len(rows),
        "detected": data["detected"],
        "cross_talk": data["cross_talk"],
        "restored_equal": data["restored_equal"],
        "seconds": data["seconds"],
        "sandbox_validation_precision": data["clean"]["validation_precision"]["precision"],
    }
    (HERE / "data" / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    with (HERE / "data" / "metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "| Check | Injection | Clean record | Own change | Other checks moved |",
        "|---|---|---:|---:|---|",
    ] + [
        f"| {r['check']} | {r['injection']} | {r['clean']} | +{r['own_delta']} | {r['cross_talk']} |"
        for r in rows
    ]
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()

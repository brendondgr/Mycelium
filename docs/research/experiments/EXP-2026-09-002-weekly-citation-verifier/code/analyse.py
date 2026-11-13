"""EXP-2026-09-002: fold census, rebuild and injection into data/metrics.json.

    python3 docs/research/experiments/EXP-2026-09-002-weekly-citation-verifier/code/analyse.py
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def main():
    census = json.loads((HERE / "data" / "census.json").read_text())
    rebuild = json.loads((HERE / "data" / "rebuild.json").read_text())
    inject = json.loads((HERE / "data" / "inject.json").read_text())
    m = {
        "weeklies": census["weeklies"], "weeklies_fallback": census["by_origin"].get("fallback", 0),
        "weeklies_llm": census["llm_weeklies"], "llm_project_sections": census["llm_project_sections"],
        "claims_checked_total": census["claims_total"], "sentences_removed_total": census["removed_total"],
        "llm_claims_checked": sum(w["llm_claims"] for w in census["weeks"].values()),
        "rebuilt": len(rebuild), "rebuilt_faithful": sum(bool(e.get("faithful")) for e in rebuild),
        "rebuilt_references_identical": sum(bool(e.get("references_identical")) for e in rebuild),
        "reverify_removed_min": min(e["reverify_removed"] for e in rebuild if "reverify_removed" in e),
        "reverify_removed_max": max(e["reverify_removed"] for e in rebuild if "reverify_removed" in e),
        "reverify_claims_equal_stored": sum(e.get("reverify_claims") == e.get("stored_claims") for e in rebuild),
    }
    for cls, v in inject["classes"].items():
        m[f"inject_{cls}_n"] = v["n"]
        m[f"inject_{cls}_caught"] = v["caught"]
        if v["recall"] is not None:
            m[f"inject_{cls}_recall"] = v["recall"]
            m[f"inject_{cls}_recall_ci_low"] = v["ci95"][0]
            m[f"inject_{cls}_recall_ci_high"] = v["ci95"][1]
    (HERE / "data" / "metrics.json").write_text(json.dumps(m, indent=1))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerows(m.items())
    print(json.dumps(m, indent=1))


if __name__ == "__main__":
    main()

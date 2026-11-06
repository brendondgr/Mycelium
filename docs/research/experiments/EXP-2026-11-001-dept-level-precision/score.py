"""EXP-2026-11-001: precision of apps/content/dept_level.py.

    score.py dump    every firing on the corpus → data/labels.csv (label column empty)
    score.py score   data/labels.csv (labelled) → data/metrics.json, data/metrics.csv
    score.py check   re-run the current detector; list firings not in data/labels.csv

Run from the repository root with DATABASE_URL pointing at the corpus copy.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ROOT = HERE.parents[3]
FIELDS = ["content_id", "type", "title", "reason", "rule", "field", "evidence",
          "eligibility_excerpt", "label", "note"]


def _django():
    sys.path.insert(0, str(ROOT / "web" / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def dump() -> None:
    _django()
    from apps.content.dept_level import reasons
    from apps.content.models import ContentItem

    DATA.mkdir(exist_ok=True)
    rows, total = [], 0
    items = ContentItem.objects.filter(
        type__in=["grant", "fellowship", "conference"]
    ).order_by("id")
    for item in items.iterator():
        total += 1
        meta = item.metadata or {}
        elig = meta.get("eligibility")
        if isinstance(elig, list):
            elig = " ".join(str(e) for e in elig)
        for r in reasons(meta):
            rows.append({
                "content_id": str(item.id),
                "type": item.type,
                "title": (meta.get("title") or meta.get("name") or "")[:160],
                "reason": r.key,
                "rule": r.rule,
                "field": r.field,
                "evidence": r.evidence,
                "eligibility_excerpt": " ".join(str(elig or "").split())[:400],
                "label": "",
                "note": "",
            })
    with (DATA / "labels.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (DATA / "population.json").write_text(json.dumps({"records": total, "firings": len(rows)}))
    print(f"{len(rows)} firings over {total} records → data/labels.csv")


def score() -> None:
    rows = list(csv.DictReader((DATA / "labels.csv").open()))
    missing = [r for r in rows if r["label"] not in ("correct", "incorrect", "unclear")]
    if missing:
        sys.exit(f"{len(missing)} rows unlabelled")
    population = json.loads((DATA / "population.json").read_text())
    removed = set(json.loads((DATA / "removed_rules.json").read_text())) if (
        DATA / "removed_rules.json").exists() else set()

    def precision(subset):
        n = len(subset)
        ok = sum(r["label"] == "correct" for r in subset)
        return {"fired": n, "correct": ok, "precision": round(ok / n, 4) if n else None}

    by_reason = {}
    for version, keep in (("v1", lambda r: True), ("v2", lambda r: r["rule"] not in removed)):
        kept = [r for r in rows if keep(r)]
        by_reason[version] = {
            reason: precision([r for r in kept if r["reason"] == reason])
            for reason in sorted({r["reason"] for r in rows})
        }
        by_reason[version]["overall"] = precision(kept)
    rules = {}
    for rule in sorted({r["rule"] for r in rows}):
        subset = [r for r in rows if r["rule"] == rule]
        rules[rule] = precision(subset)
    metrics = {
        "population_records": population["records"],
        "judgments": "agent-labelled (Claude), not human",
        "precision": by_reason,
        "per_rule_v1": rules,
        "removed_rules": sorted(removed),
        "labels": dict(Counter(r["label"] for r in rows)),
    }
    check = DATA / "check_v2.json"
    if check.exists():
        c = json.loads(check.read_text())
        ok = c["fired"] - len(c["unlabelled"]) - len(c["labelled_wrong"])
        metrics["v2_detector_rerun"] = {
            "fired": c["fired"],
            "unlabelled": len(c["unlabelled"]),
            "labelled_wrong": len(c["labelled_wrong"]),
            "precision": round(ok / c["fired"], 4) if c["fired"] else None,
        }
    (DATA / "metrics.json").write_text(json.dumps(metrics, indent=2))
    with (DATA / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["version", "reason", "fired", "correct", "precision"])
        for version, table in by_reason.items():
            for reason, m in table.items():
                w.writerow([version, reason, m["fired"], m["correct"], m["precision"]])
    _table(metrics)
    print(json.dumps(by_reason, indent=2))


def _table(metrics: dict) -> None:
    """tables/summary.md, generated from metrics.json (never typed)."""
    lines = [
        "| Detector | Reason | Fired | Correct | Precision |",
        "|---|---|---:|---:|---:|",
    ]
    for version in ("v1", "v2"):
        for reason, m in metrics["precision"][version].items():
            lines.append(
                f"| {version} | {reason} | {m['fired']} | {m['correct']} | "
                f"{m['precision']} |"
            )
    rerun = metrics.get("v2_detector_rerun")
    if rerun:
        lines.append(
            f"| v2 (re-run) | overall | {rerun['fired']} | "
            f"{rerun['fired'] - rerun['unlabelled'] - rerun['labelled_wrong']} | "
            f"{rerun['precision']} |"
        )
    lines.append("")
    lines.append(f"Judgments: {metrics['judgments']}. Records: {metrics['population_records']}.")
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "summary.md").write_text("\n".join(lines) + "\n")


def check() -> None:
    """The v2 detector on the same corpus: every firing must already be labelled
    (a removed rule can let a later rule fire on the same record)."""
    _django()
    from apps.content.dept_level import VERSION, reasons
    from apps.content.models import ContentItem

    labelled = {
        (r["content_id"], r["reason"]): r for r in csv.DictReader((DATA / "labels.csv").open())
    }
    fired, new, wrong = 0, [], []
    items = ContentItem.objects.filter(type__in=["grant", "fellowship", "conference"])
    for item in items.iterator():
        for r in reasons(item.metadata or {}):
            fired += 1
            row = labelled.get((str(item.id), r.key))
            if row is None:
                new.append((str(item.id), r.key, r.rule, r.evidence[:120]))
            elif row["label"] != "correct":
                wrong.append((str(item.id), r.key, r.rule, row["note"]))
    out = {"detector": VERSION, "fired": fired, "unlabelled": new, "labelled_wrong": wrong}
    (DATA / "check_v2.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({"fired": fired, "unlabelled": len(new), "labelled_wrong": len(wrong)}))


if __name__ == "__main__":
    {"dump": dump, "score": score, "check": check}[sys.argv[1]]()

"""EXP-2026-11-019: metrics from the run logs.

    python3 docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/analyse.py [--tag main]

Reads ``logs/runs_{gate,baseline}_<tag>.jsonl``; writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``. Only repetitions completed by
both arms are pooled (PROTOCOL.md "Scale"). Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
Z = 1.959964
CLAIM_B = ("S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10")
ORDER = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S4o")


def wilson(k, n):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def upper0(n):
    """Exact one-sided 95% upper bound for 0 events in n."""
    return round(1 - 0.05 ** (1 / n), 4) if n else None


def newcombe(k1, n1, k2, n2):
    """Hybrid Wilson interval for p1 - p2 (Newcombe 1998, method 10)."""
    if not n1 or not n2:
        return [None, None]
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return [round(lo, 4), round(hi, 4)]


def load(arm, tag, grading="v2"):
    """Run rows; with grading v2 (Amendment 2) the answer-point fields come
    from ``logs/grades_v2_<arm>_<tag>.jsonl`` (``code/regrade019.py``)."""
    path = HERE / "logs" / f"runs_{arm}_{tag}.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.open()]
    if grading == "v2":
        g = HERE / "logs" / f"grades_v2_{arm}_{tag}.jsonl"
        over = {}
        for line in g.open():
            r = json.loads(line)
            over[(r["rep"], r["scenario"], r["seeker"])] = r
        missing = [r for r in rows if (r["rep"], r["scenario"], r["seeker"]) not in over]
        if missing:
            raise SystemExit(f"{len(missing)} {arm} rows have no v2 grade: run regrade019.py")
        for r in rows:
            v = over[(r["rep"], r["scenario"], r["seeker"])]
            for k, val in v.items():
                if k not in ("arm", "rep", "scenario", "seeker"):
                    r[k] = val
    return rows


def rate(rows, key):
    k = sum(1 for r in rows if r.get(key))
    n = len(rows)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


def compute(tag, grading):
    raw = {arm: load(arm, tag, grading) for arm in ("gate", "baseline")}
    reps = {arm: defaultdict(set) for arm in raw}
    for arm, rows in raw.items():
        for r in rows:
            reps[arm][r["rep"]].add((r["scenario"], r["seeker"]))
    planned = max((len(v) for arm in reps for v in reps[arm].values()), default=0)
    complete = sorted(
        rep
        for rep in set(reps["gate"]) & set(reps["baseline"])
        if len(reps["gate"][rep]) == planned and len(reps["baseline"][rep]) == planned
    )
    out: dict = {"tag": tag, "grading": grading, "reps_pooled": complete,
                 "runs_per_rep": planned}
    out["ended_on_question"] = {
        arm: sum(1 for r in rows if r.get("ended_on_question")) for arm, rows in raw.items()
    }
    out["runs_logged"] = {arm: len(rows) for arm, rows in raw.items()}
    out["runs_not_pooled"] = {
        arm: sum(1 for r in rows if r["rep"] not in complete) for arm, rows in raw.items()
    }
    pooled = {arm: [r for r in rows if r["rep"] in complete] for arm, rows in raw.items()}
    # Amendment 3 (post hoc): empty turns by repetition, and what recall showed.
    out["vacuous_by_rep"] = {
        arm: {str(rep): sum(1 for r in rows if r["rep"] == rep and r.get("vacuous") and not r.get("failed"))
              for rep in sorted({r["rep"] for r in rows})}
        for arm, rows in raw.items()
    }
    out["recall"] = {}
    for arm in raw:
        path = HERE / "logs" / f"recall_{arm}_{tag}.jsonl"
        if path.exists():
            rec = [json.loads(line) for line in path.open()]
            out["recall"][arm] = {
                "runs": len(rec),
                "with_recall": sum(1 for r in rec if r["recall_present"]),
                "recall_naming_outside_consent": sum(1 for r in rec if r["recall_outside"]),
                "upper95_if_zero": upper0(len(rec)),
            }
    valid = {
        arm: [r for r in rows if not r.get("failed") and not r.get("vacuous")]
        for arm, rows in pooled.items()
    }
    out["failed"] = {arm: sum(1 for r in rows if r.get("failed")) for arm, rows in pooled.items()}
    out["vacuous"] = {
        arm: sum(1 for r in rows if not r.get("failed") and r.get("vacuous"))
        for arm, rows in pooled.items()
    }
    flat: list[dict] = []

    def put(arm, scenario, variant, metric, d):
        flat.append({"arm": arm, "scenario": scenario, "variant": variant, "metric": metric,
                     "k": d.get("k"), "n": d.get("n"), "value": d.get("rate", d.get("value")),
                     "lo": (d.get("wilson95") or [None, None])[0],
                     "hi": (d.get("wilson95") or [None, None])[1]})

    per = {}
    for arm, rows in valid.items():
        per[arm] = {}
        for s in ORDER:
            rs = [r for r in rows if r["scenario"] == s]
            if not rs:
                continue
            m = {"n": len(rs)}
            for key in ("violation_any", "violation_answer", "must_named", "outside_first",
                        "outside_used", "tier_stated", "says_nobody", "reason_stated",
                        "beyond_offered", "for_call_offered"):
                if any(key in r for r in rs):
                    m[key] = rate([r for r in rs if key in r], key)
                    put(arm, s, "all", key, m[key])
            variants = sorted({r["variant"] for r in rs})
            if len(variants) > 1:
                m["by_variant"] = {}
                for v in variants:
                    vr = [r for r in rs if r["variant"] == v]
                    m["by_variant"][v] = {
                        key: rate([r for r in vr if key in r], key)
                        for key in ("violation_any", "violation_answer", "reason_stated",
                                    "says_nobody", "beyond_offered", "for_call_offered")
                        if any(key in r for r in vr)
                    }
                    for key, d in m["by_variant"][v].items():
                        put(arm, s, v, key, d)
            secs = [r["seconds"] for r in rs if r.get("seconds")]
            m["seconds_mean"] = round(sum(secs) / len(secs), 1) if secs else None
            m["tokens_mean"] = round(sum(r.get("tokens") or 0 for r in rs) / len(rs))
            per[arm][s] = m
    out["per_scenario"] = per

    claims: dict = {}
    g = valid["gate"]
    a = {}
    for s in ("S1", "S2"):
        rs = [r for r in g if r["scenario"] == s]
        a[s] = rate(rs, "must_named")
        a[s]["bar"] = 0.8
        a[s]["passes"] = a[s]["rate"] is not None and a[s]["rate"] >= 0.8
    claims["a"] = a
    b_rows = [r for r in g if r["scenario"] in CLAIM_B]
    b = rate(b_rows, "violation_any")
    b["upper95_if_zero"] = upper0(b["n"])
    b["points"] = {
        p: sum(1 for r in b_rows if (r.get("violations") or {}).get(p)) for p in ("catalog", "results", "answer")
    }
    with_o = [r for r in g if r["scenario"] in CLAIM_B + ("S4o",)]
    b["secondary_with_S4o"] = rate(with_o, "violation_any")
    b["secondary_with_S4o"]["upper95_if_zero"] = upper0(len(with_o))
    b["passes"] = b["k"] == 0 and b["n"] > 0
    claims["b"] = b
    base_rows = [r for r in valid["baseline"] if r["scenario"] in CLAIM_B]
    cg = rate(b_rows, "violation_answer")
    cb = rate(base_rows, "violation_answer")
    diff = newcombe(cb["k"], cb["n"], cg["k"], cg["n"])
    claims["c"] = {
        "gate": cg,
        "baseline": cb,
        "difference": round(cb["rate"] - cg["rate"], 4) if cb["n"] and cg["n"] else None,
        "newcombe95": diff,
        "passes": diff[0] is not None and diff[0] > 0,
        "baseline_any_point": rate(base_rows, "violation_any"),
    }
    out["claims"] = claims
    put("gate", "S1", "all", "claim_a_named", a.get("S1", {}))
    put("gate", "S2", "all", "claim_a_named", a.get("S2", {}))
    put("gate", "S3-S10", "all", "claim_b_violation_any", b)
    put("gate", "S3-S10", "all", "claim_c_answer_violation", cg)
    put("baseline", "S3-S10", "all", "claim_c_answer_violation", cb)
    flat.append({"arm": "baseline-gate", "scenario": "S3-S10", "variant": "all",
                 "metric": "claim_c_difference", "k": None, "n": None,
                 "value": claims["c"]["difference"], "lo": diff[0], "hi": diff[1]})

    for row in flat:
        row["grading"] = grading
    lines = []
    for arm in ("gate", "baseline"):
        for sc, m in per.get(arm, {}).items():
            def cell(key):
                d = m.get(key)
                return f"{d['k']}/{d['n']}" if d else "—"
            lines.append(f"| {grading} | {arm} | {sc} | {m['n']} | {cell('violation_any')} | "
                         f"{cell('violation_answer')} | {cell('must_named')} | {cell('says_nobody')} |")
    return out, flat, lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="main")
    args = ap.parse_args()
    both, flat, lines = {}, [], []
    # v2 (Amendment 2) is primary; v1 is the grading registered first.
    for grading in ("v2", "v1"):
        out, f, ls = compute(args.tag, grading)
        both[grading] = out
        flat += f
        lines += ls
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "metrics.json").write_text(json.dumps(both, indent=1))
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["grading", "arm", "scenario", "variant", "metric",
                                           "k", "n", "value", "lo", "hi"])
        w.writeheader()
        w.writerows(flat)
    head = ["| Grading | Arm | Scenario | n | Violation (any point) | Answer violation | "
            "Named (S1/S2) | Says nobody |", "|---|---|---|---:|---|---|---|---|"]
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "summary.md").write_text(
        f"Generated by `code/analyse.py` from `logs/runs_*_{args.tag}.jsonl` and "
        f"`logs/grades_v2_*_{args.tag}.jsonl`; repetitions pooled: "
        f"{both['v2']['reps_pooled']}. v2 = Amendment 2 (answer = final text + "
        f"questions shown), primary; v1 = as first registered.\n\n"
        + "\n".join(head + lines) + "\n")
    print(json.dumps({g: both[g]["claims"] for g in both}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

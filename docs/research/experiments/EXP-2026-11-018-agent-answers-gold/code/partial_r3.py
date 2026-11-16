"""EXP-2026-11-018 Amendment 3, measure 3: did a list answer present a partial
view as complete? Fixed in PROTOCOL.md before the run. Standard library only.

    python3 docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/partial_r3.py

Reads ``data/runs_r3.jsonl``; for each arm-(a)/(c) run of a ``list`` question
(the first non-failed attempt of each job) writes one row to
``data/partial_r3.jsonl`` and the per-arm counts to ``data/metrics_partial_r3.json``
and ``tables/partial_r3.md``; reports ``j08`` on its own in
``tables/j08_r3.md``.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
MARK = re.compile(r"only the first \d+ of \d+|\d+ more deadlines? falls? after", re.I)
SAYS = [re.compile(p, re.I) for p in (
    r"\b(first|top|only)\s+\d+\s+(of|out of)\s+\d+",
    r"\bpartial\b",
    r"\bnot (a )?(complete|full|exhaustive)\b",
    r"\b\d+\s+more\b",
    r"\bmore (items|results|grants|fellowships|conferences|calls|papers|deadlines)\b",
    r"\bnot all\b",
    r"\b(and|plus) others\b",
    r"\bincomplete\b",
)]


def wilson(k, n, z=1.96):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 4), round(min(1, c + h), 4)]


def classify(row):
    results = row.get("results") or []
    marked = [i for i, r in enumerate(results) if MARK.search(str(r.get("content") or ""))]
    if not marked:
        return "no_partial"
    first = marked[0]
    name = results[first].get("name")
    if any(r.get("name") == name and not MARK.search(str(r.get("content") or ""))
           for r in results[first + 1:]):
        return "fetched_rest"
    if not (row.get("final_text") or "").strip():
        return "no_answer"  # ended on a question or the give-up line: nothing presented
    seen = row.get("final_text") or ""
    if any(p.search(seen) for p in SAYS):
        return "said_partial"
    return "presented_complete"


def main() -> int:
    rows = [json.loads(x) for x in (EXP / "data" / "runs_r3.jsonl").read_text().splitlines() if x.strip()]
    jobs = {}
    for r in rows:
        jobs.setdefault((r["arm"], r["rep"], r["id"]), []).append(r)
    out, counts = [], {}
    for (arm, rep, qid), attempts in sorted(jobs.items()):
        if arm == "b" or attempts[0].get("kind") != "list":
            continue
        attempts.sort(key=lambda r: r.get("attempt", 1))
        ok = next((r for r in attempts if not r.get("failed")), None)
        cls = "failed" if ok is None else classify(ok)
        out.append({"arm": arm, "rep": rep, "id": qid, "class": cls})
        counts.setdefault(arm, {}).setdefault(cls, 0)
        counts[arm][cls] += 1
    m = {}
    for arm, c in counts.items():
        n = sum(c.values())
        saw = n - c.get("no_partial", 0) - c.get("failed", 0)
        k = c.get("presented_complete", 0)
        m[arm] = {"runs": n, "saw_partial": saw, **c,
                  "presented_complete_rate_all": {"k": k, "n": n, "rate": round(k / n, 4) if n else None,
                                                  "wilson95": wilson(k, n)},
                  "presented_complete_rate_saw": {"k": k, "n": saw, "rate": round(k / saw, 4) if saw else None,
                                                  "wilson95": wilson(k, saw)}}
    (EXP / "data" / "partial_r3.jsonl").write_text("".join(json.dumps(r) + "\n" for r in out))
    (EXP / "data" / "metrics_partial_r3.json").write_text(json.dumps(m, indent=1) + "\n")
    lines = ["| arm | list runs | saw partial | fetched rest | said partial | presented complete | no partial | failed | (iii)/all [95%] |",
             "|---|---|---|---|---|---|---|---|---|"]
    for arm in sorted(m):
        v = m[arm]
        a = v["presented_complete_rate_all"]
        lines.append(f"| {arm} | {v['runs']} | {v['saw_partial']} | {v.get('fetched_rest', 0)} | "
                     f"{v.get('said_partial', 0)} | {v.get('presented_complete', 0)} | "
                     f"{v.get('no_partial', 0)} | {v.get('failed', 0)} | {a['rate']} {a['wilson95']} |")
    (EXP / "tables").mkdir(exist_ok=True)
    (EXP / "tables" / "partial_r3.md").write_text("\n".join(lines) + "\n")
    j = [r for r in rows if r["id"] == "j08"]
    jl = ["| arm | rep | attempt | failed | functions | errors | final (first 160 chars) |", "|---|---|---|---|---|---|---|"]
    for r in sorted(j, key=lambda r: (r["arm"], r["rep"], r.get("attempt", 1))):
        fn = ", ".join(r.get("functions") or []) if r["arm"] != "b" else "(single call)"
        err = "; ".join(str((e or {}).get("code")) for e in (r.get("errors") or [])) or r.get("error", "")
        txt = (r.get("final_text") or "").replace("\n", " ").replace("|", "/")[:160]
        jl.append(f"| {r['arm']} | {r['rep']} | {r.get('attempt', 1)} | {r.get('failed') or ''} | {fn} | {err} | {txt} |")
    (EXP / "tables" / "j08_r3.md").write_text("\n".join(jl) + "\n")
    print(json.dumps(m, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

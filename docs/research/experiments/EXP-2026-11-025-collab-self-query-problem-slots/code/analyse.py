"""EXP-2026-11-025: counts from the anonymised logs -> data/metrics.{json,csv},
tables/summary.md. Reads only this folder and EXP-2026-11-023/-024's
anonymised records; prints nothing that is not also written."""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
E023 = HERE.parent / "EXP-2026-11-023-collab-live-fsu-sc"
E024 = HERE.parent / "EXP-2026-11-024-collab-typed-question-rerun"
ARMS = ("prev", "multi")

runs = {a: json.loads((HERE / f"logs/search_{a}_anon.json").read_text()) for a in ARMS}
rows = {a: {r["seeker_id"]: r for r in runs[a]["results"]} for a in ARMS}
e024 = {
    r["seeker_id"]: r
    for r in json.loads((E024 / "logs/search_after_anon.json").read_text())["results"]
}
e023_pairs = {
    (p["seeker"], p["candidate"]): p
    for p in json.loads((E023 / "data/ratings_anon.json").read_text())["pairs"]
}
seekers = sorted(rows["multi"])


def in_field(r):
    return [c for c in r["candidates"] if c["lane"] == "in_field"]


m = {"seekers": len(seekers)}
m["e024_after_seekers_with_any_suggestion"] = sum(e024[s]["shown"] > 0 for s in seekers)
for arm in ARMS:
    rs = [rows[arm][s] for s in seekers]
    shown = [(r["seeker_id"], c) for r in rs for c in r["candidates"] if c["shown_with_model"]]
    m[f"{arm}_seekers_with_any_suggestion"] = sum(r["shown"] > 0 for r in rs)
    m[f"{arm}_seekers_zero_shown"] = sum(r["shown"] == 0 for r in rs)
    m[f"{arm}_seekers_zero_slots_searched"] = sum(r["n_slots"] == 0 and not r["refused"] for r in rs)
    m[f"{arm}_seekers_refused_no_topic"] = sum(r["refused"] == "no_topic" for r in rs)
    m[f"{arm}_seekers_error"] = sum(bool(r["error"]) for r in rs)
    m[f"{arm}_slot_source_fallback"] = sum(r["slot_source"] == "fallback" for r in rs)
    m[f"{arm}_slots_total"] = sum(r["n_slots"] for r in rs)
    m[f"{arm}_problem_slots_total"] = sum(r["slot_facets"].count("problem") for r in rs)
    m[f"{arm}_seekers_one_problem_slot"] = sum(r["slot_facets"].count("problem") == 1 for r in rs)
    m[f"{arm}_seekers_with_any_gap_slot"] = sum(r["n_gaps"] > 0 for r in rs)
    m[f"{arm}_in_field_shortlisted_total"] = sum(len(in_field(r)) for r in rs)
    m[f"{arm}_shortlisted_total"] = sum(len(r["candidates"]) for r in rs)
    m[f"{arm}_dropped_by_model"] = sum(c["dropped_by_model"] for r in rs for c in r["candidates"])
    m[f"{arm}_seekers_whole_shortlist_dropped"] = sum(
        bool(r["candidates"]) and all(c["dropped_by_model"] for c in r["candidates"]) for r in rs
    )
    m[f"{arm}_seekers_empty_shortlist"] = sum(not r["candidates"] for r in rs)
    m[f"{arm}_shown_total"] = len(shown)
    for lane in ("in_field", "method_bridge", "problem_bridge", "resource"):
        m[f"{arm}_shown_{lane}"] = sum(c["lane"] == lane for _, c in shown)
    m[f"{arm}_distinct_candidates_shown"] = len({c["candidate_id"] for _, c in shown})
    m[f"{arm}_unexplained_searches"] = sum(r["explained"] is False for r in rs)
    pairs = {(s, c["candidate_id"]) for s, c in shown}
    rated = [e023_pairs[p] for p in pairs if p in e023_pairs]
    m[f"{arm}_shown_pairs"] = len(pairs)
    m[f"{arm}_shown_pairs_rated_in_023"] = len(rated)
    m[f"{arm}_shown_pairs_rated_in_023_yes"] = sum(p["rating"] == "yes" for p in rated)
    m[f"{arm}_shown_pairs_rated_in_023_maybe"] = sum(p["rating"] == "maybe" for p in rated)
    m[f"{arm}_shown_pairs_rated_in_023_no"] = sum(p["rating"] == "no" for p in rated)

(HERE / "data").mkdir(exist_ok=True)
(HERE / "data/metrics.json").write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
with open(HERE / "data/metrics.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["metric", "value", "n"])
    for k, v in sorted(m.items()):
        w.writerow([k, v, len(seekers)])

lines = [
    "| Seeker | 024 after: shown | Prev: problem slots / in-field shortlist / dropped / shown | Multi: problem slots / in-field shortlist / dropped / shown |",
    "|---|---|---|---|",
]
for s in seekers:
    cells = []
    for arm in ARMS:
        r = rows[arm][s]
        cells.append(
            f"{r['slot_facets'].count('problem')} / {len(in_field(r))} / "
            f"{sum(c['dropped_by_model'] for c in r['candidates'])} / {r['shown']}"
        )
    lines.append(f"| {s} | {e024[s]['shown']} | {cells[0]} | {cells[1]} |")
(HERE / "tables").mkdir(exist_ok=True)
(HERE / "tables/summary.md").write_text("\n".join(lines) + "\n")
print(json.dumps(m, indent=1, sort_keys=True))
print("\n".join(lines))

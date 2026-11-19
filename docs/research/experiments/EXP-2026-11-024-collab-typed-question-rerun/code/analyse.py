"""EXP-2026-11-024: counts from the anonymised logs -> data/metrics.{json,csv},
tables/summary.md. Reads only files in this folder and EXP-2026-11-023's
anonymised record; prints nothing that is not also written."""

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
E023 = HERE.parent / "EXP-2026-11-023-collab-live-fsu-sc"
ARMS = ("before", "after")

runs = {a: json.loads((HERE / f"logs/search_{a}_anon.json").read_text()) for a in ARMS}
rows = {a: {r["seeker_id"]: r for r in runs[a]["results"]} for a in ARMS}
works = json.loads((HERE / "logs/works_anon.json").read_text())
prep = json.loads((HERE / "logs/prepare.json").read_text())
e023_search = {r["seeker_id"]: r for r in json.loads((E023 / "logs/search_anon.json").read_text())}
e023_pairs = {
    (p["seeker"], p["candidate"]): p
    for p in json.loads((E023 / "data/ratings_anon.json").read_text())["pairs"]
}
seekers = sorted(rows["after"])

m = {"seekers": len(seekers)}
for arm in ARMS:
    rs = [rows[arm][s] for s in seekers]
    shown = [(r["seeker_id"], c) for r in rs for c in r["candidates"] if c["shown_with_model"]]
    m[f"{arm}_seekers_with_any_suggestion"] = sum(r["shown"] > 0 for r in rs)
    m[f"{arm}_seekers_zero_shown"] = sum(r["shown"] == 0 for r in rs)
    m[f"{arm}_seekers_zero_slots_searched"] = sum(
        r["n_slots"] == 0 and not r["refused"] for r in rs
    )
    m[f"{arm}_seekers_refused_no_topic"] = sum(r["refused"] == "no_topic" for r in rs)
    m[f"{arm}_seekers_error"] = sum(bool(r["error"]) for r in rs)
    for source, n in Counter(r["slot_source"] for r in rs).items():
        m[f"{arm}_slot_source_{source}"] = n
    m[f"{arm}_reader_unreachable"] = sum(
        (r["reader"] or {}).get("reachable") is False for r in rs
    )
    m[f"{arm}_seekers_with_any_gap_slot"] = sum(r["n_gaps"] > 0 for r in rs)
    m[f"{arm}_slots_total"] = sum(r["n_slots"] for r in rs)
    m[f"{arm}_shown_total"] = len(shown)
    for lane in ("in_field", "method_bridge", "problem_bridge", "resource"):
        m[f"{arm}_shown_{lane}"] = sum(c["lane"] == lane for _, c in shown)
    m[f"{arm}_shown_students"] = sum(c["candidate_role"] == "student" for _, c in shown)
    m[f"{arm}_distinct_candidates_shown"] = len({c["candidate_id"] for _, c in shown})
    m[f"{arm}_shortlisted_total"] = sum(len(r["candidates"]) for r in rs)
    m[f"{arm}_dropped_by_model"] = sum(c["dropped_by_model"] for r in rs for c in r["candidates"])
    m[f"{arm}_unexplained_searches"] = sum(r["explained"] is False for r in rs)
    m[f"{arm}_retries"] = sum(r["attempts"] > 1 for r in rs)
    pairs = {(s, c["candidate_id"]) for s, c in shown}
    rated = [e023_pairs[p] for p in pairs if p in e023_pairs]
    m[f"{arm}_shown_pairs"] = len(pairs)
    m[f"{arm}_shown_pairs_rated_in_023"] = len(rated)
    m[f"{arm}_shown_pairs_rated_in_023_yes"] = sum(p["rating"] == "yes" for p in rated)
    m[f"{arm}_shown_pairs_rated_in_023_maybe"] = sum(p["rating"] == "maybe" for p in rated)
    m[f"{arm}_shown_pairs_rated_in_023_no"] = sum(p["rating"] == "no" for p in rated)
    m[f"{arm}_shown_pairs_unrated"] = len(pairs) - len(rated)

# Seekers 023's typed path left empty, and what each arm shows them now.
empty_023 = [s for s in seekers if not any(
    c["shown_with_model"] for c in e023_search[s]["product"]["candidates"]
)]
m["e023_product_seekers_with_any_suggestion"] = len(seekers) - len(empty_023)
for arm in ARMS:
    m[f"{arm}_seekers_with_any_suggestion_among_023_empty"] = sum(
        rows[arm][s]["shown"] > 0 for s in empty_023
    )
m["e023_product_empty_seekers"] = len(empty_023)

fac = [w for w in works if w["role"] == "faculty"]
stu = [w for w in works if w["role"] == "student"]
m["faculty_works_imported"] = sum(w["works"] for w in fac)
m["faculty_works_read_non_thin"] = sum(w["facets_read"] - w["facets_thin"] for w in fac)
m["faculty_works_thin"] = sum(w["facets_thin"] for w in fac)
m["students_imported"] = sum(w["works"] > 0 for w in stu)
m["student_works_imported"] = sum(w["works"] for w in stu)
m["coauthor_pairs_rebuilt"] = prep["coauthorship"].get("pairs")
m["import_errors"] = sum(bool(r.get("error")) for r in prep["imports"])

(HERE / "data").mkdir(exist_ok=True)
(HERE / "data/metrics.json").write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
with open(HERE / "data/metrics.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["metric", "value", "n"])
    for k, v in sorted(m.items()):
        w.writerow([k, v, len(seekers)])

wb = {w["id"]: w for w in works}
lines = [
    "| Seeker | Works (read) | 023 product: slots / shown | Before: slots / source / shown | After: slots / source / gaps / shown |",
    "|---|---|---|---|---|",
]
for s in seekers:
    p23 = e023_search[s]["product"]
    sh23 = sum(c["shown_with_model"] for c in p23["candidates"])
    b, a = rows["before"][s], rows["after"][s]
    w = wb[s]
    lines.append(
        f"| {s} | {w['works']} ({w['facets_read'] - w['facets_thin']}) "
        f"| {p23['n_slots']} / {sh23} "
        f"| {b['n_slots']} / {b['slot_source']} / {b['shown']} "
        f"| {a['n_slots']} / {a['slot_source']} / {a['n_gaps']} / {a['shown']} |"
    )
(HERE / "tables").mkdir(exist_ok=True)
(HERE / "tables/summary.md").write_text("\n".join(lines) + "\n")
print(json.dumps(m, indent=1, sort_keys=True))
print("\n".join(lines))

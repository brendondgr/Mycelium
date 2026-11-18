"""EXP-2026-11-023: counts from the anonymised logs -> data/metrics.{json,csv}, tables/summary.md."""
import csv, json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
rows = json.loads((HERE / "logs/search_anon.json").read_text())
works = json.loads((HERE / "logs/works_anon.json").read_text())
prep = json.loads((HERE / "logs/prepare.json").read_text())
ARMS = ("product", "manual")
m = {"seekers": len(rows)}
for arm in ARMS:
    shown = [c for r in rows for c in r[arm]["candidates"] if c["shown_with_model"]]
    m[f"{arm}_seekers_zero_slots"] = sum(r[arm]["n_slots"] == 0 for r in rows)
    m[f"{arm}_seekers_with_any_gap_slot"] = sum(r[arm]["n_gaps"] > 0 for r in rows)
    m[f"{arm}_seekers_zero_shown"] = sum(
        not any(c["shown_with_model"] for c in r[arm]["candidates"]) for r in rows
    )
    m[f"{arm}_shown_total"] = len(shown)
    for lane, n in Counter(c["lane"] for c in shown).items():
        m[f"{arm}_shown_{lane}"] = n
    m[f"{arm}_shown_students"] = sum(c["candidate_role"] == "student" for c in shown)
    m[f"{arm}_shown_declared_tier"] = sum(c["tier"] == "declared" for c in shown)
    m[f"{arm}_shortlisted_total"] = sum(len(r[arm]["candidates"]) for r in rows)
    m[f"{arm}_dropped_by_model"] = sum(
        c["dropped_by_model"] for r in rows for c in r[arm]["candidates"]
    )
    m[f"{arm}_unexplained_searches"] = sum(r[arm]["explained"] is False for r in rows)
    m[f"{arm}_retries"] = sum(r[arm]["attempts"] > 1 for r in rows)
    m[f"{arm}_distinct_candidates_shown"] = len({c["candidate_id"] for c in shown})
m["rating_rows"] = sum(r["rating_rows"] for r in rows)
m["rating_rows_shown_with_model"] = sum(r["rating_rows_shown_with_model"] for r in rows)
m["rating_rows_model_dropped_only"] = m["rating_rows"] - m["rating_rows_shown_with_model"]
m["optional_extras"] = sum(r["optional_extras"] for r in rows)
m["seekers_zero_rating_rows"] = sum(r["rating_rows"] == 0 for r in rows)
m["excluded_lab_mate_pairs"] = sum(r["manual"]["excluded_lab_mate"] for r in rows)
m["excluded_coauthor_pairs"] = sum(r["manual"]["excluded_coauthor"] for r in rows)
fac = [w for w in works if w["role"] == "faculty"]
stu = [w for w in works if w["role"] == "student"]
m["faculty_works_imported"] = sum(w["works"] for w in fac)
m["faculty_works_read_non_thin"] = sum(w["facets_read"] - w["facets_thin"] for w in fac)
m["faculty_works_thin"] = sum(w["facets_thin"] for w in fac)
m["students_imported"] = sum(w["imported"] for w in stu)
m["student_works_imported"] = sum(w["works"] for w in stu)
m["candidates_open"] = rows[0]["manual"]["open_others"] + 1
m["coauthor_pairs_rebuilt"] = prep["coauthorship"].get("pairs")
m["ratings_done"] = 0
(HERE / "data/metrics.json").write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
with open(HERE / "data/metrics.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["metric", "value", "n"])
    for k, v in sorted(m.items()):
        w.writerow([k, v, 1])
lines = ["| Seeker | Works (read) | Product arm: slots / gaps / shown | Manual arm: slots / gaps / shortlisted / shown | Rating rows (shown) | Excluded: lab-mate / co-author |", "|---|---|---|---|---|---|"]
wb = {w["id"]: w for w in works}
for r in rows:
    p, q = r["product"], r["manual"]
    sp = sum(c["shown_with_model"] for c in p["candidates"]); sq = sum(c["shown_with_model"] for c in q["candidates"])
    w = wb[r["seeker_id"]]
    lines.append(f"| {r['seeker_id']} | {w['works']} ({w['facets_read']-w['facets_thin']}) | {p['n_slots']} / {p['n_gaps']} / {sp} | {q['n_slots']} / {q['n_gaps']} / {len(q['candidates'])} / {sq} | {r['rating_rows']} ({r['rating_rows_shown_with_model']}) | {q['excluded_lab_mate']} / {q['excluded_coauthor']} |")
(HERE / "tables/summary.md").write_text("\n".join(lines) + "\n")
print(json.dumps(m, indent=1, sort_keys=True))
print("\n".join(lines))

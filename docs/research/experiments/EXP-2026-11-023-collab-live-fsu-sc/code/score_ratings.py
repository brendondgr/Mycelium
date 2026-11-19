"""EXP-2026-11-023: score the maintainer's ratings (post hoc to the run, 2026-11-19).

Two steps:

  python3 code/score_ratings.py --private DIR   # DIR holds ratings_input.json and ratings/*.json
  python3 code/score_ratings.py                 # score from data/ratings_anon.json only

With --private, the private rating sheet input (names) and the rating page's
saved documents are joined into `data/ratings_anon.json`, which keeps only
anonymous ids, flags and the rating. Free-text notes are not copied, only
whether one was written. Then, from that file, the script writes the rating
metrics into `data/ratings_metrics.json` and `tables/ratings.md`.

The unit is a seeker-candidate pair. The rating page keyed each rating by
(seeker, candidate), so when one person appeared on two rows for the same
seeker (two lanes), both rows share one rating (ISSUES.md). Such a pair counts
once, and is "shown" if any of its rows was shown with the model.
"""

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ANON = HERE / "data" / "ratings_anon.json"


def wilson(k, n, z=1.959964):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def export(private: Path) -> None:
    sheet = json.loads((private / "ratings_input.json").read_text())
    saved = {p.stem: json.loads(p.read_text()) for p in (private / "ratings").glob("*.json")}
    pairs = {}
    seekers = []
    for s in sheet:
        sid = s["seeker_id"]
        doc = saved.get(sid, {})
        seekers.append({"seeker": sid, "rows": len(s["suggestions"]),
                        "missing_note_written": bool((doc.get(f"missing_{sid}") or "").strip())})
        for c in s["suggestions"]:
            cid = c["candidate_id"]
            key = f"r_{sid}_{cid}"
            p = pairs.setdefault((sid, cid), {
                "seeker": sid, "candidate": cid, "candidate_role": c["candidate_role"],
                "rows": 0, "lanes": [], "tiers": [],
                "shown_product": False, "shown_manual": False,
                "dropped_product": False, "dropped_manual": False,
                "rating": doc.get(key), "not_their_work": bool(doc.get(f"{key}_wrong")),
                "note_written": bool((doc.get(f"{key}_note") or "").strip()),
            })
            p["rows"] += 1
            p["lanes"].append(c["lane"])
            p["tiers"].append(c["tier"])
            for arm, a in c["arms"].items():
                p[f"shown_{arm}"] |= bool(a.get("shown_with_model"))
                p[f"dropped_{arm}"] |= bool(a.get("dropped_by_model"))
    out = {"seekers": seekers,
           "overall_note_written": bool((saved.get("overall", {}).get("overall_note") or "").strip()),
           "pairs": sorted(pairs.values(), key=lambda p: (p["seeker"], p["candidate"]))}
    ANON.write_text(json.dumps(out, indent=1) + "\n")


def score() -> None:
    d = json.loads(ANON.read_text())
    pairs = d["pairs"]
    for p in pairs:
        p["shown"] = p["shown_product"] or p["shown_manual"]

    def tally(sub):
        c = Counter(p["rating"] for p in sub)
        n = sum(c[v] for v in ("yes", "maybe", "no"))
        lo, hi = wilson(c["yes"], n)
        return {"n": n, "yes": c["yes"], "maybe": c["maybe"], "no": c["no"],
                "unrated": len(sub) - n,
                "yes_rate": round(c["yes"] / n, 4) if n else None,
                "yes_wilson95": [round(lo, 4), round(hi, 4)]}

    groups = {
        "all pairs": pairs,
        "shown with the model (either arm)": [p for p in pairs if p["shown"]],
        "dropped by the model only": [p for p in pairs if not p["shown"]],
        "shown, product arm": [p for p in pairs if p["shown_product"]],
        "shown, manual arm": [p for p in pairs if p["shown_manual"]],
        "includes a bridge-lane row": [p for p in pairs if any(l != "in_field" for l in p["lanes"])],
        "candidate is a student": [p for p in pairs if p["candidate_role"] == "student"],
    }
    m = {"groups": {k: tally(v) for k, v in groups.items()}}
    m["sheet_rows"] = sum(s["rows"] for s in d["seekers"])
    m["pairs"] = len(pairs)
    m["pairs_on_two_rows"] = sum(p["rows"] > 1 for p in pairs)
    m["not_their_work"] = sum(p["not_their_work"] for p in pairs)
    m["pair_notes_written"] = sum(p["note_written"] for p in pairs)
    m["missing_notes_written"] = sum(s["missing_note_written"] for s in d["seekers"])
    m["overall_note_written"] = d["overall_note_written"]
    per = defaultdict(Counter)
    for p in pairs:
        per[p["seeker"]][p["rating"]] += 1
    m["seekers_with_pairs"] = len(per)
    m["seekers_all_yes"] = sum(c["yes"] == sum(c.values()) for c in per.values())
    m["per_seeker"] = {s: dict(c) for s, c in sorted(per.items())}
    (HERE / "data" / "ratings_metrics.json").write_text(json.dumps(m, indent=1) + "\n")

    lines = ["<!-- generated by code/score_ratings.py; do not edit -->", "",
             "| Pairs | n | Would contact | Maybe | No | Would contact, rate (Wilson 95%) |",
             "|---|---:|---:|---:|---:|---|"]
    for k, t in m["groups"].items():
        rate = "–" if t["yes_rate"] is None else f"{t['yes_rate']} ({t['yes_wilson95'][0]}–{t['yes_wilson95'][1]})"
        lines.append(f"| {k} | {t['n']} | {t['yes']} | {t['maybe']} | {t['no']} | {rate} |")
    lines += ["", f"Sheet rows {m['sheet_rows']}; seeker-candidate pairs {m['pairs']} "
              f"({m['pairs_on_two_rows']} on two rows); unrated {m['groups']['all pairs']['unrated']}; "
              f"'not their work' {m['not_their_work']}; seekers with pairs {m['seekers_with_pairs']}, "
              f"all rated would-contact {m['seekers_all_yes']}."]
    (HERE / "tables" / "ratings.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path)
    a = ap.parse_args()
    if a.private:
        export(a.private)
    score()

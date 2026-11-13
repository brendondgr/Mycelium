"""EXP-2026-11-013: score the returned rating sheets. Written before any
rating came back; nothing in it depends on the ratings' content.

    python3 docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged/code/score.py \
        [--sheets data/ratings] [--tag main]

Reads the filled sheets (``answers_rater<k>.csv``, ``removed_rater<k>.csv``) from
``--sheets`` (default ``data/ratings/``: copy the returned files there, unchanged),
unblinds with data/key.csv and data/removed_key.csv, and writes
data/human_metrics.json and tables/human.md.

- Majority label per item (ties are reported as ties, never broken by picking
  a rater). ``correct``: share of questions whose majority label is ``yes``;
  ``partly`` is reported beside it.
- Citation support: per citation, majority of yes/no; rate over all citations.
- Paired bootstrap (10,000 resamples of questions, seed fixed) for the
  difference in majority-yes rate, arm a minus arm b, over questions both arms
  answered.
- Verifier removal precision: of the flagged items with a majority label,
  share labelled unsupported (``no``).
- Verifier recall: of the unsupported details raters list in arm a answers
  (majority: listed by at least half the raters, matched by normalised text),
  plus every flagged item raters judged unsupported, share the verifier flagged.
  Details listed on a final answer were by construction not flagged in it
  (the loop either repaired or stripped them), so they count as misses.
- Agreement: Cohen's kappa (two raters) or Fleiss' kappa (three or more) for
  ``correct``, citation support and removed-item support.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def read_csv(p):
    with p.open(newline="") as fh:
        return list(csv.DictReader(fh))


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().casefold())


def majority(labels):
    labels = [x for x in labels if x]
    if not labels:
        return None
    c = Counter(labels).most_common()
    if len(c) > 1 and c[0][1] == c[1][1]:
        return "tie"
    return c[0][0]


def fleiss(table, cats):
    """table: list of per-item label lists (same raters per item)."""
    rows = [t for t in table if all(t)]
    if not rows:
        return None
    n = len(rows[0])
    if n < 2:
        return None
    P, totals = [], Counter()
    for t in rows:
        c = Counter(t)
        totals.update(c)
        P.append((sum(v * v for v in c.values()) - n) / (n * (n - 1)))
    N = len(rows)
    p_bar = sum(P) / N
    pe = sum((totals[k] / (N * n)) ** 2 for k in cats)
    return round((p_bar - pe) / (1 - pe), 4) if pe < 1 else None


def cohen(table, cats):
    rows = [t for t in table if len(t) == 2 and all(t)]
    if not rows:
        return None
    po = sum(a == b for a, b in rows) / len(rows)
    ca, cb = Counter(a for a, _ in rows), Counter(b for _, b in rows)
    pe = sum((ca[k] / len(rows)) * (cb[k] / len(rows)) for k in cats)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else None


def kappa(table, cats):
    return cohen(table, cats) if table and len(table[0]) == 2 else fleiss(table, cats)


def parse_cites(cell):
    out = {}
    for part in (cell or "").split(";"):
        m = re.match(r"\s*#(\d+)\s*=\s*(\w+)", part)
        if m:
            out[int(m.group(1))] = m.group(2).lower()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default="data/ratings")
    ap.add_argument("--tag", default="main")
    args = ap.parse_args()
    src = HERE / args.sheets
    key = {r["answer_id"]: r for r in read_csv(HERE / "data" / "key.csv")}
    rkey = {r["removed_id"]: r for r in read_csv(HERE / "data" / "removed_key.csv")}
    raters = sorted(src.glob("answers_rater*.csv"))
    if len(raters) < 2:
        raise SystemExit("need at least two filled answer sheets in " + str(src))
    by_answer = {}
    for p in raters:
        for row in read_csv(p):
            by_answer.setdefault(row["answer_id"], []).append(row)
    items = {}
    corr_table, cite_table = [], []
    for aid, rows in by_answer.items():
        labels = [norm(r["correct"]) for r in rows]
        corr_table.append(labels)
        cites = [parse_cites(r["citation_support"]) for r in rows]
        all_n = sorted({n for c in cites for n in c})
        cite_major = {}
        for n in all_n:
            ls = [c.get(n, "") for c in cites]
            cite_table.append(ls)
            cite_major[n] = majority(ls)
        details = [{norm(d) for d in (r["unsupported_details"] or "").split(";") if d.strip()} for r in rows]
        listed = Counter(d for ds in details for d in ds)
        items[aid] = {
            **key[aid], "correct": majority(labels), "labels": labels, "cites": cite_major,
            "useful": [int(r["useful_1to5"]) for r in rows if (r["useful_1to5"] or "").strip().isdigit()],
            "details_majority": sorted(d for d, k in listed.items() if k * 2 >= len(rows)),
        }
    res = {"raters": len(raters), "answers_rated": len(items), "arms": {}}
    for arm in ("a", "b"):
        its = [i for i in items.values() if i["arm"] == arm]
        cites = [v for i in its for v in i["cites"].values() if v in ("yes", "no")]
        useful = [u for i in its for u in i["useful"]]
        res["arms"][arm] = {
            "answers": len(its),
            "correct_yes": sum(i["correct"] == "yes" for i in its),
            "correct_partly": sum(i["correct"] == "partly" for i in its),
            "correct_no": sum(i["correct"] == "no" for i in its),
            "correct_tie": sum(i["correct"] == "tie" for i in its),
            "correct_rate": round(sum(i["correct"] == "yes" for i in its) / len(its), 4) if its else None,
            "citations_judged": len(cites),
            "citation_support_rate": round(cites.count("yes") / len(cites), 4) if cites else None,
            "useful_mean": round(sum(useful) / len(useful), 3) if useful else None,
            "answers_with_unsupported_detail": sum(bool(i["details_majority"]) for i in its),
        }
        cats = sorted({i["category"] for i in its})
        res["arms"][arm]["by_category"] = {
            c: round(sum(i["correct"] == "yes" for i in its if i["category"] == c)
                     / max(1, sum(1 for i in its if i["category"] == c)), 4) for c in cats}
    pairs = {}
    for i in items.values():
        pairs.setdefault(i["question_id"], {})[i["arm"]] = 1.0 if i["correct"] == "yes" else 0.0
    paired = [(v["a"], v["b"]) for v in pairs.values() if "a" in v and "b" in v]
    rng = random.Random(20261112)
    diffs = []
    for _ in range(10000):
        s = [paired[rng.randrange(len(paired))] for _ in paired]
        diffs.append(sum(a - b for a, b in s) / len(s))
    diffs.sort()
    res["paired"] = {"questions": len(paired),
                     "diff_a_minus_b": round(sum(a - b for a, b in paired) / len(paired), 4),
                     "ci95": [round(diffs[249], 4), round(diffs[9749], 4)],
                     "a_better": sum(a > b for a, b in paired), "b_better": sum(b > a for a, b in paired)}
    removed_rows = {}
    for p in sorted(src.glob("removed_rater*.csv")):
        for row in read_csv(p):
            removed_rows.setdefault(row["removed_id"], []).append(norm(row["supported"]))
    rem_major = {rid: majority(ls) for rid, ls in removed_rows.items()}
    judged = [rid for rid, m in rem_major.items() if m in ("yes", "no")]
    flagged_unsupported = [rid for rid in judged if rem_major[rid] == "no"]
    raters_missed = sum(len(i["details_majority"]) for i in items.values() if i["arm"] == "a")
    res["verifier"] = {
        "flagged_items": len(rem_major), "flagged_judged": len(judged),
        "removal_precision": round(len(flagged_unsupported) / len(judged), 4) if judged else None,
        "unsupported_found_by_raters_in_final_answers": raters_missed,
        "recall": round(len(flagged_unsupported) / (len(flagged_unsupported) + raters_missed), 4)
        if (flagged_unsupported or raters_missed) else None,
    }
    res["agreement"] = {
        "correct": kappa(corr_table, ["yes", "partly", "no"]),
        "citation_support": kappa(cite_table, ["yes", "no"]),
        "removed_support": kappa(list(removed_rows.values()), ["yes", "no"]),
    }
    res["disagreements"] = [{"answer_id": aid, "question_id": i["question_id"], "arm": i["arm"],
                             "labels": i["labels"]} for aid, i in items.items() if len(set(i["labels"])) > 1]
    (HERE / "data" / "human_metrics.json").write_text(json.dumps(res, indent=1))
    lines = ["| Arm | Answers | Correct (majority yes) | Partly | No | Citation support | Useful (mean) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, v in res["arms"].items():
        lines.append(f"| {arm} | {v['answers']} | {v['correct_rate']} | {v['correct_partly']} | {v['correct_no']} | "
                     f"{v['citation_support_rate']} | {v['useful_mean']} |")
    lines.append(f"\nPaired difference (a − b): {res['paired']['diff_a_minus_b']} {res['paired']['ci95']}")
    lines.append(f"Verifier precision {res['verifier']['removal_precision']}, recall {res['verifier']['recall']}")
    lines.append(f"Agreement: {res['agreement']}")
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "human.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "disagreements"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

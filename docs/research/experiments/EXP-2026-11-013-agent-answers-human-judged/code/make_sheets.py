"""EXP-2026-11-013: build the blinded rating sheets.

    python3 docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged/code/make_sheets.py \
        [--tag main] [--raters 3]

Standard library only. Reads data/arm_a_<tag>.jsonl and data/arm_b_<tag>.jsonl
and writes, under data/sheets/:

- ``answers_rater<k>.csv`` — every answer of both arms, rows shuffled with a
  per-rater seed, arm hidden behind an opaque answer id;
- ``removed_rater<k>.csv`` — every detail or citation the verifier flagged in
  a first draft (what the repair was asked to fix, and exactly what a
  repair-off loop would have stripped), verdict hidden;
- ``evidence/<answer id>.md`` — the question, the answer and the evidence that
  answer's producer read (arm a: every function result and reference card the
  turn had in view; arm b: the numbered records it was given);
- ``RATER_INSTRUCTIONS.md``.

The unblinding key is written to data/key.csv, outside ``sheets/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SALT = "EXP-2026-11-013"
INSTRUCTIONS = """# Rating instructions

Thank you for rating. Plan on about two hours; you can stop and resume.

You will rate answers to questions a lab's principal investigator asked a
research assistant. Each row of `answers_rater<k>.csv` is one answer. Open the
file named in `evidence_file` (in `evidence/`): it shows the question, the
answer, and **the evidence the assistant had in front of it**. The lab is
fictional; the papers, grants and fellowships are real.

**Judge only against the evidence shown, never against outside knowledge.**
If you cannot tell from the evidence whether something is true, treat it as
unsupported.

For each answer fill in:

1. `correct` — `yes`, `partly` or `no`. Does the answer correctly answer the
   question, given the evidence? `partly` means some of it is right and some
   is wrong or missing.
2. `citation_support` — the column lists every citation in the answer as
   `#n=?`. Replace each `?` with `yes` if the evidence item numbered `#n`
   supports the sentence the citation sits on, otherwise `no`. Leave it empty
   if the answer has no citations.
3. `unsupported_details` — list every stated detail (an author, venue, date,
   year, amount, number, or a named finding) that you **cannot find in the
   evidence**, separated by `;`. Leave it empty if there are none.
4. `useful_1to5` — how useful would this answer be to a PI? 1 = useless or
   misleading, 3 = adequate, 5 = exactly what they needed.
5. `notes` — optional.

Rate each answer on its own. Two answers to the same question may appear; do
not compare them.

The second sheet, `removed_rater<k>.csv`, lists details and citations that an
automatic checker flagged in a draft answer, each shown in its sentence. Open
the evidence file and mark `supported` `yes` if the evidence supports that
detail (or, for a citation, if the cited item supports the sentence), `no` if
it does not or you cannot tell.

Please rate independently: do not discuss items with the other raters until
everyone has finished.
"""


def opaque(question_id, arm):
    return "R" + hashlib.sha256(f"{SALT}:{question_id}:{arm}".encode()).hexdigest()[:8].upper()


def load(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def evidence_a(row):
    parts = []
    for p in row["results"]:
        if p.get("content"):
            parts.append(f"### Function result: {p.get('name') or ''}\n\n{p['content']}")
    if row.get("extra"):
        parts.append("### Reference cards in view\n\n" + "\n\n".join(row["extra"]))
    refs = "\n".join(f"- #{e['n']}: {e.get('title', '')}" for e in row["refs"])
    return f"### Reference numbers in this conversation\n\n{refs}\n\n" + "\n\n".join(parts)


def evidence_b(row):
    return "\n\n".join(f"### Evidence {b['text']}" for b in row["evidence"])


def sentence_of(text, snippet):
    """The sentence holding ``snippet``; sentences end at '. ' / '! ' / '? ' or a
    line break, so a figure like 1.5 or a version like 3.1.4 never splits one."""
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        if snippet in part:
            return part.strip()
    return snippet


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="main")
    ap.add_argument("--raters", type=int, default=3)
    args = ap.parse_args()
    qs = {q["id"]: q for q in json.loads((HERE / "code" / "questions.json").read_text())["questions"]}
    a = {r["id"]: r for r in load(HERE / "data" / f"arm_a_{args.tag}.jsonl") if "error" not in r}
    b = {r["id"]: r for r in load(HERE / "data" / f"arm_b_{args.tag}.jsonl") if "error" not in r}
    sheets = HERE / "data" / "sheets"
    ev_dir = sheets / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    items, key, removed = [], [], []
    for qid, q in qs.items():
        for arm, rows, ev in (("a", a, evidence_a), ("b", b, evidence_b)):
            if qid not in rows:
                continue
            row = rows[qid]
            aid = opaque(qid, arm)
            text = row["final_text"]
            (ev_dir / f"{aid}.md").write_text(
                f"# {aid}\n\n## Question\n\n{q['text']}\n\n## Answer\n\n{text}\n\n## Evidence\n\n{ev(row)}\n")
            cites = sorted({int(n) for n in re.findall(r"#(\d+)", text)})
            items.append({"answer_id": aid, "question": q["text"], "answer": text,
                          "evidence_file": f"evidence/{aid}.md",
                          "correct": "", "citation_support": "; ".join(f"#{n}=?" for n in cites),
                          "unsupported_details": "", "useful_1to5": "", "notes": ""})
            key.append({"answer_id": aid, "question_id": qid, "category": q["category"], "arm": arm})
            if arm == "a":
                drafts = row.get("drafts") or []
                for v in row["verdicts"]:
                    if v.get("ok"):
                        continue
                    marks = list(v.get("unsupported") or []) + [f"#{n}" for n in (v.get("unmatched") or [])]
                    draft = next((d for d in drafts if marks and all(m in d for m in marks)),
                                 drafts[-1] if drafts else text)
                    for snippet in v.get("unsupported") or []:
                        removed.append({"aid": aid, "qid": qid, "kind": "detail", "flag": "unsupported",
                                        "action": v.get("action"), "item": snippet,
                                        "sentence": sentence_of(draft, snippet)})
                    for flag in ("unmatched", "unread"):
                        for n in v.get(flag) or []:
                            removed.append({"aid": aid, "qid": qid, "kind": "citation", "flag": flag,
                                            "action": v.get("action"), "item": f"#{n}",
                                            "sentence": sentence_of(draft, f"#{n}")})
                    if v.get("action") == "repair" and drafts:
                        (ev_dir / f"{aid}-draft.md").write_text(
                            f"# {aid} — the draft the checker judged (before its repair)\n\n{draft}\n")
    seen, unique = set(), []
    for r in removed:  # a repair verdict and the strip after it name the same item
        if (r["aid"], r["item"], r["flag"]) not in seen:
            seen.add((r["aid"], r["item"], r["flag"]))
            unique.append(r)
    removed = unique
    for k in range(1, args.raters + 1):
        rng = random.Random(f"{SALT}:rater:{k}")
        rows = items[:]
        rng.shuffle(rows)
        with (sheets / f"answers_rater{k}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        rem = removed[:]
        rng.shuffle(rem)
        with (sheets / f"removed_rater{k}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["removed_id", "kind", "item", "sentence",
                                               "evidence_file", "supported", "notes"])
            w.writeheader()
            for i, r in enumerate(rem):
                rid = "X" + hashlib.sha256(f"{SALT}:{r['aid']}:{r['item']}:{r['flag']}".encode()).hexdigest()[:8].upper()
                w.writerow({"removed_id": rid, "kind": r["kind"], "item": r["item"],
                            "sentence": r["sentence"], "evidence_file": f"evidence/{r['aid']}.md",
                            "supported": "", "notes": ""})
    with (HERE / "data" / "key.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["answer_id", "question_id", "category", "arm"])
        w.writeheader()
        w.writerows(key)
    with (HERE / "data" / "removed_key.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["removed_id", "answer_id", "question_id", "kind", "flag", "action", "item"])
        w.writeheader()
        for r in removed:
            rid = "X" + hashlib.sha256(f"{SALT}:{r['aid']}:{r['item']}:{r['flag']}".encode()).hexdigest()[:8].upper()
            w.writerow({"removed_id": rid, "answer_id": r["aid"], "question_id": r["qid"],
                        "kind": r["kind"], "flag": r["flag"], "action": r["action"], "item": r["item"]})
    (sheets / "RATER_INSTRUCTIONS.md").write_text(INSTRUCTIONS)
    print(json.dumps({"answers": len(items), "removed_items": len(removed), "raters": args.raters}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""EXP-2026-11-020 5c: a second model reads each regenerated answer against the
evidence its producer had, and lists every stated detail as supported or not.

    docker compose run … -e EVAL2_LLM_BASE_URL=… -e EVAL2_LLM_MODEL=… -e EVAL2_LLM_API_KEY=… \
        python docs/research/experiments/EXP-2026-11-020-agent-verifier-loop/code/reader.py [--conc 3]

Input: EXP-2026-11-013 Amendment 5 (``fix1``): 50 Mylo answers and 50
single-call answers, the blinded evidence files under ``data/sheets_fix1/``
(question, answer, the evidence that answer's producer read) and
``data/key_fix1.csv``. The reader sees the evidence and the answer, never the
arm. Output, one row per answer, ``data/reader_runs.jsonl``: the reader's
detail list, and the answer checker's flags on the same text and evidence
(``tools/agent/verify.unsupported`` and citation numbers that match nothing),
computed here so they can be compared. Temperature 0; one retry on an
unparseable reply; both replies kept.

Also writes ``data/sheets/calibration.csv`` (30 answers, ``random.Random(20261115)``
over the 100 answer ids sorted) for one person to mark the same way, and
``data/sheets/CALIBRATION_INSTRUCTIONS.md``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
R1 = EXP.parent / "EXP-2026-11-013-agent-answers-human-judged"
SHEETS = R1 / "data" / "sheets_fix1"

SYSTEM = (
    "You check a research assistant's answer against the evidence the assistant had in front of it. "
    "Judge only against the evidence shown, never against outside knowledge. If you cannot tell from "
    "the evidence whether a detail is true, it is unsupported."
)
PROMPT = """Evidence the assistant had:

{evidence}

Question: {question}

Answer to check:

{answer}

Go through the answer sentence by sentence. List every stated detail: an author, venue, date, year, amount, number, name, or a specific finding or property claimed about an item, project or person. Citation markers like #3 are not details. For each detail return an object with:
- "detail": the words from the answer, verbatim, at most 20 words;
- "where": "fact_line" if it sits on a line of the form "Label: value"; "figure" if it is a number, percentage or amount in running text; "sentence" if it is a name, date, venue or other specific value in running text that is not a figure; "claim" if it is a statement with no number (a finding, a property, a relationship);
- "supported": true if the evidence states it, false otherwise.
Return only a JSON array of these objects, nothing else. Return [] if the answer states no detail."""

CAL_INSTRUCTIONS = """# Calibration sheet — how to mark it

About 30 minutes. Each row of `calibration.csv` is one answer a research
assistant gave. Open its `evidence_file`: it shows the question, the answer and
**the evidence the assistant had**. The lab is fictional; the items are real.

Judge only against the evidence shown, never against outside knowledge. If you
cannot tell from the evidence whether a detail is true, treat it as
unsupported.

Fill in:

1. `n_details` — how many stated details the answer contains (an author,
   venue, date, year, amount, number, name, or a specific finding or property
   claimed about an item, project or person; citation markers like `#3` are
   not details).
2. `unsupported_details` — every detail you cannot find in the evidence,
   separated by `;`, each followed by its kind in brackets: `[fact_line]` (on a
   `Label: value` line), `[figure]` (a number or amount in a sentence),
   `[sentence]` (another specific value in a sentence), `[claim]` (a
   statement with no number). Leave empty if none.
3. `notes` — optional.

Mark each answer on its own. An automatic reader marked the same answers; its
marks are kept outside this folder until you finish.
"""


def ask_model(messages):
    base = os.environ["EVAL2_LLM_BASE_URL"].rstrip("/")
    body = json.dumps({"model": os.environ["EVAL2_LLM_MODEL"], "messages": messages,
                       "temperature": 0, "max_tokens": 6000}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {os.environ.get('EVAL2_LLM_API_KEY', '')}"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read())
    msg = data["choices"][0]["message"]
    return (msg.get("content") or ""), data.get("usage") or {}, data.get("model")


def parse(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        items = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(items, list):
        return None
    out = []
    for it in items:
        if isinstance(it, dict) and "detail" in it:
            out.append({"detail": str(it.get("detail")), "where": str(it.get("where") or ""),
                        "supported": bool(it.get("supported")) if not isinstance(it.get("supported"), str)
                        else it.get("supported").strip().lower() in ("true", "yes")})
    return out


def evidence_section(md: str) -> str:
    return md.split("## Evidence", 1)[1].strip() if "## Evidence" in md else md


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--sheet-only", action="store_true")
    args = ap.parse_args()
    key = list(csv.DictReader((R1 / "data" / "key_fix1.csv").open()))
    ids = sorted(r["answer_id"] for r in key)

    # calibration sheet (fixed draw; independent of the reader's output)
    rng = random.Random(20261115)
    cal = sorted(rng.sample(ids, 30))
    (EXP / "data" / "sheets").mkdir(parents=True, exist_ok=True)
    qtext = {}
    for row in key:
        md = (SHEETS / "evidence" / f"{row['answer_id']}.md").read_text()
        q = md.split("## Question", 1)[1].split("## Answer", 1)[0].strip()
        a = md.split("## Answer", 1)[1].split("## Evidence", 1)[0].strip()
        qtext[row["answer_id"]] = (q, a, md)
    with (EXP / "data" / "sheets" / "calibration.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["answer_id", "question", "answer", "evidence_file",
                                           "n_details", "unsupported_details", "notes"])
        w.writeheader()
        for aid in cal:
            q, a, _ = qtext[aid]
            w.writerow({"answer_id": aid, "question": q, "answer": a,
                        "evidence_file": f"../../../EXP-2026-11-013-agent-answers-human-judged/data/sheets_fix1/evidence/{aid}.md",
                        "n_details": "", "unsupported_details": "", "notes": ""})
    (EXP / "data" / "sheets" / "CALIBRATION_INSTRUCTIONS.md").write_text(CAL_INSTRUCTIONS)
    if args.sheet_only:
        print("calibration sheet written:", len(cal))
        return 0

    sys.path.insert(0, str(R1 / "code"))
    import mylo_turn

    mylo_turn.setup()
    from tools.agent import verify

    rows = {}
    for a in ("a", "b"):
        for r in map(json.loads, (R1 / "data" / f"arm_{a}_fix1.jsonl").read_text().splitlines()):
            rows[(r["id"], a)] = r
    out = EXP / "data" / "reader_runs.jsonl"
    done = set()
    if out.exists():
        done = {json.loads(x)["answer_id"] for x in out.read_text().splitlines() if x.strip()}
    todo = [k for k in key if k["answer_id"] not in done and (not args.only or k["answer_id"] in args.only.split(","))]
    lock = threading.Lock()

    def checker(row, arm, text):
        if arm == "a":
            source = verify.source_text(row.get("results") or [], row.get("extra") or [])
            known = {e["n"] for e in row.get("refs") or []}
        else:
            source = verify.source_text([{"content": b["text"]} for b in row.get("evidence") or []])
            known = {b["n"] for b in row.get("evidence") or []}
        return {"unsupported": verify.unsupported(text, source),
                "unmatched": [n for n in verify.cited(text) if n not in known]}

    def one(k):
        aid, qid, arm = k["answer_id"], k["question_id"], k["arm"]
        q, a, md = qtext[aid]
        row = rows[(qid, arm)]
        rec = {"answer_id": aid, "question_id": qid, "arm": arm, "category": k["category"],
               "evidence_chars": len(evidence_section(md)), "answer_chars": len(a)}
        rec["checker"] = checker(row, arm, row["final_text"])
        rec["loop_verdicts"] = row.get("verdicts") if arm == "a" else None
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": PROMPT.format(evidence=evidence_section(md), question=q, answer=a)}]
        replies = []
        for attempt in (1, 2):
            t0 = time.monotonic()
            try:
                text, usage, model = ask_model(messages)
                parsed = parse(text)
                replies.append({"attempt": attempt, "text": text[:20000], "usage": usage, "model": model,
                                "latency_s": round(time.monotonic() - t0, 2), "parsed": parsed is not None})
                if parsed is not None:
                    rec["details"] = parsed
                    break
            except Exception as exc:  # noqa: BLE001
                replies.append({"attempt": attempt, "error": f"{type(exc).__name__}: {exc}"[:300],
                                "latency_s": round(time.monotonic() - t0, 2)})
        rec["replies"] = replies
        rec["failed"] = "details" not in rec
        rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with lock, out.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        print(aid, arm, len(rec.get("details") or []), rec["failed"], flush=True)

    with ThreadPoolExecutor(max_workers=args.conc) as pool:
        list(pool.map(one, todo))
    return 0


if __name__ == "__main__":
    sys.exit(main())

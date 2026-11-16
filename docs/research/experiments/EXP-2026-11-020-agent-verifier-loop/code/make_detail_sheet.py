"""EXP-2026-11-020 Amendment 2: the short calibration sheet — one row per
detail, not per answer.

    python3 docs/research/experiments/EXP-2026-11-020-agent-verifier-loop/code/make_detail_sheet.py

Over the 30 calibration answers (``data/sheets/calibration.csv``), the 5c
reader's detail lists (``reader_runs.jsonl``, a failed row replaced by its
Amendment 1 re-read when that parsed): every detail the reader marked
unsupported, plus as many reader-supported details drawn with
``random.Random(20261116)`` from all of them (sorted by answer id, then list
order). Rows are shuffled with the same generator. Writes
``data/sheets/calibration_details.csv`` (what the person sees: no reader mark)
and ``data/sheets/calibration_details_key.csv`` (the reader's mark and the
stratum), and prints the counts.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
D = HERE / "data"
SEED = 20261116


def reader_rows() -> dict:
    runs = {json.loads(x)["answer_id"]: json.loads(x) for x in (D / "reader_runs.jsonl").open()}
    for x in (D / "reader_runs_amend1.jsonl").open():
        r = json.loads(x)
        if not r["failed"] and r.get("details") is not None:
            runs[r["answer_id"]] = r
    return runs


def main() -> int:
    runs = reader_rows()
    cal = [r["answer_id"] for r in csv.DictReader((D / "sheets" / "calibration.csv").open())]
    flagged, supported, unread = [], [], []
    for aid in sorted(cal):
        r = runs[aid]
        if r.get("details") is None:
            unread.append(aid)
            continue
        for i, d in enumerate(r["details"]):
            row = {"answer_id": aid, "index": i, "detail": d["detail"], "where": d["where"]}
            (supported if d["supported"] else flagged).append(row)
    rng = random.Random(SEED)
    sample = rng.sample(supported, len(flagged))
    rows = [dict(r, stratum="reader_unsupported") for r in flagged] + [dict(r, stratum="reader_supported_sample") for r in sample]
    rng.shuffle(rows)
    for k, r in enumerate(rows, 1):
        r["item"] = f"D{k:02d}"
    with (D / "sheets" / "calibration_details.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["item", "answer_id", "detail", "where", "judgement", "notes"])
        w.writeheader()
        for r in rows:
            w.writerow({"item": r["item"], "answer_id": r["answer_id"], "detail": r["detail"], "where": r["where"],
                        "judgement": "", "notes": ""})
    with (D / "sheets" / "calibration_details_key.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["item", "answer_id", "index", "stratum", "reader_supported"])
        w.writeheader()
        for r in rows:
            w.writerow({"item": r["item"], "answer_id": r["answer_id"], "index": r["index"], "stratum": r["stratum"],
                        "reader_supported": r["stratum"] == "reader_supported_sample"})
    print(json.dumps({"answers": len(cal), "answers_without_reader_list": unread,
                      "details_total": len(flagged) + len(supported), "reader_unsupported": len(flagged),
                      "reader_supported": len(supported), "sampled_supported": len(sample), "items": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

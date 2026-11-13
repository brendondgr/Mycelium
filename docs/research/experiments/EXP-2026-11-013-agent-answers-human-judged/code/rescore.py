"""EXP-2026-11-013 Amendment 3: re-check stored answers with the current verifier.

    python docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged/code/rescore.py

Run inside the backend (imports tools.agent.verify). Reads data/arm_a_<tag>.jsonl
and data/inject_<tag>.jsonl for tags main, rep2, rep3; writes data/rescore_v2.json.
Nothing is regenerated: the same texts against the same stored evidence.
"""

from __future__ import annotations

import difflib
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = sys.argv[1] if len(sys.argv) > 1 else "rescore_v2.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inject import check, wilson  # noqa: E402


def source_row(rows, copy):
    """The answer a copy was made from. ``inject_main.jsonl`` predates the
    question-id rename (Amendment 1), so its ``ta0N`` names either the paper
    question ``ta0N`` or the opportunity question now called ``to0N``: the copy
    is matched to whichever original its text came from."""
    qid = copy["answer"]
    candidates = [rows[qid]]
    if qid.startswith("ta") and "to" + qid[2:] in rows:
        candidates.append(rows["to" + qid[2:]])
    return max(candidates, key=lambda r: difflib.SequenceMatcher(
        None, r.get("final_text") or "", copy["text"], autojunk=False).ratio())


def main() -> int:
    import django

    django.setup()
    from tools.agent import verify

    out = {"tags": {}, "pooled": {}, "original_flags": [], "repaired_drafts": []}
    pooled = defaultdict(lambda: [0, 0, 0, 0])  # n, old, new, new on a clean original
    for tag in ("main", "rep2", "rep3"):
        rows = {}
        for line in (HERE / "data" / f"arm_a_{tag}.jsonl").open():
            r = json.loads(line)
            rows[r["id"]] = r
        per = defaultdict(lambda: [0, 0, 0, 0])
        originals = 0
        flagged = set()
        for qid, r in rows.items():
            if not r.get("final_text"):
                continue
            originals += 1
            got = check(verify, r, r["final_text"])
            if got["caught"]:
                flagged.add(qid)
                out["original_flags"].append({"tag": tag, "id": qid, **{k: got[k] for k in ("unmatched", "unread", "unsupported")}})
        # The drafts that triggered last night's repairs: is the flagged item
        # still flagged? (the draft holding it, as in analyse.py)
        for qid, r in rows.items():
            for v in r.get("verdicts") or []:
                if v.get("action") != "repair":
                    continue
                for draft in r.get("drafts") or []:
                    if all(item in draft for item in v.get("unsupported") or []):
                        got = check(verify, r, draft)
                        out["repaired_drafts"].append({"tag": tag, "id": qid, "flagged_then": v.get("unsupported"),
                                                       "flagged_now": got["unsupported"]})
                        break
        for line in (HERE / "data" / f"inject_{tag}.jsonl").open():
            c = json.loads(line)
            src = source_row(rows, c)
            got = check(verify, src, c["text"])
            for key in ((c["class"], c["placement"]), (c["class"], "all")):
                for bucket in (per, pooled):
                    b = bucket[key]
                    b[0] += 1
                    b[1] += bool(c["caught"])
                    b[2] += bool(got["caught"])
                    # caught on a copy whose original is itself flagged is the
                    # original's flag, not this error being found
                    b[3] += bool(got["caught"]) and src["id"] not in flagged
        out["tags"][tag] = {"originals": originals,
                            "cells": {f"{k[0]}|{k[1]}": {"n": v[0], "old": v[1], "new": v[2], "new_clean_original": v[3]} for k, v in sorted(per.items())}}
    out["pooled"] = {f"{k[0]}|{k[1]}": {"n": v[0], "old": v[1], "new": v[2], "new_ci": wilson(v[2], v[0]),
                         "new_clean_original": v[3]}
                     for k, v in sorted(pooled.items())}
    out["copies"] = sum(v["n"] for k, v in out["pooled"].items() if k.endswith("|all"))
    out["originals"] = sum(t["originals"] for t in out["tags"].values())
    (HERE / "data" / OUT).write_text(json.dumps(out, indent=1))
    for k, v in out["pooled"].items():
        print(f"{k:28s} n={v['n']:4d} old={v['old']:4d} new={v['new']:4d} clean={v['new_clean_original']:4d}")
    print("copies", out["copies"], "originals", out["originals"], "original flags", len(out["original_flags"]))
    for f in out["repaired_drafts"]:
        print(" REPAIRED", f)
    for f in out["original_flags"]:
        print(" FLAG", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

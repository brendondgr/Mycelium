"""EXP-2026-11-022: every number in RESULTS.md, from the logs.

    python3 docs/research/experiments/EXP-2026-11-022-gemma-empty-replies-replay/code/analyse.py

Reads ``logs/runs_<label>_s<seed>_<arm>.jsonl`` and ``logs/calls_…`` (dry runs
excluded), and the 2026-11-15 reference from EXP-2026-11-016 (its logs and its
Amendment-1 re-read, first repetition and all repetitions). Writes
``data/metrics.json``, ``data/metrics.csv``, ``tables/summary.md`` and
``tables/empty_calls.md``.
"""

from __future__ import annotations

import csv
import glob
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
G016 = HERE.parent / "EXP-2026-11-016-agent-gate-replication"


def wilson(k, n, z=1.96):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def reference():
    """2026-11-15: blank turns of EXP-2026-11-016's instance rows (Amendment 1)."""
    seen = {}
    for line in (G016 / "data" / "regrade_a1.jsonl").open():
        g = json.loads(line)
        seen[g["key"]] = g["reply_seen"]
    out = defaultdict(lambda: [0, 0])
    for f in sorted(glob.glob(str(G016 / "logs" / "runs_main_*_instance.jsonl"))):
        for line in open(f):
            r = json.loads(line)
            o = r["output"]
            key = f"{r['seed']}|{r['arm']}|{r['model']}|{r['task']}|{r['rep']}"
            text = seen.get(key, o.get("text") or "")
            refused = o.get("refused_at_open") or o.get("refused_at_send")
            blank = not refused and (bool(o.get("error")) or not text.strip())
            for k in [(r["arm"], "rep0" if r["rep"] == 0 else None), (r["arm"], "all"),
                      ("both", "rep0" if r["rep"] == 0 else None), ("both", "all")]:
                if k[1] is None:
                    continue
                out[k][0] += blank
                out[k][1] += 1
    return out


def main() -> int:
    runs, calls = defaultdict(list), defaultdict(list)
    for path in sorted((HERE / "logs").glob("runs_*.jsonl")):
        if path.stem.endswith("_dry"):
            continue
        label = re.match(r"runs_([a-z0-9]+)_s", path.name).group(1)
        runs[label] += [json.loads(x) for x in path.open()]
    for path in sorted((HERE / "logs").glob("calls_*.jsonl")):
        if path.stem.endswith("_dry"):
            continue
        label = re.match(r"calls_([a-z0-9]+)_s", path.name).group(1)
        calls[label] += [{**json.loads(x), "_file": path.name} for x in path.open()]

    values, rows_csv, table = {}, [], []
    ref = reference()
    for (arm, rep), (k, n) in sorted(ref.items()):
        values[f"ref_20261115.{arm}.{rep}.blank_turns"] = {"mean": k, "n": n, "ci95": wilson(k, n)}
        rows_csv.append(["ref_20261115", arm, rep, n, k, "", "", ""])
        if rep == "rep0":
            table.append(f"| 2026-11-15 (EXP-2026-11-016, rep 0) | {arm} | {n} | {k} | "
                         f"{k / n:.3f} {wilson(k, n)} | — | — |")
    empties_md = []
    for label in sorted(runs):
        rr, cc = runs[label], [c for c in calls[label] if c.get("task") != "warmup"]
        for arm in ("gate", "prompt_only", "both"):
            sel = [r for r in rr if arm == "both" or r["arm"] == arm]
            n = len(sel)
            blank = sum(r["blank"] for r in sel)
            err = sum(bool(r.get("error")) for r in sel)
            q = sum(bool(r.get("ended_on_question")) for r in sel)
            keys = {(r["seed"], r["task"], r["rep"]) for r in sel}
            arms = {r["arm"] for r in sel}
            seeds_files = {f"s{r['seed']}_{r['arm']}" for r in sel}
            csel = [c for c in cc if any(s in c["_file"] for s in seeds_files)]
            empty_calls = [c for c in csel if c["empty"]]
            turns_with_empty = {(c["_file"], c["task"], c["rep"]) for c in empty_calls}
            values[f"{label}.{arm}.blank_turns"] = {"mean": blank, "n": n, "ci95": wilson(blank, n)}
            values[f"{label}.{arm}.turns_with_empty_call"] = {"mean": len(turns_with_empty), "n": n}
            values[f"{label}.{arm}.empty_calls"] = {"mean": len(empty_calls), "n": len(csel)}
            values[f"{label}.{arm}.errors"] = {"mean": err, "n": n}
            values[f"{label}.{arm}.ended_on_question"] = {"mean": q, "n": n}
            rows_csv.append([label, arm, "rep0", n, blank, len(turns_with_empty), len(empty_calls), len(csel)])
            table.append(f"| {label} (replay) | {arm} | {n} | {blank} | "
                         f"{(blank / n if n else 0):.3f} {wilson(blank, n)} | "
                         f"{len(turns_with_empty)} | {len(empty_calls)} / {len(csel)} |")
            del keys, arms
        ec = [c for c in cc if c["empty"]]
        pos = Counter("after a function result" if c["after_tool"] else f"after {c['last_role']}" for c in ec)
        fin = Counter(str(c["finish"]) for c in ec)
        tok = Counter(str((c.get("usage") or {}).get("completion_tokens")) for c in ec)
        values[f"{label}.empty_calls_after_function_result"] = {
            "mean": sum(c["after_tool"] for c in ec), "n": len(ec)}
        short = [c for c in cc if c["after_tool"]
                 and ((c.get("usage") or {}).get("completion_tokens") or 99) <= 17]
        values[f"{label}.short_calls_after_function_result_dropped"] = {
            "mean": sum(c["empty"] for c in short), "n": len(short)}
        diag = [c for c in ec if c.get("diagnostic")]
        argless = [c for c in diag if re.fullmatch(
            r"\s*<\|tool_call>call:[A-Za-z0-9_]+\{\}<tool_call\|>\s*",
            str(c["diagnostic"].get("content") or ""))]
        values[f"{label}.diagnostic_is_one_argumentless_call"] = {"mean": len(argless), "n": len(diag)}
        unoffered = [c for c in argless if re.search(r"call:([A-Za-z0-9_]+)", c["diagnostic"]["content"])
                     .group(1) not in (c.get("offered") or [])]
        # How the turns that met an empty call ended.
        met = {(c["_file"], c["task"], c["rep"]) for c in ec}
        ends = Counter()
        for r in rr:
            if (f"calls_{label}_s{r['seed']}_{r['arm']}.jsonl", r["task"], r["rep"]) not in met:
                continue
            v = r["trace"].get("verdicts") or []
            ends["blank" if r["blank"] else "give_up_line" if "empty_gave_up" in v
                 else "question" if r.get("ended_on_question") else "answered"] += 1
        for k in ("blank", "give_up_line", "question", "answered"):
            values[f"{label}.turns_with_empty_call_ended.{k}"] = {"mean": ends[k], "n": len(met)}
        # The model call's identical retry: empty again?
        seq = defaultdict(list)
        for c in cc:
            seq[(c["_file"], c["task"], c["rep"])].append(c)
        firsts = again = 0
        for calls_of_turn in seq.values():
            for a, b in zip(calls_of_turn, calls_of_turn[1:]):
                if a["empty"] and b["n_messages"] == a["n_messages"]:
                    firsts += 1
                    again += b["empty"]
        values[f"{label}.identical_retry_empty_again"] = {"mean": again, "n": firsts}
        values[f"{label}.diagnostic_call_not_offered"] = {"mean": len(unoffered), "n": len(argless)}
        empties_md += [f"### {label}", "",
                       f"- empty calls: {len(ec)}; position: {dict(pos)}",
                       f"- finish reason: {dict(fin)}",
                       f"- completion tokens: {dict(tok)}", ""]
        diag = [c for c in ec if c.get("diagnostic")]
        if diag:
            empties_md += ["| file | task | after | offered has called fn? | diagnostic finish | diagnostic raw text (first 300 chars) |",
                           "|---|---|---|---|---|---|"]
            for c in diag:
                d = c["diagnostic"]
                raw = str(d.get("content") or "")
                m = re.search(r"call:([A-Za-z0-9_]+)", raw)
                has = "" if not m else ("yes" if m.group(1) in (c.get("offered") or []) else f"no ({m.group(1)})")
                cell = raw[:300].replace("|", "\\|").replace("\n", "\\n")
                empties_md.append(f"| {c['_file']} | {c['task']} | {c.get('last_name') or c['last_role']} | "
                                  f"{has} | {d.get('finish')} | `{cell}` |")
            empties_md.append("")

    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "data" / "metrics.json").write_text(json.dumps(values, indent=1) + "\n")
    with (HERE / "data" / "metrics.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["label", "arm", "rep", "turns", "blank_turns", "turns_with_empty_call",
                    "empty_calls", "calls"])
        w.writerows(rows_csv)
    head = ["| Run | Arm | Turns | Blank | Rate [Wilson 95%] | Turns with an empty call | Empty calls / calls |",
            "|---|---|---:|---:|---|---:|---|"]
    (HERE / "tables" / "summary.md").write_text("\n".join(head + table) + "\n")
    (HERE / "tables" / "empty_calls.md").write_text("\n".join(empties_md) + "\n")
    print("\n".join(head + table))
    print("\n".join(empties_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

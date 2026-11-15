"""EXP-2026-11-018: grade every answer against the frozen gold, by code only.

    python3 docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/grade.py [--runs data/runs.jsonl]

Standard library only; no model is involved. Writes ``data/graded.jsonl`` (one
row per job), ``data/metrics.json``, ``data/metrics.csv`` and
``tables/summary.md``.

Grading (fixed in PROTOCOL.md before the first answer):

- **Named objects (primary).** An answer names an object when it cites ``#n``
  and the harness resolves ``#n`` to that object's id: arms a and c through the
  thread's reference table, arm b through its numbered evidence. Only objects
  of the gold's kinds count (items of the gold's corpus types; people;
  projects).
- **Named objects (secondary, reported beside).** As primary, plus a gold
  object whose title, project name, or a person's first name or surname
  appears in the answer text. Secondary can only raise recall.
- **Values.** Dates, amounts and percentages are read by ``normalise.py``; a
  gold value is found when one stated value matches it. A stated value of the
  gold's type that matches nothing stored on the records involved (and is not
  today's date) counts against precision. Phrases (venue, author surnames,
  topics, interest labels, status facts) are found by folded substring; they
  carry no precision term.
- **Per question:** recall = found gold units / gold units; precision = right
  named units / named units (1 when nothing of a checked type is named); full
  credit only when both are 1.
- **Unanswerable:** ``states_fact`` when the question's fact pattern matches
  the answer; ``declines`` when the decline pattern matches; full credit when
  it declines and states no fact.
- A job's first non-failed attempt is graded; a job whose every attempt failed
  scores 0 and is counted under ``failed``.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))
import normalise as N  # noqa: E402

SEED = 20261115
BOOT = 10000
ANSWERABLE = ("field", "list", "project", "people", "join")
KINDS = ANSWERABLE + ("unanswerable",)
TYPE_RX = re.compile(r"\[(paper|grant|fellowship|conference)\]")


def cited_objects(row: dict) -> list[tuple]:
    """(kind, id, item_type) for every #n the answer cites that resolves."""
    text = row.get("final_text") or ""
    ns = {int(n) for n in re.findall(r"#(\d+)", text)}
    out = []
    if row["arm"] == "b":
        for ev in row.get("evidence") or []:
            if ev["n"] in ns:
                m = TYPE_RX.search(ev.get("text", "")[:300])
                out.append(("item", ev["key"], m[1] if m else None))
    else:
        for ref in row.get("refs") or []:
            if ref.get("n") in ns:
                t = TYPE_RX.search(ref.get("title") or "")
                out.append((ref.get("kind"), str(ref.get("key")), t[1] if t else None))
    return out


def name_hits(text: str, obj: dict) -> bool:
    if obj["kind"] == "person":
        parts = obj["name"].split(" ", 1)
        cands = [parts[0]] + ([parts[1]] if len(parts) > 1 else [])
        return any(N.has_phrase(text, c) for c in cands)
    if obj["kind"] == "project":
        return N.has_phrase(text, obj["name"])
    title = N.fold(obj.get("title") or "").strip()
    if len(title) < 8:
        return False
    words = title.split()
    stem = " ".join(words[:8])
    return f" {stem} " in N.fold(text)


def _allowed_date(found, allowed: list[str]) -> bool:
    for a in allowed:
        y, mo, d = (int(x) for x in a.split("-"))
        if found[1] == mo and found[2] == d and (found[0] is None or y == 0 or found[0] == y):
            return True
    return False


def grade_answerable(text: str, row: dict, gold: dict, secondary: bool) -> dict:
    objs = gold["objects"]
    vals = gold["values"]
    gold_ids = {(o["kind"], o["id"]) for o in objs}
    kinds = {o["kind"] for o in objs}
    types = {o.get("item_type") for o in objs if o["kind"] == "item"}
    named = {(k, i) for k, i, t in cited_objects(row)
             if k in kinds and (k != "item" or t in types or t is None)}
    if secondary:
        named |= {(o["kind"], o["id"]) for o in objs if name_hits(text, o)}
    found_obj = len(named & gold_ids)
    right_named = found_obj
    n_named = len(named)
    found_val = 0
    allowed = gold.get("allowed") or {}
    checked = {v["type"] for v in vals} & {"date", "amount", "percent"}
    for v in vals:
        if v["type"] == "phrase":
            found_val += any(N.has_phrase(text, a) for a in v["alts"])
        elif v["type"] == "date":
            found_val += any(N.date_matches(d, v["gold"]) for d in N.dates(text))
        elif v["type"] == "amount":
            found_val += any(N.amount_matches(a, v["gold"]) for a in N.amounts(text))
        elif v["type"] == "percent":
            found_val += any(abs(p - v["gold"]) < 0.5 for p in N.percents(text))
    if "date" in checked:
        ds = N.dates(text)
        n_named += len(ds)
        right_named += sum(_allowed_date(d, allowed.get("date", [])) for d in ds)
    if "amount" in checked:
        am = N.amounts(text)
        n_named += len(am)
        right_named += sum(any(N.amount_matches(a, g) for g in allowed.get("amount", [])) for a in am)
    if "percent" in checked:
        ps = N.percents(text)
        n_named += len(ps)
        right_named += sum(any(abs(p - g) < 0.5 for g in allowed.get("percent", [])) for p in ps)
    total = len(objs) + len(vals)
    recall = (found_obj + found_val) / total
    precision = right_named / n_named if n_named else 1.0
    return {"recall": round(recall, 4), "precision": round(precision, 4),
            "full": int(recall == 1 and precision == 1),
            "named": sorted(f"{k}:{i}" for k, i in named)}


DECLINE_V2 = False


def grade_unanswerable(text: str, gold: dict, patterns: dict) -> dict:
    u = gold["unanswerable"]
    if u["pattern"] == "AMOUNT":
        fact = bool(N.amounts(text))
    elif u["pattern"] == "PERCENT":
        fact = bool(N.percents(text))
    else:
        fact = bool(re.search(patterns[u["pattern"]], text, re.I))
    dec = N.declines(text, DECLINE_V2)
    return {"states_fact": int(fact), "declines": int(dec), "full": int(dec and not fact)}


def wilson(k: int, n: int, z: float = 1.96) -> list:
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def boot_mean(vals: list[float], seed: int) -> list:
    rng = random.Random(seed)
    n = len(vals)
    if not n:
        return [None, None]
    means = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOT))
    return [round(means[int(0.025 * BOOT)], 4), round(means[int(0.975 * BOOT) - 1], 4)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="data/runs.jsonl")
    ap.add_argument("--suffix", default="")
    # Amendment 1: grade each job's first attempt only (no retry).
    ap.add_argument("--first-attempt", action="store_true")
    # Amendment 2: the decline pattern also accepts "not visible".
    ap.add_argument("--decline-v2", action="store_true")
    args = ap.parse_args()
    global DECLINE_V2
    DECLINE_V2 = args.decline_v2
    gold_doc = json.loads((EXP / "data" / "gold.json").read_text())
    golds = {q["id"]: q for q in gold_doc["questions"]}
    path = EXP / args.runs
    if not path.exists() and (EXP / (args.runs + ".gz")).exists():
        path = EXP / (args.runs + ".gz")  # stored compressed (the record is > 10 MB as text)
    raw = gzip.decompress(path.read_bytes()).decode() if path.suffix == ".gz" else path.read_text()
    rows = [json.loads(x) for x in raw.splitlines() if x.strip()]
    jobs: dict[tuple, list] = {}
    for r in rows:
        if args.first_attempt and r.get("attempt", 1) != 1:
            continue
        jobs.setdefault((r["arm"], r["rep"], r["id"]), []).append(r)
    graded = []
    for (arm, rep, qid), attempts in sorted(jobs.items()):
        attempts.sort(key=lambda r: r.get("attempt", 1))
        ok = next((r for r in attempts if not r.get("failed")), None)
        q = golds[qid]
        base = {"arm": arm, "rep": rep, "id": qid, "kind": q["kind"],
                "attempts": len(attempts), "failed_attempts": sum(1 for r in attempts if r.get("failed")),
                "failed": ok is None,
                "asked_attempts": sum(1 for r in attempts if r.get("state") == "waiting"),
                "asked": ok is None and any(r.get("state") == "waiting" for r in attempts)}
        if ok is None:
            g = {"primary": {"recall": 0, "precision": 0, "full": 0} if q["kind"] != "unanswerable"
                 else {"states_fact": 0, "declines": 0, "full": 0}}
            g["secondary"] = g["primary"]
        else:
            text = ok.get("final_text") or ""
            if q["kind"] == "unanswerable":
                p = grade_unanswerable(text, q["gold"], gold_doc["patterns"])
                g = {"primary": p, "secondary": p}
            else:
                g = {"primary": grade_answerable(text, ok, q["gold"], False),
                     "secondary": grade_answerable(text, ok, q["gold"], True)}
            base.update({"wall_s": ok.get("wall_s"), "prompt_tokens": ok.get("prompt_tokens"),
                         "completion_tokens": ok.get("completion_tokens"),
                         "model_calls": ok.get("model_calls"), "function_calls": ok.get("function_calls"),
                         "repair": ok.get("repair"), "cited": ok.get("cited")})
        base.update(g)
        graded.append(base)
    (EXP / "data" / f"graded{args.suffix}.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in graded) + "\n")

    arms = sorted({g["arm"] for g in graded})
    qids = [q["id"] for q in gold_doc["questions"]]

    def per_q(arm, grading="primary", field="full"):
        out = {}
        for qid in qids:
            v = [g[grading][field] for g in graded if g["arm"] == arm and g["id"] == qid
                 and field in g[grading]]
            if v:
                out[qid] = statistics.mean(v)
        return out

    m: dict = {"n_jobs": len(graded), "n_rows": len(rows), "snapshot": gold_doc["snapshot"], "arms": {}}
    csv_rows = []
    for grading in ("primary", "secondary"):
        for arm in arms:
            runs = [g for g in graded if g["arm"] == arm]
            ans = [g for g in runs if g["kind"] in ANSWERABLE]
            un = [g for g in runs if g["kind"] == "unanswerable"]
            fq = per_q(arm, grading)
            k_full = sum(g[grading]["full"] for g in ans)
            entry = {
                "runs": len(runs), "failed_jobs": sum(g["failed"] for g in runs),
                "asked_jobs": sum(g["asked"] for g in runs),
                "asked_attempts": sum(g["asked_attempts"] for g in runs),
                "failed_attempts": sum(g["failed_attempts"] for g in runs),
                "answerable_full": {"k": k_full, "n": len(ans), "rate": round(k_full / len(ans), 4) if ans else None,
                                    "wilson95": wilson(k_full, len(ans)),
                                    "boot95_questions": boot_mean([fq[q] for q in fq if golds[q]["kind"] in ANSWERABLE], SEED)},
                "all_full": {"rate": round(statistics.mean(fq.values()), 4) if fq else None, "n_questions": len(fq)},
                "recall_mean": round(statistics.mean(g[grading]["recall"] for g in ans), 4) if ans else None,
                "precision_mean": round(statistics.mean(g[grading]["precision"] for g in ans), 4) if ans else None,
                "by_kind": {},
            }
            for kind in KINDS:
                kr = [g for g in runs if g["kind"] == kind]
                if not kr:
                    continue
                k = sum(g[grading]["full"] for g in kr)
                entry["by_kind"][kind] = {"k": k, "n": len(kr), "rate": round(k / len(kr), 4), "wilson95": wilson(k, len(kr))}
                csv_rows.append({"grading": grading, "arm": arm, "kind": kind, "metric": "full_credit",
                                 "k": k, "n": len(kr), "value": round(k / len(kr), 4),
                                 "lo": wilson(k, len(kr))[0], "hi": wilson(k, len(kr))[1]})
            sf = sum(g[grading]["states_fact"] for g in un)
            entry["unanswerable_states_fact"] = {"k": sf, "n": len(un), "rate": round(sf / len(un), 4) if un else None,
                                                 "wilson95": wilson(sf, len(un))}
            csv_rows.append({"grading": grading, "arm": arm, "kind": "unanswerable", "metric": "states_fact",
                             "k": sf, "n": len(un), "value": entry["unanswerable_states_fact"]["rate"],
                             "lo": wilson(sf, len(un))[0], "hi": wilson(sf, len(un))[1]})
            csv_rows.append({"grading": grading, "arm": arm, "kind": "answerable", "metric": "full_credit",
                             "k": k_full, "n": len(ans), "value": entry["answerable_full"]["rate"],
                             "lo": entry["answerable_full"]["boot95_questions"][0],
                             "hi": entry["answerable_full"]["boot95_questions"][1]})
            if grading == "primary":
                ok = [g for g in runs if not g["failed"]]
                entry["cost"] = {
                    "wall_s_median": round(statistics.median(g["wall_s"] for g in ok), 2) if ok else None,
                    "wall_s_mean": round(statistics.mean(g["wall_s"] for g in ok), 2) if ok else None,
                    "tokens_mean": round(statistics.mean((g["prompt_tokens"] or 0) + (g["completion_tokens"] or 0) for g in ok)) if ok else None,
                    "repairs": sum(1 for g in ok if g.get("repair")),
                }
            m["arms"].setdefault(grading, {})[arm] = entry

        def paired(a, b, subset):
            fa, fb = per_q(a, grading), per_q(b, grading)
            common = [q for q in qids if q in fa and q in fb and golds[q]["kind"] in subset]
            d = [fa[q] - fb[q] for q in common]
            if not d:
                return None
            return {"diff": round(statistics.mean(d), 4), "boot95": boot_mean(d, SEED), "n_questions": len(common),
                    "a": round(statistics.mean(fa[q] for q in common), 4),
                    "b": round(statistics.mean(fb[q] for q in common), 4)}

        comps = {}
        if {"a", "b"} <= set(arms):
            comps["a_minus_b_all"] = paired("a", "b", KINDS)
            comps["a_minus_b_answerable"] = paired("a", "b", ANSWERABLE)
            for kind in KINDS:
                comps[f"a_minus_b_{kind}"] = paired("a", "b", (kind,))
        if {"a", "c"} <= set(arms):
            comps["a_minus_c_project_people_join"] = paired("a", "c", ("project", "people", "join"))
            for kind in KINDS:
                comps[f"a_minus_c_{kind}"] = paired("a", "c", (kind,))
            comps["a_minus_c_all"] = paired("a", "c", KINDS)
        m.setdefault("comparisons", {})[grading] = comps
        for name, c in comps.items():
            if c:
                csv_rows.append({"grading": grading, "arm": name, "kind": "", "metric": "paired_diff_full",
                                 "k": "", "n": c["n_questions"], "value": c["diff"], "lo": c["boot95"][0], "hi": c["boot95"][1]})

    # claims, read from the primary grading exactly as PROTOCOL.md states them
    P = m["arms"].get("primary", {})
    C = m.get("comparisons", {}).get("primary", {})
    claims = {}
    if "a" in P:
        r = P["a"]["answerable_full"]["rate"]
        claims["a_full_credit_ge_70"] = {"value": r, "ci": P["a"]["answerable_full"]["boot95_questions"],
                                         "n": P["a"]["answerable_full"]["n"], "pass": r is not None and r >= 0.70}
        sf = P["a"]["unanswerable_states_fact"]
        claims["d_states_fact_le_10"] = {"value": sf["rate"], "ci": sf["wilson95"], "n": sf["n"],
                                         "pass": sf["rate"] is not None and sf["rate"] <= 0.10}
    if C.get("a_minus_b_all"):
        c = C["a_minus_b_all"]
        claims["b_a_beats_b"] = {"value": c["diff"], "ci": c["boot95"], "n": c["n_questions"], "pass": c["boot95"][0] > 0}
    if C.get("a_minus_c_project_people_join"):
        c = C["a_minus_c_project_people_join"]
        each = all((C.get(f"a_minus_c_{k}") or {}).get("diff", 0) > 0 for k in ("project", "people", "join"))
        claims["c_a_beats_c"] = {"value": c["diff"], "ci": c["boot95"], "n": c["n_questions"],
                                 "each_kind_positive": each,
                                 "pass": c["boot95"][0] > 0 and each, "partial": c["boot95"][0] > 0 and not each}
    m["claims"] = claims
    (EXP / "data" / f"metrics{args.suffix}.json").write_text(json.dumps(m, indent=1) + "\n")
    with (EXP / "data" / f"metrics{args.suffix}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["grading", "arm", "kind", "metric", "k", "n", "value", "lo", "hi"])
        w.writeheader()
        w.writerows(csv_rows)

    # table
    lines = ["| grading | arm | " + " | ".join(KINDS) + " | answerable full (95% CI, questions bootstrap) | unanswerable states a fact |",
             "|---|---|" + "---|" * len(KINDS) + "---|---|"]
    for grading in ("primary", "secondary"):
        for arm in arms:
            e = m["arms"][grading][arm]
            cells = [f"{e['by_kind'][k]['k']}/{e['by_kind'][k]['n']}" if k in e["by_kind"] else "–" for k in KINDS]
            af = e["answerable_full"]
            sf = e["unanswerable_states_fact"]
            lines.append(f"| {grading} | {arm} | " + " | ".join(cells)
                         + f" | {af['rate']} [{af['boot95_questions'][0]}, {af['boot95_questions'][1]}] (n={af['n']})"
                         + f" | {sf['k']}/{sf['n']} [{sf['wilson95'][0]}, {sf['wilson95'][1]}] |")
    lines += ["", "| grading | comparison | diff (full credit, per-question mean) | paired bootstrap 95% | questions |",
              "|---|---|---|---|---|"]
    for grading in ("primary", "secondary"):
        for name, c in (m.get("comparisons", {}).get(grading) or {}).items():
            if c:
                lines.append(f"| {grading} | {name} | {c['diff']:+.4f} | [{c['boot95'][0]:+.4f}, {c['boot95'][1]:+.4f}] | {c['n_questions']} |")
    (EXP / "tables").mkdir(exist_ok=True)
    (EXP / "tables" / f"summary{args.suffix}.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(claims, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

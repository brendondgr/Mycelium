"""EXP-2026-11-020: score 5a, 5b and 5c from the stored runs (standard library only).

    python3 docs/research/experiments/EXP-2026-11-020-agent-verifier-loop/code/analyse.py

Rules fixed in PROTOCOL.md before any run. Writes ``data/metrics.json``,
``data/metrics.csv`` and ``tables/summary.md``; reads only ``data/``.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import unicodedata
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
D = EXP / "data"


def fold(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold())


def wilson(k, n, z=1.96):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def upper_zero(n):
    """One-sided exact 95% upper bound on a rate when 0 of n were seen."""
    return round(1 - 0.05 ** (1 / n), 4) if n else None


def load(name):
    p = D / name
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def numbers(s):
    return [x.strip(".,") for x in re.findall(r"\d[\d,.]*", str(s or ""))]


# --- 5a ----------------------------------------------------------------------

def error_flagged(cls, token, v0):
    if cls == "cite":
        return int(token[1:]) in (v0.get("unmatched") or [])
    snippets = v0.get("unsupported") or []
    if cls == "figure":
        core = numbers(token)
        return any(c and c in s for s in snippets for c in core)
    return any(fold(token) in fold(s) for s in snippets)


def still_in(cls, token, row):
    text = row.get("final_text") or ""
    if cls == "cite":
        k = int(token[1:])
        if not re.search(rf"#{k}\b", text):
            return "absent"
        final_ns = {e["n"] for e in row.get("refs") or []}
        if k not in final_ns:
            return "still"
        return "rebound" if k not in set(row.get("orig_refs") or []) else "still"
    t = fold(token)
    return "still" if (t in fold(text) or t.lstrip("$€£ ") in fold(text)) else "absent"


def score_5a():
    rows = load("forced_runs.jsonl")
    per = []
    for r in rows:
        if "error" in r:
            per.append({"draft_id": r["draft_id"], "cls": r["cls"], "outcome": "harness_error", "error": r["error"]})
            continue
        vs = r.get("verdicts") or []
        v0 = vs[0] if vs else {}
        vlast = vs[-1] if vs else {}
        flagged_any = bool(v0) and not v0.get("ok", True)
        eflag = flagged_any and error_flagged(r["cls"], r["token"], v0)
        st = still_in(r["cls"], r["token"], r)
        if not eflag:
            outcome = "not_flagged"
        elif st == "still":
            outcome = "still_in_final"
        elif vlast.get("action") == "stripped":
            outcome = "removed_with_notice"
        elif v0.get("action") == "repair" and vlast.get("action") == "none":
            outcome = "repaired"
        else:
            outcome = "other"
        per.append({"draft_id": r["draft_id"], "cls": r["cls"], "outcome": outcome, "flagged_any": flagged_any,
                    "error_flagged": eflag, "token_in_final": st, "repair_s": r.get("repair_s"),
                    "repair_tokens": r.get("repair_tokens"), "real_calls": len(r.get("real_calls") or []),
                    "final_action": vlast.get("action"), "functions": r.get("functions")})
    # Exploratory (added after the run, in no claim): how much of the draft
    # the repaired answer keeps, by length.
    sample = {x["draft_id"]: x for x in load("forced_sample.jsonl")}
    for p, r in zip(per, rows):
        if "error" not in r and r["draft_id"] in sample:
            p["length_ratio"] = round(len(r.get("final_text") or "") / max(1, len(sample[r["draft_id"]]["draft"])), 3)
    out = {"n_rows": len(rows), "by_class": {}, "per_draft": per}
    for cls in ("cite", "figure", "factline", "all"):
        sub = [p for p in per if cls == "all" or p["cls"] == cls]
        fl = [p for p in sub if p["outcome"] not in ("not_flagged", "harness_error")]
        counts = {o: sum(1 for p in sub if p["outcome"] == o) for o in
                  ("repaired", "removed_with_notice", "still_in_final", "other", "not_flagged", "harness_error")}
        rebound = sum(1 for p in sub if p["token_in_final"] == "rebound")
        rs = [p["repair_s"] for p in fl if p.get("real_calls")]
        rt = [p["repair_tokens"] for p in fl if p.get("real_calls")]
        out["by_class"][cls] = {
            "drafts": len(sub), "flagged": len(fl), "counts": counts, "cite_rebound": rebound,
            "still_rate": round(counts["still_in_final"] / len(fl), 4) if fl else None,
            "still_upper95": upper_zero(len(fl)) if fl and counts["still_in_final"] == 0 else wilson(counts["still_in_final"], len(fl))[1],
            "repaired_rate": round(counts["repaired"] / len(fl), 4) if fl else None,
            "repaired_wilson95": wilson(counts["repaired"], len(fl)),
            "repair_s_median": round(statistics.median(rs), 2) if rs else None,
            "repair_s_mean": round(statistics.mean(rs), 2) if rs else None,
            "repair_tokens_median": round(statistics.median(rt)) if rt else None,
            "repair_tokens_mean": round(statistics.mean(rt)) if rt else None,
            "length_ratio_median": round(statistics.median(p["length_ratio"] for p in fl if "length_ratio" in p), 3) if fl else None,
            "final_under_half_of_draft": sum(1 for p in fl if p.get("length_ratio", 1) < 0.5),
            "repair_called_functions": sum(1 for p in fl if p.get("functions")),
        }
    return out


# --- 5b ----------------------------------------------------------------------

def score_5b():
    rows = load("unread_runs.jsonl")
    out = {"n_rows": len(rows)}
    for arm in ("surfaced", "read", "cleared"):
        sub = [r for r in rows if r["arm"] == arm]
        ok = [r for r in sub if "error" not in r]
        k = sum(1 for r in ok if r.get("flag_unread"))
        anyf = sum(1 for r in ok if r.get("flag_any"))
        out[arm] = {"runs": len(sub), "valid": len(ok), "errors": len(sub) - len(ok),
                    "flag_unread": k, "flag_unread_wilson95": wilson(k, len(ok)),
                    "flag_any": anyf}
    return out


# --- 5c ----------------------------------------------------------------------

def matches_checker(detail, snippets):
    d = fold(detail)
    for s in snippets:
        f = fold(s)
        if f and (f in d or d in f):
            return True
        if set(n for n in numbers(detail) if len(n) > 1) & set(n for n in numbers(s) if len(n) > 1):
            return True
    return False


KINDS = ("sentence", "fact_line", "figure", "claim", "other")


def merged_amend1():
    """Amendment 1: a row that failed at the 6,000-token cap is replaced by its
    re-read at the larger cap, when that re-read parsed."""
    rows = load("reader_runs.jsonl")
    again = {r["answer_id"]: r for r in load("reader_runs_amend1.jsonl") if not r.get("failed")}
    return [again.get(r["answer_id"], r) if r.get("failed") else r for r in rows]


def score_5c(rows=None):
    rows = load("reader_runs.jsonl") if rows is None else rows
    if not rows:
        return {"status": "not run"}
    out = {"n_rows": len(rows), "failed": sum(1 for r in rows if r.get("failed")), "by_arm": {}}
    for arm in ("a", "b"):
        sub = [r for r in rows if r["arm"] == arm and not r.get("failed")]
        per_answer = []
        tot = {k: {"details": 0, "unsupported": 0, "checker_flagged": 0} for k in KINDS}
        for r in sub:
            snippets = (r.get("checker") or {}).get("unsupported") or []
            uns = 0
            for d in r.get("details") or []:
                kind = d["where"] if d["where"] in KINDS[:-1] else "other"
                tot[kind]["details"] += 1
                if not d["supported"]:
                    uns += 1
                    tot[kind]["unsupported"] += 1
                    tot[kind]["checker_flagged"] += matches_checker(d["detail"], snippets)
            per_answer.append(uns)
        n = len(sub)
        with_any = sum(1 for u in per_answer if u > 0)
        all_uns = sum(v["unsupported"] for v in tot.values())
        all_flag = sum(v["checker_flagged"] for v in tot.values())
        checker_total = sum(len((r.get("checker") or {}).get("unsupported") or []) for r in sub)
        out["by_arm"][arm] = {
            "answers": n, "details": sum(v["details"] for v in tot.values()),
            "unsupported": all_uns, "unsupported_per_answer_mean": round(all_uns / n, 3) if n else None,
            "answers_with_unsupported": with_any, "answers_with_unsupported_wilson95": wilson(with_any, n),
            "by_kind": tot,
            "checker_flags_on_text": checker_total,
            "checker_recall_model_judged": round(all_flag / all_uns, 4) if all_uns else None,
            "checker_recall_wilson95": wilson(all_flag, all_uns),
        }
    # agreement with the calibration sheet, when a person has filled it
    cal = D / "sheets" / "calibration.csv"
    filled = [r for r in csv.DictReader(cal.open())] if cal.exists() else []
    filled = [r for r in filled if (r.get("n_details") or "").strip()]
    if filled:
        reader = {r["answer_id"]: r for r in rows if not r.get("failed")}
        pairs = []
        for r in filled:
            m = reader.get(r["answer_id"])
            if m is None:
                continue
            person = bool((r.get("unsupported_details") or "").strip())
            model = any(not d["supported"] for d in m.get("details") or [])
            pairs.append((person, model))
        n = len(pairs)
        agree = sum(1 for a, b in pairs if a == b)
        pa = sum(a for a, _ in pairs) / n
        pb = sum(b for _, b in pairs) / n
        pe = pa * pb + (1 - pa) * (1 - pb)
        kappa = (agree / n - pe) / (1 - pe) if pe < 1 else None
        out["calibration"] = {"filled": n, "agreement_any_unsupported": round(agree / n, 4), "cohen_kappa": kappa}
    else:
        out["calibration"] = {"filled": 0, "status": "not checked by a person"}
    return out


def main():
    m = {"5a": score_5a(), "5b": score_5b(), "5c": score_5c()}
    if load("reader_runs_amend1.jsonl"):
        m["5c_amend1"] = score_5c(merged_amend1())
    a = m["5a"]["by_class"]["all"]
    b = m["5b"]
    claims = {
        "a_never_reaches_final": {"still": a["counts"]["still_in_final"], "n_flagged": a["flagged"],
                                  "upper95": a["still_upper95"], "pass": a["flagged"] > 0 and a["counts"]["still_in_final"] == 0},
        "b_repair_at_least_half": {"repaired": a["counts"]["repaired"], "n_flagged": a["flagged"],
                                   "rate": a["repaired_rate"], "wilson95": a["repaired_wilson95"],
                                   "pass": a["repaired_rate"] is not None and a["repaired_rate"] >= 0.5},
        "c_unread_flags": {"surfaced_flagged": b.get("surfaced", {}).get("flag_unread"),
                           "surfaced_valid": b.get("surfaced", {}).get("valid"),
                           "read_flagged": b.get("read", {}).get("flag_unread"),
                           "read_valid": b.get("read", {}).get("valid"),
                           "pass": (b.get("surfaced", {}).get("flag_unread") or 0) >= 18
                           and b.get("read", {}).get("flag_unread") == 0
                           and b.get("surfaced", {}).get("valid") == 20 and b.get("read", {}).get("valid") == 20},
    }
    m["claims"] = claims
    (D / "metrics.json").write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    rows = []
    for cls, e in m["5a"]["by_class"].items():
        for o, k in e["counts"].items():
            rows.append({"part": "5a", "group": cls, "metric": o, "k": k, "n": e["drafts"], "value": round(k / e["drafts"], 4) if e["drafts"] else "", "lo": "", "hi": ""})
        rows.append({"part": "5a", "group": cls, "metric": "repaired_rate_of_flagged", "k": e["counts"]["repaired"], "n": e["flagged"],
                     "value": e["repaired_rate"], "lo": e["repaired_wilson95"][0], "hi": e["repaired_wilson95"][1]})
        rows.append({"part": "5a", "group": cls, "metric": "still_in_final_of_flagged", "k": e["counts"]["still_in_final"], "n": e["flagged"],
                     "value": e["still_rate"], "lo": 0, "hi": e["still_upper95"]})
        rows.append({"part": "5a", "group": cls, "metric": "repair_s_median", "k": "", "n": e["flagged"], "value": e["repair_s_median"], "lo": "", "hi": ""})
        rows.append({"part": "5a", "group": cls, "metric": "repair_tokens_median", "k": "", "n": e["flagged"], "value": e["repair_tokens_median"], "lo": "", "hi": ""})
        rows.append({"part": "5a", "group": cls, "metric": "exploratory_final_under_half_of_draft", "k": e["final_under_half_of_draft"], "n": e["flagged"],
                     "value": round(e["final_under_half_of_draft"] / e["flagged"], 4) if e["flagged"] else "",
                     "lo": wilson(e["final_under_half_of_draft"], e["flagged"])[0], "hi": wilson(e["final_under_half_of_draft"], e["flagged"])[1]})
    for arm in ("surfaced", "read", "cleared"):
        e = b.get(arm) or {}
        if e:
            rows.append({"part": "5b", "group": arm, "metric": "flag_unread", "k": e["flag_unread"], "n": e["valid"],
                         "value": round(e["flag_unread"] / e["valid"], 4) if e["valid"] else "",
                         "lo": e["flag_unread_wilson95"][0], "hi": e["flag_unread_wilson95"][1]})
    for part, c in (("5c", m["5c"]), ("5c_amend1", m.get("5c_amend1") or {})):
      for arm, e in (c.get("by_arm") or {}).items():
          rows.append({"part": part, "group": f"arm_{arm}", "metric": "unsupported_per_answer_mean", "k": e["unsupported"], "n": e["answers"],
                       "value": e["unsupported_per_answer_mean"], "lo": "", "hi": ""})
          rows.append({"part": part, "group": f"arm_{arm}", "metric": "answers_with_unsupported", "k": e["answers_with_unsupported"], "n": e["answers"],
                       "value": round(e["answers_with_unsupported"] / e["answers"], 4) if e["answers"] else "",
                       "lo": e["answers_with_unsupported_wilson95"][0], "hi": e["answers_with_unsupported_wilson95"][1]})
          rows.append({"part": part, "group": f"arm_{arm}", "metric": "checker_recall_model_judged", "k": "", "n": e["unsupported"],
                       "value": e["checker_recall_model_judged"], "lo": e["checker_recall_wilson95"][0], "hi": e["checker_recall_wilson95"][1]})
          for kind, t in e["by_kind"].items():
              rows.append({"part": part, "group": f"arm_{arm}:{kind}", "metric": "unsupported", "k": t["unsupported"], "n": t["details"],
                           "value": round(t["unsupported"] / t["details"], 4) if t["details"] else "", "lo": "", "hi": ""})
              rows.append({"part": part, "group": f"arm_{arm}:{kind}", "metric": "checker_flagged_of_unsupported", "k": t["checker_flagged"], "n": t["unsupported"],
                           "value": round(t["checker_flagged"] / t["unsupported"], 4) if t["unsupported"] else "",
                           "lo": wilson(t["checker_flagged"], t["unsupported"])[0], "hi": wilson(t["checker_flagged"], t["unsupported"])[1]})
    with (D / "metrics.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["part", "group", "metric", "k", "n", "value", "lo", "hi"])
        w.writeheader()
        w.writerows(rows)
    lines = ["| part | group | metric | k | n | value | 95% interval |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        ci = f"[{r['lo']}, {r['hi']}]" if r["lo"] != "" or r["hi"] != "" else ""
        lines.append(f"| {r['part']} | {r['group']} | {r['metric']} | {r['k']} | {r['n']} | {r['value']} | {ci} |")
    (EXP / "tables").mkdir(exist_ok=True)
    (EXP / "tables" / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(claims, indent=1))


if __name__ == "__main__":
    main()

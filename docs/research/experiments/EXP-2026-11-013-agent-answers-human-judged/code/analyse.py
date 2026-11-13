"""EXP-2026-11-013: the numbers that need no people.

    docker compose run --rm --no-deps -T backend uv run --no-sync --project web/backend \
        python docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged/code/analyse.py [--tag main]

Per arm and category: answers, errors, seconds, tokens, model and function
calls. For arm (a): verifier outcomes, and the exact repair-off counterfactual
(the loop's own give-up path applied to the stored first draft:
``strip_claims(strip(draft, unmatched), unsupported)``), the repair's cost
(tokens and seconds of the model calls after the draft), and what it
recovered. Merges the injected-error summary. Writes data/metrics.json,
data/metrics.csv, tables/summary.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent.parent


def load(p):
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def arm_stats(rows, arm):
    ok = [r for r in rows if "error" not in r]
    out = {"answers": len(ok), "errors": len(rows) - len(ok)}
    if not ok:
        return out
    tok = [(r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) for r in ok]
    out.update({
        "tokens_mean": round(st.mean(tok)), "tokens_median": st.median(tok), "tokens_max": max(tok),
        "seconds_mean": round(st.mean(r["wall_s"] for r in ok), 2),
        "seconds_median": round(st.median(r["wall_s"] for r in ok), 2),
        "seconds_max": round(max(r["wall_s"] for r in ok), 2),
        "answers_with_citation": sum(bool(r.get("cited")) for r in ok),
    })
    if arm == "a":
        out.update({
            "model_calls_mean": round(st.mean(r["model_calls"] for r in ok), 2),
            "function_calls_mean": round(st.mean(r["function_calls"] for r in ok), 2),
            "hit_max_steps": sum(r["hit_max_steps"] for r in ok),
            "thrash_stop": sum(r["thrash_stop"] for r in ok),
            "repair_runs": sum(r["repair"] for r in ok),
            "final_stripped": sum(1 for r in ok if r["removed"] or r["removed_claims"]),
            "final_clean": sum(1 for r in ok if r["verdicts"] and r["verdicts"][-1].get("action") == "none"),
            "empty_answers": sum(1 for r in ok if not (r.get("final_text") or "").strip()),
        })
    return out


def repair_off(rows):
    from tools.agent import verify

    out = []
    for r in rows:
        if "error" in r or not r.get("repair"):
            continue
        first = next(v for v in r["verdicts"] if v.get("action") == "repair")
        draft = (r.get("drafts") or [""])[0]
        off = draft
        if first.get("unmatched"):
            off = verify.strip(off, first["unmatched"])
        if first.get("unsupported"):
            off = verify.strip_claims(off, first["unsupported"])
        final_v = r["verdicts"][-1]
        # Per-call function counts were recorded as 0 by a harness bug before
        # the fix of 2026-11-12 23:42 (see ISSUES.md); the repair's cost is then
        # unknown rather than guessed.
        known = any(c["function_calls"] for c in r["calls"])
        idx = next((i for i, c in enumerate(r["calls"]) if c["function_calls"] == 0), None) if known else None
        after = r["calls"][idx + 1:] if idx is not None else None
        kept = [s for s in first.get("unsupported") or [] if s in (r.get("final_text") or "")]
        out.append({
            "id": r["id"], "category": r["category"],
            "flagged_unmatched": len(first.get("unmatched") or []),
            "flagged_unread": len(first.get("unread") or []),
            "flagged_unsupported": len(first.get("unsupported") or []),
            "draft_chars": len(draft), "off_chars": len(off),
            "final_chars": len(r.get("final_text") or ""),
            "off_removed_chars": len(draft) - len(off),
            "final_ok": bool(final_v.get("ok")), "final_action": final_v.get("action"),
            "flagged_details_kept_in_final": len(kept),
            "repair_tokens": sum((c["prompt_tokens"] or 0) + (c["completion_tokens"] or 0) for c in after) if after is not None else None,
            "repair_seconds": round(sum(c["latency_s"] for c in after), 2) if after is not None else None,
            "repair_model_calls": len(after) if after is not None else None,
            "off_text": off, "draft_text": draft,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="main")
    args = ap.parse_args()
    import mylo_turn

    mylo_turn.setup()
    a = load(HERE / "data" / f"arm_a_{args.tag}.jsonl")
    b = load(HERE / "data" / f"arm_b_{args.tag}.jsonl")
    metrics = {"tag": args.tag, "arm_a": arm_stats(a, "a"), "arm_b": arm_stats(b, "b"),
               "by_category": {}}
    for cat in sorted({r["category"] for r in a}):
        metrics["by_category"][cat] = {"a": arm_stats([r for r in a if r["category"] == cat], "a"),
                                       "b": arm_stats([r for r in b if r["category"] == cat], "b")}
    rep = repair_off(a)
    (HERE / "data" / f"repair_off_{args.tag}.json").write_text(json.dumps(rep, indent=1))
    if rep:
        metrics["repair"] = {
            "repaired_turns": len(rep),
            "repair_succeeded_final_clean": sum(r["final_ok"] for r in rep),
            "turns_where_off_would_remove_text": sum(r["off_removed_chars"] > 0 for r in rep),
            "turns_with_flagged_details_kept_after_repair": sum(r["flagged_details_kept_in_final"] > 0 for r in rep),
            "repair_tokens_mean": (round(st.mean(x)) if (x := [r["repair_tokens"] for r in rep if r["repair_tokens"] is not None]) else None),
            "repair_seconds_mean": (round(st.mean(x), 2) if (x := [r["repair_seconds"] for r in rep if r["repair_seconds"] is not None]) else None),
            "repair_model_calls_mean": (round(st.mean(x), 2) if (x := [r["repair_model_calls"] for r in rep if r["repair_model_calls"] is not None]) else None),
            "repair_cost_known_turns": sum(r["repair_tokens"] is not None for r in rep),
            "flags": {k: sum(r[f"flagged_{k}"] for r in rep) for k in ("unmatched", "unread", "unsupported")},
        }
    inj = HERE / "data" / f"inject_{args.tag}_summary.json"
    if inj.exists():
        metrics["injected"] = json.loads(inj.read_text())
    suffix = "" if args.tag == "main" else f"_{args.tag}"
    (HERE / "data" / f"metrics{suffix}.json").write_text(json.dumps(metrics, indent=1))
    flat = []
    for arm in ("a", "b"):
        flat.append({"scope": "all", "arm": arm, **metrics[f"arm_{arm}"]})
        for cat, v in metrics["by_category"].items():
            flat.append({"scope": cat, "arm": arm, **v[arm]})
    keys = sorted({k for r in flat for k in r})
    with (HERE / "data" / f"metrics{suffix}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(flat)
    lines = ["| Scope | Arm | Answers | Mean s | Median s | Max s | Mean tokens | Max tokens |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in flat:
        lines.append(f"| {r['scope']} | {r['arm']} | {r.get('answers')} | {r.get('seconds_mean')} | "
                     f"{r.get('seconds_median')} | {r.get('seconds_max')} | {r.get('tokens_mean')} | {r.get('tokens_max')} |")
    if "injected" in metrics:
        lines += ["", "| Injected class | Copies | Caught | Recall | 95% CI | in place | prose | fact line |",
                  "|---|---:|---:|---:|---|---|---|---|"]
        for cls, v in metrics["injected"]["classes"].items():
            cell = lambda p: (f"{v[p]['caught']}/{v[p]['n']}" if p in v else "—")  # noqa: E731
            lines.append(f"| {cls} | {v['n']} | {v['caught']} | {v['recall']} | {v['recall_ci95']} | "
                         f"{cell('inplace')} | {cell('prose')} | {cell('factline')} |")
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / f"summary{suffix}.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "by_category"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""EXP-2026-11-018 Amendment 8, item 6: counts read from a run's rows, with no
new grader. Standard library only.

    python3 docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/r5_counts.py r5 [r4 r4g …]

For each tag it reads ``data/runs_<tag>.jsonl[.gz]`` and ``data/graded_<tag>.jsonl``
and writes ``data/counts_<tag>.json``; ``tables/counts.md`` holds every tag
given, side by side. Arm (a) only. "Rows" are every recorded attempt (a retried
job has two); "jobs" take a job's last attempt, as the grader does.
"""

from __future__ import annotations

import collections
import gzip
import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent


def read(tag):
    p = EXP / "data" / f"runs_{tag}.jsonl"
    opener = open if p.exists() else gzip.open
    p = p if p.exists() else p.with_name(p.name + ".gz")
    with opener(p, "rt") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def counts(tag):
    rows = [r for r in read(tag) if r["arm"] == "a"]
    graded = [json.loads(x) for x in (EXP / "data" / f"graded_{tag}.jsonl").open()]
    graded = [g for g in graded if g["arm"] == "a"]
    jobs = {}
    for r in rows:
        jobs[(r["id"], r["rep"])] = r  # the last attempt
    full = {(g["id"], g["rep"]): g["primary"]["full"] for g in graded if g["kind"] != "unanswerable"}
    attempts = collections.defaultdict(list)
    for r in rows:
        attempts[(r["id"], r["rep"])].append(bool(r.get("failed")))
    failed_both = sorted(f"{q}:{rep}" for (q, rep), a in attempts.items() if all(a))
    by_q = collections.defaultdict(lambda: [0, 0])
    for g in graded:
        by_q[g["id"]][0] += g["primary"]["full"]
        by_q[g["id"]][1] += 1
    denied_jobs = [k for k, r in jobs.items() if r.get("denied")]
    with_d = [full[k] for k in denied_jobs if k in full]
    without = [full[k] for k, r in jobs.items() if not r.get("denied") and k in full]
    shapes = collections.Counter(" > ".join((jobs[k].get("functions") or [])[:4]) for k in denied_jobs)

    def text(r):
        return json.dumps(r.get("results") or []) + json.dumps(r.get("errors") or [])

    by_kind = collections.defaultdict(lambda: [0, 0])
    for g in graded:
        by_kind[g["kind"]][0] += g["primary"]["full"]
        by_kind[g["kind"]][1] += 1
    return {
        "tag": tag,
        "arm_a_rows": len(rows),
        "arm_a_jobs": len(jobs),
        "jobs_failed_both_attempts": failed_both,
        "rows_with_a_denied_call": sum(1 for r in rows if r.get("denied")),
        "jobs_with_a_denied_call": len(denied_jobs),
        "full_credit_answerable_jobs_with_denied": [sum(with_d), len(with_d)],
        "full_credit_answerable_jobs_without_denied": [sum(without), len(without)],
        "denied_jobs_first_calls": shapes.most_common(5),
        "jobs_with_a_call_past_the_step_limit": sum(1 for r in jobs.values() if "too_many_calls" in text(r)),
        "jobs_ended_by_fit_final": sum(
            1 for r in jobs.values() if any((v or {}).get("action") == "fit_final" for v in r.get("verdicts") or [])
        ),
        "jobs_whose_final_text_is_call_markup": sorted(
            f"{q}:{rep}" for (q, rep), r in jobs.items() if "tool_call" in (r.get("final_text") or "")
        ),
        "max_function_calls_in_a_job": max((r.get("function_calls") or 0) for r in jobs.values()),
        "jobs_with_more_than_12_function_calls": sum(1 for r in jobs.values() if (r.get("function_calls") or 0) > 12),
        "jobs_using_load_functions": sum(1 for r in jobs.values() if "load_functions" in (r.get("functions") or [])),
        "full_credit_by_kind": {k: v for k, v in sorted(by_kind.items())},
        "questions_below_full_credit": {q: f"{v[0]}/{v[1]}" for q, v in sorted(by_q.items()) if v[0] < v[1]},
    }


def main(tags) -> int:
    out = [counts(t) for t in tags]
    for c in out:
        (EXP / "data" / f"counts_{c['tag']}.json").write_text(json.dumps(c, indent=1) + "\n")
    rows = [
        ("Arm (a) jobs / rows", lambda c: f"{c['arm_a_jobs']} / {c['arm_a_rows']}"),
        ("Jobs failed on both attempts", lambda c: f"{len(c['jobs_failed_both_attempts'])} ({', '.join(c['jobs_failed_both_attempts']) or 'none'})"),
        ("Rows with a denied call", lambda c: f"{c['rows_with_a_denied_call']} of {c['arm_a_rows']}"),
        ("Full credit, answerable jobs with a denied call", lambda c: "{} of {}".format(*c["full_credit_answerable_jobs_with_denied"])),
        ("Full credit, answerable jobs with none", lambda c: "{} of {}".format(*c["full_credit_answerable_jobs_without_denied"])),
        ("Jobs with a call past the step limit", lambda c: str(c["jobs_with_a_call_past_the_step_limit"])),
        ("Jobs ended by answering from what fits", lambda c: str(c["jobs_ended_by_fit_final"])),
        ("Jobs whose final text is call markup", lambda c: f"{len(c['jobs_whose_final_text_is_call_markup'])} ({', '.join(c['jobs_whose_final_text_is_call_markup']) or 'none'})"),
        ("Most function calls in one job", lambda c: str(c["max_function_calls_in_a_job"])),
        ("Jobs with more than 12 function calls", lambda c: str(c["jobs_with_more_than_12_function_calls"])),
        ("Jobs that used load_functions", lambda c: f"{c['jobs_using_load_functions']} of {c['arm_a_jobs']}"),
        ("Questions below full credit", lambda c: ", ".join(f"{q} {v}" for q, v in c["questions_below_full_credit"].items())),
    ]
    lines = ["<!-- generated by code/r5_counts.py; do not edit -->", "",
             "| Count (arm a) | " + " | ".join(f"`{c['tag']}`" for c in out) + " |",
             "|---|" + "---|" * len(out)]
    lines += [f"| {name} | " + " | ".join(fn(c) for c in out) + " |" for name, fn in rows]
    (EXP / "tables" / "counts.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["r5"]))

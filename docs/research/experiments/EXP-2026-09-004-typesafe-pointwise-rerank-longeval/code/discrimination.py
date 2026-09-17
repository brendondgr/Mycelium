"""Can the model separate relevant from irrelevant at all? Read from the dumps.

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/discrimination.py

The C-016 measurements from `EXP-2026-08-008/code/llm_diagnosis.py`, applied to
the TypeSafe arms' raw answers (`eval/runs/typesafe_*_answers.json`):

1. distinct values per 20-candidate window, mean over queries;
2. mean value by judged grade (0, 1, 2), which must be monotonic;
3. the share of adjacent within-window pairs the model actually ordered
   (distinct values) versus the base-rank tiebreak;
4. agreement between the two arms: mean top-10 Jaccard of their run files.

Also sums the dumps' token counts and prices them at the list rate.

Writes `tables/discrimination.md` and `data/discrimination.json`.
"""

from __future__ import annotations

import gzip
import json
import os
import statistics
import sys
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

RUNS = REPO_ROOT / "eval" / "runs"
PRICE_PER_MILLION_INPUT_USD = 0.042
PRICE_READ_ON = "2026-09-17"
COLLECTION = "sci-2026-train"
QRELS = "dctr"


def newest(pattern: str) -> Path | None:
    hits = sorted(RUNS.glob(pattern), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def read_run(path: Path) -> dict[str, list[str]]:
    ranking: dict[str, list[str]] = defaultdict(list)
    with gzip.open(path, "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 3:
                ranking[parts[0]].append(parts[2])
    return dict(ranking)


def main() -> int:
    import django

    django.setup()
    from harness import datasets

    collection = datasets.load_collections()[COLLECTION]
    dataset = datasets.load_dataset(collection, QRELS)
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for q in dataset.qrels_iter():
        qrels[q.query_id][q.doc_id] = int(q.relevance)

    out: dict = {"price_per_million_input_usd": PRICE_PER_MILLION_INPUT_USD, "price_read_on": PRICE_READ_ON}
    lines = ["# Discrimination — the C-016 measurements on the TypeSafe arms", ""]
    runs: dict[str, dict[str, list[str]]] = {}
    for arm in ("noul", "score"):
        dump_path = RUNS / f"typesafe_{arm}_answers.json"
        if not dump_path.exists():
            lines.append(f"*`typesafe_{arm}`: no dump found; arm not run.*")
            continue
        dump = json.loads(dump_path.read_text())
        distinct_per_query, decided_share, by_grade = [], [], defaultdict(list)
        for qid, rows in dump["answers"].items():
            values = [r["value"] for r in rows if r.get("value") is not None]
            if len(values) < 2:
                continue
            distinct_per_query.append(len({round(v, 3) for v in values}))
            ordered = sorted(values, reverse=True)
            adjacent = list(pairwise(ordered))
            decided_share.append(sum(1 for a, b in adjacent if a != b) / len(adjacent))
            for r in rows:
                if r.get("value") is None:
                    continue
                grade = qrels.get(qid, {}).get(r["doc_id"], 0)
                by_grade[grade].append(r["value"])
        grade_means = {g: statistics.fmean(v) for g, v in sorted(by_grade.items())}
        grades = sorted(grade_means)
        monotonic = all(grade_means[a] <= grade_means[b] for a, b in pairwise(grades))
        tokens = dump["input_tokens"]
        result = {
            "pairs": dump["pairs"], "answered": dump["answered"], "failed": dump["failed"],
            "distinct_values_per_query_mean": statistics.fmean(distinct_per_query) if distinct_per_query else None,
            "model_decided_adjacent_share": statistics.fmean(decided_share) if decided_share else None,
            "mean_value_by_grade": {str(g): round(m, 4) for g, m in grade_means.items()},
            "n_by_grade": {str(g): len(v) for g, v in sorted(by_grade.items())},
            "monotonic_in_grade": monotonic,
            "input_tokens": tokens, "output_tokens": dump["output_tokens"],
            "cost_usd": round(tokens / 1e6 * PRICE_PER_MILLION_INPUT_USD, 4),
            "model": dump["model"], "base": dump["base"], "window": dump["window"],
        }
        out[f"typesafe_{arm}"] = result
        lines += [
            f"## `typesafe_{arm}` over `{dump['base']}`, window {dump['window']}, `{dump['model']}`", "",
            "| measure | value |", "|---|---:|",
            f"| pairs answered / failed | {result['answered']} / {result['failed']} |",
            f"| distinct values per query (mean) | {result['distinct_values_per_query_mean']:.2f} |",
            f"| adjacent within-window pairs the model ordered | {result['model_decided_adjacent_share']:.3f} |",
            f"| mean value by grade | {result['mean_value_by_grade']} (n {result['n_by_grade']}) |",
            f"| monotonic in grade | {'yes' if monotonic else '**no**'} |",
            f"| input tokens / cost at list price | {tokens:,} / ${result['cost_usd']:.4f} |",
            "",
        ]
        run_path = newest(f"*__typesafe_{arm}__pooled__*.txt.gz")
        if run_path:
            runs[arm] = read_run(run_path)

    if len(runs) == 2:
        jaccards = []
        for qid in set(runs["noul"]) & set(runs["score"]):
            a, b = set(runs["noul"][qid][:10]), set(runs["score"][qid][:10])
            if a or b:
                jaccards.append(len(a & b) / len(a | b))
        out["top10_jaccard_noul_vs_score_mean"] = statistics.fmean(jaccards) if jaccards else None
        lines += [
            "## Agreement between the two framings", "",
            (
                f"Mean top-10 Jaccard, `typesafe_noul` vs `typesafe_score`: "
                f"**{out['top10_jaccard_noul_vs_score_mean']:.3f}** over {len(jaccards)} queries."
            ),
            "",
        ]

    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables" / "discrimination.md").write_text("\n".join(lines) + "\n")
    (EXP_DIR / "data" / "discrimination.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

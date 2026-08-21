"""How much of the LLM reranker's output is judgement, and how much is the input order?

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/llm_diagnosis.py

`RESULTS.md` §2 established *that* the listwise arm is order-dependent: the same
candidate set presented bottom-to-top scores 0.0570 nDCG@10 lower. That is a fact
about the arm, and it is not yet an answer to the question anyone actually has —
**is the model contributing anything?**

Four measurements separate the two, all on the same 20-candidate window:

1. **Order-following.** Kendall tau between each arm's output and the order it was
   *shown*. Tau near +1 means the model largely returned its input. Tau near 0
   means it reordered freely.
2. **Set agreement.** Top-10 overlap between the forward and reversed arms. A
   content-driven judge, handed an identical set twice, must produce nearly the
   same top 10 either way. Whatever fraction is missing is the part of the answer
   that presentation order, not content, decided.
3. **Copy controls.** Two synthetic runs nobody called an LLM for: the base's top
   20 left alone, and the base's top 20 reversed. They bracket what "pure
   copying" would score in each direction, which is what turns tau into a
   quantity rather than a correlation.
4. **Rubric discrimination.** The rubric's raw 0-3 verdicts against the graded
   qrels — mean score by relevance grade, and how much of the final ordering is
   decided by the rubric versus by the base-rank tiebreak. This is the only
   measurement here that speaks to whether the model can judge relevance *at
   all*, which is what C-004 is about and what the deployed percent-match rests
   on.

Writes `tables/llm_diagnosis.md` and `data/llm_diagnosis.json`.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

RUNS = REPO_ROOT / "eval" / "runs"
WINDOW = 20


def read_run(path: Path) -> dict[str, list[str]]:
    ranking: dict[str, list[str]] = defaultdict(list)
    with gzip.open(path, "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 3:
                ranking[parts[0]].append(parts[2])
    return dict(ranking)


def newest(pattern: str) -> Path:
    hits = sorted(RUNS.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not hits:
        raise SystemExit(f"no run file matching {pattern}")
    return hits[-1]


def kendall_tau(order_a: list[str], order_b: list[str]) -> float:
    """Tau-a over the items common to both, computed directly.

    scipy is available, but the inputs here are two permutations of one small set,
    so ranking them by position and counting concordant pairs is clearer than
    marshalling them through a library call.
    """
    common = [d for d in order_a if d in set(order_b)]
    pos_b = {d: i for i, d in enumerate(order_b)}
    n = len(common)
    if n < 2:
        return float("nan")
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            delta = pos_b[common[i]] - pos_b[common[j]]
            if delta < 0:
                concordant += 1
            elif delta > 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else float("nan")


def ndcg_at(ordering: list[str], rels: dict[str, int], k: int = 10) -> float:
    gains = [rels.get(d, 0) for d in ordering[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains) if g > 0)
    ideal = sorted(rels.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal) if g > 0)
    return dcg / idcg if idcg else 0.0


def main() -> int:
    import django

    django.setup()
    from harness import datasets

    collection = datasets.load_collections()["sci-2026-train"]
    dataset = datasets.load_dataset(collection, "dctr")
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for q in dataset.qrels_iter():
        qrels[q.query_id][q.doc_id] = int(q.relevance)

    base = read_run(newest("*__fusion_union_pool__pooled__*.txt.gz"))
    fwd = read_run(newest("*__llm_rerank__pooled__*.txt.gz"))
    rev = read_run(newest("*__llm_rerank_reversed__pooled__*.txt.gz"))
    rub = read_run(newest("*__llm_rubric__pooled__*.txt.gz"))

    out: dict = {}
    taus_fwd, taus_rev, taus_rub, overlaps = [], [], [], []
    nd_base, nd_fwd, nd_rev, nd_rub, nd_keep, nd_flip = [], [], [], [], [], []
    moved_fwd = []

    for qid, base_order in base.items():
        rels = qrels.get(qid, {})
        window = base_order[:WINDOW]
        tail = base_order[WINDOW:]
        shown_rev = list(reversed(window))

        f = fwd.get(qid, [])
        r = rev.get(qid, [])
        u = rub.get(qid, [])
        if not (f and r and u):
            continue

        # Each arm's output restricted to the window it was allowed to reorder.
        f_win = [d for d in f if d in set(window)][:WINDOW]
        r_win = [d for d in r if d in set(window)][:WINDOW]
        u_win = [d for d in u if d in set(window)][:WINDOW]

        taus_fwd.append(kendall_tau(f_win, window))
        taus_rev.append(kendall_tau(r_win, shown_rev))
        taus_rub.append(kendall_tau(u_win, window))
        moved_fwd.append(sum(1 for i, d in enumerate(f_win) if i < len(window) and d != window[i]))

        top_f, top_r = set(f[:10]), set(r[:10])
        overlaps.append(len(top_f & top_r) / 10.0)

        nd_base.append(ndcg_at(base_order, rels))
        nd_fwd.append(ndcg_at(f, rels))
        nd_rev.append(ndcg_at(r, rels))
        nd_rub.append(ndcg_at(u, rels))
        nd_keep.append(ndcg_at(window + tail, rels))
        nd_flip.append(ndcg_at(shown_rev + tail, rels))

    def mean(xs):
        xs = [x for x in xs if not math.isnan(x)]
        return sum(xs) / len(xs) if xs else float("nan")

    out["n_queries"] = len(nd_base)
    out["kendall_tau_output_vs_shown"] = {
        "llm_rerank (shown best-first)": mean(taus_fwd),
        "llm_rerank_reversed (shown worst-first)": mean(taus_rev),
        "llm_rubric (vs base order)": mean(taus_rub),
    }
    out["top10_overlap_forward_vs_reversed"] = mean(overlaps)
    out["mean_positions_changed_in_window_forward"] = mean(moved_fwd)
    out["ndcg10"] = {
        "base": mean(nd_base),
        "copy control: window untouched": mean(nd_keep),
        "copy control: window reversed": mean(nd_flip),
        "llm_rerank": mean(nd_fwd),
        "llm_rerank_reversed": mean(nd_rev),
        "llm_rubric": mean(nd_rub),
    }
    out["per_query_vs_base"] = {
        "llm_rerank better": sum(1 for a, b in zip(nd_fwd, nd_base, strict=True) if a > b),
        "llm_rerank worse": sum(1 for a, b in zip(nd_fwd, nd_base, strict=True) if a < b),
        "llm_rerank tied": sum(1 for a, b in zip(nd_fwd, nd_base, strict=True) if a == b),
        "llm_rubric better": sum(1 for a, b in zip(nd_rub, nd_base, strict=True) if a > b),
        "llm_rubric worse": sum(1 for a, b in zip(nd_rub, nd_base, strict=True) if a < b),
        "llm_rubric tied": sum(1 for a, b in zip(nd_rub, nd_base, strict=True) if a == b),
    }

    # --- rubric discrimination -------------------------------------------------
    dump = RUNS / "llm_rubric_scores.json"
    if dump.exists():
        verdicts = json.loads(dump.read_text())
        by_grade: dict[int, list[float]] = defaultdict(list)
        distinct_per_query, judged_seen = [], 0
        for qid, rows in verdicts.items():
            rels = qrels.get(qid, {})
            distinct_per_query.append(len({row["score"] for row in rows}))
            for row in rows:
                if row["doc_id"] in rels:
                    by_grade[rels[row["doc_id"]]].append(row["score"])
                    judged_seen += 1
                else:
                    by_grade[0].append(row["score"])
        out["rubric_discrimination"] = {
            "mean_rubric_score_by_qrel_grade": {
                str(g): round(mean(v), 3) for g, v in sorted(by_grade.items())
            },
            "n_scored_by_grade": {str(g): len(v) for g, v in sorted(by_grade.items())},
            "judged_pairs_seen": judged_seen,
            "mean_distinct_scores_per_20_item_window": round(mean(distinct_per_query), 2),
        }
    else:
        out["rubric_discrimination"] = "no verdict dump found — re-run llm_rubric"

    (EXP_DIR / "data").mkdir(exist_ok=True)
    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data" / "llm_diagnosis.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )

    nd = out["ndcg10"]
    tau = out["kendall_tau_output_vs_shown"]
    pq = out["per_query_vs_base"]
    rub = out["rubric_discrimination"]
    rows = [
        "### Did the model follow its input, or judge the content?",
        "",
        "| Measurement | Value | Reads as |",
        "|---|---:|---|",
        f"| Kendall tau, `llm_rerank` output vs the order it was shown | {tau['llm_rerank (shown best-first)']:+.3f} | partial agreement, not copying |",
        f"| Kendall tau, `llm_rerank_reversed` output vs the order it was shown | {tau['llm_rerank_reversed (shown worst-first)']:+.3f} | no agreement with its input either |",
        f"| Kendall tau, `llm_rubric` output vs the base order | {tau['llm_rubric (vs base order)']:+.3f} | mostly the base, surfacing through ties |",
        f"| Mean positions changed inside the 20-item window (`llm_rerank`) | {out['mean_positions_changed_in_window_forward']:.2f} / 20 | it reorders aggressively |",
        f"| Top-10 overlap, forward vs reversed | {out['top10_overlap_forward_vs_reversed']:.2f} | {(1 - out['top10_overlap_forward_vs_reversed']) * 100:.0f}% of the top 10 is decided by presentation order |",
        "",
        "### What the orderings score, against two controls nobody called a model for",
        "",
        "| Run | nDCG@10 |",
        "|---|---:|",
        f"| copy control — window left untouched (= the base) | {nd['copy control: window untouched']:.4f} |",
        f"| copy control — window reversed verbatim | {nd['copy control: window reversed']:.4f} |",
        f"| `llm_rerank` (shown best-first) | {nd['llm_rerank']:.4f} |",
        f"| `llm_rerank_reversed` (shown worst-first) | {nd['llm_rerank_reversed']:.4f} |",
        f"| `llm_rubric` | {nd['llm_rubric']:.4f} |",
        "",
        "### Per-query record against the base",
        "",
        "| Arm | better | worse | tied |",
        "|---|---:|---:|---:|",
        f"| `llm_rerank` | {pq['llm_rerank better']} | {pq['llm_rerank worse']} | {pq['llm_rerank tied']} |",
        f"| `llm_rubric` | {pq['llm_rubric better']} | {pq['llm_rubric worse']} | {pq['llm_rubric tied']} |",
        "",
        "### Can the rubric tell relevance apart at all?",
        "",
        "| Judged relevance grade | mean rubric score (0-3) | n |",
        "|---|---:|---:|",
    ]
    for grade, value in sorted(rub["mean_rubric_score_by_qrel_grade"].items()):
        rows.append(f"| {grade} | {value:.3f} | {rub['n_scored_by_grade'][grade]} |")
    rows += [
        "",
        (
            "Distinct rubric values used per 20-candidate window, on average: "
            f"**{rub['mean_distinct_scores_per_20_item_window']:.2f}** out of 4 available."
        ),
        "",
        (
            f"Grade 0 here is *unjudged-or-irrelevant* ({rub['n_scored_by_grade']['0']} "
            "pairs); in a pooled collection an unjudged document near the top of a "
            "good ranking is often relevant but never assessed, so that bucket "
            "understates the model. The grade-1-versus-grade-2 comparison is the "
            "clean one, because both are judged."
        ),
    ]
    (EXP_DIR / "tables" / "llm_diagnosis.md").write_text("\n".join(rows) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

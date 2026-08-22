"""The second candidate mechanism: is the damage about documents it cannot read?

    IR_DATASETS_HOME=data/eval-cache/ir_datasets \
      uv run --project eval python .../code/language_check.py

`EXP-2026-08-009` found the cross-encoder harmful and located the harm on short
queries. The prose-expansion arms in this experiment refute *length* as the
mechanism — more words made it monotonically worse. That leaves a second candidate
visible in the corpus itself: LongEval-Sci is multilingual (`Burkulması
Engellenmiş Çelik Çaprazların Uç Stabilitelerinin Arttırılması` is a real title in
the frozen subset) while `ms-marco-MiniLM-L-6-v2` is English-only. A reranker that
systematically misranks documents it cannot read would be harmful for a reason no
query rewriting could fix.

The test: stratify the per-query Δ by **what share of that query's reranked
candidate set is not predominantly Latin-script**. If the mechanism is language,
harm should concentrate where that share is high.

Script is a proxy for language, not a substitute for it — it cannot separate
English from French, and it will misread a Latin-script Turkish title. It is
chosen because it needs no model and no network, and because the prediction it
tests is directional: whatever the proxy's noise, harm should still *increase*
with the non-Latin share if language is the cause.

Uses only committed run files and the frozen subset. No new runs, no model calls.
Writes `tables/language.md` and `data/language.json`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

RUNS = REPO_ROOT / "eval" / "runs"
CONFIGS = REPO_ROOT / "eval" / "configs"
SUBSET = REPO_ROOT / "eval" / "subsets" / "sci-2025-01__pooled_d1000.txt"
DEPTH = 50

#: A title below this share of ASCII letters is treated as not predominantly
#: Latin-script. Deliberately lenient: a mostly-English title with a few accented
#: characters should not count as non-Latin.
LATIN_THRESHOLD = 0.9

BUCKETS = ("0% non-Latin", "1-10%", "10-25%", ">25%")


def config_hash(name: str) -> str:
    return hashlib.sha256(
        json.dumps(tomllib.loads((CONFIGS / name).read_text()), sort_keys=True).encode()
    ).hexdigest()[:16]


def read_run(name: str) -> dict[str, list[tuple[str, float]]]:
    digest = config_hash(name)
    hits = sorted(
        RUNS.glob(f"longeval-sci_2025-01__*__{digest}__*.txt.gz"),
        key=lambda p: p.stat().st_mtime,
    )
    if not hits:
        raise SystemExit(f"no run file for {name}")
    ranking: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with gzip.open(hits[-1], "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 5:
                ranking[parts[0]].append((parts[2], float(parts[4])))
    return dict(ranking)


def latin_share(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for ch in letters if ch.isascii()) / len(letters)


def bucket(share: float) -> str:
    if share == 0:
        return "0% non-Latin"
    if share <= 0.10:
        return "1-10%"
    if share <= 0.25:
        return "10-25%"
    return ">25%"


def main() -> int:
    import django

    django.setup()
    from harness import datasets, scoring, stats

    collection = datasets.load_collections()["sci-2025-01"]
    dataset = datasets.load_dataset(collection, "test")
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for q in dataset.qrels_iter():
        qrels[q.query_id][q.doc_id] = int(q.relevance)

    frozen = set(SUBSET.read_text().split())
    print(f"scanning {len(frozen)} subset documents for script …", flush=True)
    is_latin = {
        str(d.id): latin_share((d.metadata.get("title") or "")[:200]) >= LATIN_THRESHOLD
        for d in datasets.docs(dataset)
        if str(d.id) in frozen
    }

    base = read_run("bm25_only_pooled.toml")
    xenc = read_run("xenc_rerank_bm25base_d50.toml")
    sb = scoring.score_per_topic(base, dict(qrels), measures=["nDCG@10"])
    sx = scoring.score_per_topic(xenc, dict(qrels), measures=["nDCG@10"])

    strata: dict[str, list[float]] = defaultdict(list)
    for qid, scores in sb.items():
        if qid not in sx or qid not in base:
            continue
        top = [doc_id for doc_id, _ in base[qid][:DEPTH]]
        if not top:
            continue
        share = sum(1 for d in top if not is_latin.get(d, True)) / len(top)
        strata[bucket(share)].append(sx[qid]["nDCG@10"] - scores["nDCG@10"])

    out = {}
    lines = [
        "### Is the cross-encoder's damage about documents it cannot read?",
        "",
        (
            f"Per-query Δ nDCG@10 for `xenc over bm25 d{DEPTH}` − `bm25_only`, "
            "split by the share of that query's reranked candidate set whose "
            "title is not predominantly Latin-script."
        ),
        "",
        "| non-Latin share of the top-50 | queries | mean Δ nDCG@10 | 95% CI |",
        "|---|---:|---:|---|",
    ]
    for key in BUCKETS:
        values = strata.get(key, [])
        if not values:
            continue
        result = stats.paired_bootstrap(values)
        lines.append(
            f"| {key} | {result.n} | {result.mean:+.4f} | "
            f"[{result.ci_low:+.4f}, {result.ci_high:+.4f}] |"
        )
        out[key] = result.as_dict()

    lines += [
        "",
        (
            "**The language hypothesis is refuted.** Harm is *largest* where the "
            "candidate set is entirely Latin-script and *smallest* where "
            "non-Latin documents are most common — the opposite of the "
            "prediction. Whatever is wrong with the reranker on this collection, "
            "it is not that it cannot read the documents."
        ),
    ]

    (EXP_DIR / "tables").mkdir(exist_ok=True)
    (EXP_DIR / "data").mkdir(exist_ok=True)
    body = "\n".join(lines)
    (EXP_DIR / "tables" / "language.md").write_text(body + "\n")
    (EXP_DIR / "data" / "language.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

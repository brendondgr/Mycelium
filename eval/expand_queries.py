"""Expand short keyword queries into natural prose, at a target length, once.

    LLM_BASE_URL=http://localhost:4000/v1 LLM_MODEL=skynet \
      uv run --project eval python eval/expand_queries.py \
        --collection sci-2025-01 --words 8 16 20 40

`EXP-2026-08-009` found the cross-encoder's damage concentrated on short keyword
queries — 1 word −0.053, 2 words −0.051, 3–4 words −0.108 — and vanishing at five
words or more. A cross-encoder is trained on natural-language questions and has
almost nothing to read in `operation` or `european crania`, whereas BM25's
rare-term exact match is at its best exactly there.

So this does **not** replace the query. It writes a *second* form of it, in prose,
for the reranker alone. BM25 keeps the original short string and keeps its
strength; only the text handed to the cross-encoder changes. If query length is
really the mechanism, effectiveness should rise with the target length; if it is
not, prose will change nothing or make it worse, and either is an answer.

**The expansion sees the query and nothing else.** No documents, no judgments, no
retrieved candidates — so it cannot leak relevance into the arm it feeds. That is
the difference between query expansion and cheating, and it is enforced by the
prompt taking a single string.

Expansions are cached per `(collection, target length)` and are written to disk in
full, so what the model actually produced can be read rather than assumed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parent
BACKEND = REPO_ROOT / "web" / "backend"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import django  # noqa: E402

django.setup()

from harness import datasets  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "eval-cache" / "expansions"
CONCURRENCY = 12


def log(message: str) -> None:
    print(f"[expand] {message}", flush=True)


def cache_path(collection_id: str, words: int) -> Path:
    return CACHE_DIR / f"{collection_id}__{words}w.json"


def prompt(query: str, words: int) -> str:
    return "\n".join(
        [
            "A researcher searched a scientific literature database for this term:",
            "",
            f"    {query}",
            "",
            f"Write approximately {words} words of plain prose describing what that "
            "search is looking for — the subject matter, and the kind of paper that "
            "would satisfy it.",
            "",
            "Rules:",
            "- Stay strictly on the topic of the term. Do not broaden it, and do not "
            "invent a specific study, author, dataset, or finding.",
            "- If the term is ambiguous, describe its most common meaning in a "
            "scientific literature context.",
            "- Write one continuous passage. No preamble, no bullet points, no "
            "quotation marks, no restating these instructions.",
            'Return JSON only, of the form {"description": "..."}.',
        ]
    )


def parse(raw: str | None) -> str | None:
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, re.S)
    if match:
        try:
            value = json.loads(match.group(0)).get("description")
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())
        except json.JSONDecodeError:
            pass
    # A model that ignored the JSON envelope but wrote usable prose is still
    # usable; a model that wrote nothing is not. Recorded either way by the caller.
    text = " ".join(raw.split())
    return text or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="sci-2025-01")
    parser.add_argument("--qrels", default=None)
    parser.add_argument("--words", type=int, nargs="+", default=[8, 16, 20, 40])
    args = parser.parse_args()

    from apps.core.llm import build_llm_client

    collection = datasets.load_collections()[args.collection]
    dataset = datasets.load_dataset(collection, args.qrels)
    queries = datasets.queries(dataset)
    log(f"{collection.snapshot}: {len(queries)} queries")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    client = build_llm_client(component="eval-query-expansion")

    for words in args.words:
        path = cache_path(args.collection, words)
        if path.exists():
            log(f"cache hit: {path.name}")
            continue

        started = time.time()
        log(f"expanding {len(queries)} queries to ~{words} words …")

        def one(item, target=words):
            qid, text = item
            try:
                response = client.complete(
                    prompt(text, target), temperature=0.0, max_tokens=400
                )
            except Exception as exc:  # noqa: BLE001 - one failure must not kill the set
                return qid, text, None, type(exc).__name__
            return qid, text, parse(response.content), None

        out: dict[str, dict] = {}
        failures = 0
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            for n, (qid, original, expanded, error) in enumerate(
                pool.map(one, queries), start=1
            ):
                if expanded is None:
                    failures += 1
                out[qid] = {
                    "original": original,
                    # Falling back to the original is the honest default: it makes a
                    # failed expansion a no-op for that query rather than an empty
                    # string the reranker would score against nothing.
                    "expanded": expanded or original,
                    "ok": expanded is not None,
                    "error": error,
                    "n_words": len((expanded or original).split()),
                }
                if n % 100 == 0:
                    log(f"  {n}/{len(queries)}")

        lengths = sorted(row["n_words"] for row in out.values())
        median = lengths[len(lengths) // 2]
        path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        log(
            f"wrote {path.name}: {len(out)} queries, {failures} failed, "
            f"median {median} words (target {words}), {time.time() - started:.0f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

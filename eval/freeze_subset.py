"""Build the frozen evaluation subset once, and slice its embedding matrix.

    uv run --project eval eval/freeze_subset.py --collection sci-2026-train

Run this once per collection. It reproduces exactly what `run.py`'s `pooled`
scope computes on the fly — the judged set unioned with a corpus-wide BM25 pool
at the given depth — then writes two artifacts so nothing ever recomputes it:

* `eval/subsets/<collection>__pooled_d<depth>.txt` — the document ids in corpus
  order, committed, so every arm on every day scores an identical document set.
* a row-slice of the cached full-corpus bge-small matrix, written under the cache
  key the subset would otherwise miss on — so the dense channel costs zero
  encoding from here on.

See `harness/subset.py` for why both matter.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parent
BACKEND = REPO_ROOT / "web" / "backend"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import django  # noqa: E402

django.setup()

from harness import arms as arms_mod  # noqa: E402
from harness import datasets, subset  # noqa: E402
from harness import index as index_mod  # noqa: E402

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def log(message: str) -> None:
    print(f"[freeze] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="sci-2026-train")
    parser.add_argument("--qrels", default=None)
    parser.add_argument("--depth", type=int, default=1000)
    parser.add_argument(
        "--skip-matrix",
        action="store_true",
        help="freeze the id list only; do not slice the embedding matrix",
    )
    args = parser.parse_args()

    started = time.time()
    collections = datasets.load_collections()
    collection = collections[args.collection]
    dataset = datasets.load_dataset(collection, args.qrels)
    queries = datasets.queries(dataset)
    log(f"{collection.snapshot}: {len(queries)} queries")

    log("loading documents …")
    all_docs = list(datasets.docs(dataset))
    log(f"{len(all_docs)} documents loaded ({time.time() - started:.0f}s)")

    path = subset.subset_path(args.collection, depth=args.depth)
    frozen = subset.load_frozen(path)

    if frozen is None:
        judged = datasets.judged_doc_ids(dataset)
        log(f"{len(judged)} judged documents")
        log("building the corpus-wide BM25 pool (the slow part, once) …")
        seed = arms_mod.bm25_only(queries, all_docs, log=log)
        keep = set(judged)
        for hits in seed.values():
            keep.update(doc_id for doc_id, _ in hits[: args.depth])
        log(f"pool: {len(keep)} unique ids ({len(judged)} judged + depth {args.depth})")
        docs, positions = subset.select(all_docs, keep)
        subset.write_frozen(path, [str(doc.id) for doc in docs])
        log(f"frozen subset written: {path.name} ({len(docs)} docs)")
    else:
        log(f"frozen subset already present: {path.name} ({len(frozen)} docs)")
        docs, positions = subset.select(all_docs, set(frozen))
        if len(docs) != len(frozen):
            log(f"ERROR: {len(frozen)} frozen ids but {len(docs)} matched the corpus")
            return 1

    if args.skip_matrix:
        log("--skip-matrix: done")
        return 0

    # The key `embed_corpus` would compute for this subset at `pooled` scope.
    key = index_mod.cache_key(
        model=EMBEDDING_MODEL,
        snapshot=collection.snapshot,
        scope="pooled",
        doc_ids=[str(doc.id) for doc in docs],
    )
    out_path = index_mod.DEFAULT_CACHE_DIR / f"{key}.npy"

    full_key = index_mod.cache_key(
        model=EMBEDDING_MODEL,
        snapshot=collection.snapshot,
        scope="full",
        doc_ids=[str(doc.id) for doc in all_docs],
    )
    full_path = index_mod.DEFAULT_CACHE_DIR / f"{full_key}.npy"
    if not full_path.exists():
        log(
            f"ERROR: no cached full-corpus matrix at {full_path.name}; "
            "nothing to slice"
        )
        return 1

    full_matrix = np.load(full_path, mmap_mode="r")
    log(f"full matrix {full_matrix.shape} from {full_path.name}")
    sliced = subset.slice_matrix(full_matrix, positions, out_path=out_path, log=log)

    # Cheap proof the slice is aligned: a spot-check that sampled subset rows are
    # byte-identical to the full-corpus rows they claim to come from.
    sample = np.linspace(0, len(positions) - 1, num=min(64, len(positions)), dtype=int)
    ok = all(
        np.array_equal(sliced[i], full_matrix[positions[i]]) for i in sample
    )
    log(f"alignment spot-check over {len(sample)} rows: {'PASS' if ok else 'FAIL'}")
    if not ok:
        return 1

    log(f"done in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

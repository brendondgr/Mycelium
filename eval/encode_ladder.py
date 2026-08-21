"""Encode the frozen subset with a ladder model, once, into the shared cache.

    uv run --project eval eval/encode_ladder.py --model splade
    uv run --project eval eval/encode_ladder.py --model colbert

Separated from `run.py` on purpose. Encoding is the only expensive step left in
the day, it is resumable (see `harness/neural.py`), and it must be possible to
start it in the background and get on with the cheap arms while it works. Once it
finishes, every arm that needs those vectors loads them in seconds, forever.

Requires the frozen subset — build it first with `freeze_subset.py`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parent
BACKEND = REPO_ROOT / "web" / "backend"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import django  # noqa: E402

django.setup()

from harness import datasets, neural, subset  # noqa: E402


def log(message: str) -> None:
    print(f"[encode] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("splade", "colbert"), required=True)
    parser.add_argument("--collection", default="sci-2026-train")
    parser.add_argument("--qrels", default=None)
    parser.add_argument("--depth", type=int, default=1000)
    args = parser.parse_args()

    started = time.time()
    collections = datasets.load_collections()
    collection = collections[args.collection]

    path = subset.subset_path(args.collection, depth=args.depth)
    frozen = subset.load_frozen(path)
    if frozen is None:
        log(f"ERROR: no frozen subset at {path}; run freeze_subset.py first")
        return 1
    log(f"frozen subset: {len(frozen)} docs")

    dataset = datasets.load_dataset(collection, args.qrels)
    log("loading documents …")
    all_docs = list(datasets.docs(dataset))
    docs, _ = subset.select(all_docs, set(frozen))
    del all_docs
    log(f"{len(docs)} subset documents resolved ({time.time() - started:.0f}s)")

    if args.model == "splade":
        matrix = neural.splade_encode(
            docs, snapshot=collection.snapshot, scope="pooled", log=log
        )
        log(f"SPLADE done: {matrix.shape}, nnz={matrix.nnz}, "
            f"mean nnz/doc={matrix.nnz / matrix.shape[0]:.1f}")
    else:
        store = neural.colbert_encode(
            docs, snapshot=collection.snapshot, scope="pooled", log=log
        )
        log(f"ColBERT done: {len(store)} docs, {store.flat.shape[0]} tokens, "
            f"dim={store.flat.shape[1]}, "
            f"mean tokens/doc={store.flat.shape[0] / max(len(store), 1):.1f}")

    log(f"finished in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

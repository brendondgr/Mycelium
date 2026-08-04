"""The single entry point. One command re-measures the ranking stack.

    uv run --project eval eval/run.py --config eval/configs/bm25_only.toml
    uv run --project eval eval/run.py --all --collection sci-2026-train

Design contract (see `eval/README.md`): this file, and everything under
`harness/`, must never need editing when the ranking stack changes. The arms call
production functions; a change to `fusion.py` is measured by the next run
automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import tomllib
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parent
BACKEND = REPO_ROOT / "web" / "backend"

# `apps.content` is a Django app: importable without a database, but only once
# settings are configured. Nothing here ever opens a connection.
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import django  # noqa: E402

django.setup()

from harness import arms as arms_mod  # noqa: E402
from harness import datasets, metadata, scoring  # noqa: E402
from harness import index as index_mod  # noqa: E402

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def log(message: str) -> None:
    print(f"[eval] {message}", flush=True)


def config_hash(config: dict) -> str:
    return hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()[:16]


def read_run_file(path: Path) -> dict[str, list[tuple[str, float]]]:
    """Parse a gzipped TREC run file back into a ranking.

    Lets a pooled run reuse the lexical pool a previous `bm25_only` run already
    computed, instead of rebuilding a corpus-wide BM25 index (~17 GB and several
    minutes on this collection) just to decide which documents to embed.
    """
    import gzip

    ranking: dict[str, list[tuple[str, float]]] = {}
    with gzip.open(path, "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 5:
                continue
            ranking.setdefault(parts[0], []).append((parts[2], float(parts[4])))
    return ranking


def build_corpus(dataset, config, all_docs, queries, pool_from: Path | None):
    """The document set an arm scores over, honouring the corpus scope.

    `full` is every document. `pooled` is the plan's documented fallback: the
    union of every judged document with a deep corpus-wide lexical pool. It makes
    the embedding cost minutes instead of hours, and it is a **re-ranking**
    evaluation — recall numbers from it do not transfer to the full corpus, which
    is why `corpus_scope` is stamped onto every result row.

    The pool is seeded from a corpus-wide BM25 ranking rather than from the judged
    set alone: pooling only judged documents would flatter every arm equally and
    make the comparison meaningless.
    """
    scope = config.get("corpus", {}).get("scope", "full")
    if scope == "full":
        return all_docs, scope

    depth = int(config.get("corpus", {}).get("pool_depth", 1000))
    judged = datasets.judged_doc_ids(dataset)
    keep = set(judged)

    if pool_from and pool_from.exists():
        log(f"seeding pooled subset from {pool_from.name}")
        seed = read_run_file(pool_from)
    else:
        log("seeding pooled subset with a fresh corpus-wide BM25 pool …")
        seed = arms_mod.bm25_only(queries, all_docs, log=log)
    for hits in seed.values():
        keep.update(doc_id for doc_id, _ in hits[:depth])

    pooled = [doc for doc in all_docs if str(doc.id) in keep]
    log(
        f"pooled subset: {len(pooled)} docs "
        f"({len(judged)} judged + BM25 pool depth {depth})"
    )
    return pooled, scope


def run_arm(
    arm_name: str,
    collection_id: str,
    config: dict,
    qrels: str | None,
    pool_from: Path | None = None,
):
    collections = datasets.load_collections()
    collection = collections[collection_id]
    if not collection.scoreable:
        log(
            f"WARNING: {collection.id} has no released qrels "
            f"({collection.blocked_reason}) — emitting a run file, no metrics."
        )
    variant = qrels or collection.default_qrels or ""
    dataset = datasets.load_dataset(collection, variant)

    started = time.time()
    queries = datasets.queries(dataset)
    log(f"{len(queries)} queries")

    limit = config.get("corpus", {}).get("limit")
    log("loading documents …")
    all_docs = list(datasets.docs(dataset, limit=limit))
    log(f"{len(all_docs)} documents loaded")

    docs, scope = build_corpus(dataset, config, all_docs, queries, pool_from)
    if docs is not all_docs:
        del all_docs

    arm = arms_mod.ARMS[arm_name]
    vector_index = None
    if arm_name not in arms_mod.LEXICAL_ONLY:
        matrix = index_mod.embed_corpus(
            docs,
            model=EMBEDDING_MODEL,
            snapshot=collection.snapshot,
            scope=scope,
            parallel=config.get("embedding", {}).get("parallel"),
            batch_size=int(config.get("embedding", {}).get("batch_size", 64)),
            log=log,
        )
        vector_index = index_mod.NumpyIndex(docs, matrix)

    log(f"running arm {arm_name} …")
    ranking = arm(
        queries,
        docs,
        index=vector_index,
        pool_per_interest=int(config.get("params", {}).get("pool_per_interest", 100)),
        log=log,
    )
    wall = time.time() - started

    sha, dirty = scoring.git_state(REPO_ROOT)
    run_path = scoring.RUNS_DIR / (
        f"{collection.snapshot.replace('/', '_')}__{arm_name}__{scope}__{sha}.txt.gz"
    )
    scoring.write_trec_run(ranking, run_path, tag=f"mycelium-{arm_name}")
    log(f"run file: {run_path}")

    metrics: dict[str, float] = {}
    if collection.scoreable:
        metrics = scoring.score(ranking, dataset)
        for name, value in sorted(metrics.items()):
            log(f"  {name:<12} {value:.4f}")

    record = scoring.RunRecord(
        arm=arm_name,
        collection=collection.id,
        snapshot=collection.snapshot,
        qrels=variant or "none",
        corpus_scope=scope,
        corpus_docs=len(docs),
        git_sha=sha,
        dirty=dirty,
        config_hash=config_hash(config),
        embedding_model=None if arm_name in arms_mod.LEXICAL_ONLY else EMBEDDING_MODEL,
        metrics=metrics,
        n_queries=len(queries),
        wall_clock_s=round(wall, 1),
        timestamp=scoring.now_iso(),
        notes="" if collection.scoreable else collection.blocked_reason,
        params=config.get("params", {}),
    )
    path = record.write()
    log(f"result: {path}")
    metadata.write_ir_metadata(record, run_path.with_suffix(".yml"))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="arm config TOML")
    parser.add_argument("--all", action="store_true", help="run every arm")
    parser.add_argument("--collection", default="sci-2026-train")
    parser.add_argument("--qrels", default=None)
    parser.add_argument("--arm", default=None, help="override the config's arm")
    parser.add_argument(
        "--pool-from",
        type=Path,
        default=None,
        help="a bm25_only TREC run file to seed the pooled subset from",
    )
    parser.add_argument(
        "--list-collections", action="store_true", help="show what can be scored"
    )
    args = parser.parse_args()

    if args.list_collections:
        for coll in datasets.load_collections().values():
            state = "scoreable" if coll.scoreable else f"BLOCKED: {coll.blocked_reason}"
            print(f"{coll.id:<16} {coll.snapshot:<38} {state}")
        return 0

    config: dict = {}
    if args.config:
        config = tomllib.loads(args.config.read_text())

    arm_names = list(arms_mod.ARMS) if args.all else [args.arm or config.get("arm")]
    if not arm_names or arm_names == [None]:
        parser.error("give --config, --arm, or --all")

    for name in arm_names:
        log(f"=== {name} on {args.collection} ===")
        run_arm(name, args.collection, config, args.qrels, args.pool_from)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

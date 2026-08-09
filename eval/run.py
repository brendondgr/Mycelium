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


#: Corpus artifacts memoized across arms **within one process**. Loading 870k
#: documents and memory-mapping their embedding matrix costs minutes; a profile
#: grid is 18 configs over the identical corpus, so paying that once instead of
#: eighteen times is the difference between half an hour and half a day. Keyed by
#: everything that can change the corpus, so a cache hit is always the same data.
_CORPUS_CACHE: dict[tuple, tuple] = {}


def load_corpus(collection, dataset, config, queries, pool_from, *, needs_vectors):
    """`(docs, scope, index)` for one arm, memoized per process."""
    limit = config.get("corpus", {}).get("limit")
    key = (
        collection.id,
        config.get("corpus", {}).get("scope", "full"),
        limit,
        int(config.get("corpus", {}).get("pool_depth", 1000)),
        needs_vectors,
    )
    if key in _CORPUS_CACHE:
        log("reusing the corpus loaded earlier in this process")
        return _CORPUS_CACHE[key]

    log("loading documents …")
    all_docs = list(datasets.docs(dataset, limit=limit))
    log(f"{len(all_docs)} documents loaded")

    docs, scope = build_corpus(dataset, config, all_docs, queries, pool_from)
    if docs is not all_docs:
        del all_docs

    vector_index = None
    if needs_vectors:
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

    _CORPUS_CACHE[key] = (docs, scope, vector_index)
    return _CORPUS_CACHE[key]


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

    docs, scope, vector_index = load_corpus(
        collection,
        dataset,
        config,
        queries,
        pool_from,
        needs_vectors=arm_name not in arms_mod.LEXICAL_ONLY,
    )

    if arm_name in arms_mod.PROFILE_ARMS:
        return run_profile_arm(
            arm_name,
            collection,
            dataset,
            config,
            variant,
            docs,
            scope,
            vector_index,
            queries,
            started,
        )

    arm = arms_mod.ARMS[arm_name]
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


#: Synthesized profiles, memoized per process for the same reason as the corpus:
#: every config in the grid rebuilds the identical set, and embedding 100 queries
#: plus a 100-deep dense probe each is not free.
_PROFILE_CACHE: dict[tuple, list] = {}


def build_profiles(collection, dataset, config, queries, index):
    """The synthetic profiles one profile config scores over."""
    from harness import profiles as profiles_mod

    params = config.get("params", {})
    mode = params.get("grouping", "coherent")
    key = (
        collection.id,
        mode,
        int(params.get("seed", 20260809)),
        int(params.get("k_interests", 6)),
        int(params.get("n_clusters", 3)),
        int(params.get("n_profiles", 30)),
        int(params.get("candidate_pool", 300)),
    )
    if key in _PROFILE_CACHE:
        return _PROFILE_CACHE[key], mode

    log(f"embedding {len(queries)} queries to build {mode} profiles …")
    vectors = profiles_mod.query_vectors(queries)
    masses = (
        profiles_mod.query_masses(queries, index) if mode == "imbalanced" else None
    )
    built = profiles_mod.synthesize(
        mode=mode,
        query_ids=[query_id for query_id, _text in queries],
        query_texts=dict(queries),
        vectors=vectors,
        qrels_by_query=profiles_mod.qrels_by_query(dataset),
        masses=masses,
        n_profiles=key[5],
        k_interests=key[3],
        n_clusters=key[4],
        seed=key[2],
        candidate_pool=key[6],
    )
    log(
        f"{len(built)} {mode} profiles: {key[3]} interests in {key[4]} clusters, "
        f"median {sorted(p.n_relevant for p in built)[len(built) // 2]} relevant docs"
    )
    _PROFILE_CACHE[key] = built
    return built, mode


def run_profile_arm(
    arm_name,
    collection,
    dataset,
    config,
    variant,
    docs,
    scope,
    vector_index,
    queries,
    started,
):
    """Score one aggregation arm over synthetic multi-cluster profiles.

    The relevance family goes through `ir_measures` against the profile's union
    qrels exactly as every other arm does. The coverage family — the part C-003
    actually claims and no toolkit implements — comes from
    :mod:`harness.cluster_metrics`, attributed against each cluster's own relevant
    set. Both are reported per profile, because the comparison is paired and an
    aggregate cannot carry a confidence interval.
    """
    from harness import cluster_metrics

    profiles, mode = build_profiles(collection, dataset, config, queries, vector_index)
    params = config.get("params", {})
    beta = float(params.get("beta", 0.15))

    log(f"running arm {arm_name} (grouping={mode}, beta={beta}) …")
    result = arms_mod.PROFILE_ARMS[arm_name](
        profiles,
        docs,
        index=vector_index,
        pool_per_interest=int(params.get("pool_per_interest", 100)),
        beta=beta,
        log=log,
    )
    wall = time.time() - started

    sha, dirty = scoring.git_state(REPO_ROOT)
    run_path = scoring.RUNS_DIR / (
        f"{collection.snapshot.replace('/', '_')}__{arm_name}__{mode}"
        f"__beta{beta}__{scope}__{sha}.txt.gz"
    )
    scoring.write_trec_run(result.ranking, run_path, tag=f"mycelium-{arm_name}")
    log(f"run file: {run_path}")

    per_topic = scoring.score_per_topic(
        result.ranking,
        {profile.id: profile.qrels for profile in profiles},
        measures=params.get("measures"),
    )
    for profile in profiles:
        ranked = [doc_id for doc_id, _score in result.ranking.get(profile.id, [])]
        per_topic.setdefault(profile.id, {}).update(
            cluster_metrics.coverage_metrics(ranked, profile.cluster_relevant)
        )
    metrics = scoring.aggregate(per_topic)
    for name, value in sorted(metrics.items()):
        log(f"  {name:<24} {value:.4f}")

    record = scoring.RunRecord(
        arm=arm_name,
        collection=collection.id,
        snapshot=collection.snapshot,
        qrels=f"{variant}-union-profiles",
        corpus_scope=scope,
        corpus_docs=len(docs),
        git_sha=sha,
        dirty=dirty,
        config_hash=config_hash(config),
        embedding_model=EMBEDDING_MODEL,
        metrics=metrics,
        n_queries=len(profiles),
        wall_clock_s=round(wall, 1),
        timestamp=scoring.now_iso(),
        notes=(
            f"Synthetic {mode} profiles over {collection.snapshot}; "
            "union-of-constituent-queries qrels, not a released judgment set."
        ),
        params={**params, "grouping": mode, "beta": beta},
        per_query=per_topic,
        diagnostics=result.diagnostics,
    )
    path = record.write()
    log(f"result: {path}")
    metadata.write_ir_metadata(record, run_path.with_suffix(".yml"))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        nargs="+",
        help=(
            "one or more arm config TOMLs. Several are run in a single process so "
            "the corpus and its embedding matrix load once for the whole grid."
        ),
    )
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

    configs: list[dict] = [
        tomllib.loads(path.read_text()) for path in (args.config or [])
    ] or [{}]

    for config in configs:
        arm_names = list(arms_mod.ARMS) if args.all else [args.arm or config.get("arm")]
        if not arm_names or arm_names == [None]:
            parser.error("give --config, --arm, or --all")
        for name in arm_names:
            log(f"=== {name} on {args.collection} ===")
            run_arm(name, args.collection, config, args.qrels, args.pool_from)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

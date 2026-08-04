"""Score an *external* TREC run file with the harness's own scoring call.

    uv run --project eval eval/score_run.py \
        --run /path/to/published-baseline.txt.gz --collection sci-2026-train

This exists for one job: the plan's most important checkpoint. Comparing our
`bm25_only` number against a published BM25 baseline is only meaningful if both
are scored the *same way*, so this reuses `harness.scoring.score` verbatim rather
than trusting a number quoted in a paper. If our BM25 lands far from the
published one, the adapter or the implementation is wrong and every downstream
number is meaningless.

The result is printed, not written to `eval/results/` — those records describe
*this repository's* runs, and a third party's baseline is not one of them.
"""

from __future__ import annotations

import argparse
import gzip
from pathlib import Path

from harness import datasets, scoring


def read_run(path: Path) -> dict[str, list[tuple[str, float]]]:
    """Read a TREC run file, gzipped or plain."""
    opener = gzip.open if path.suffix == ".gz" else open
    ranking: dict[str, list[tuple[str, float]]] = {}
    with opener(path, "rt") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 5:
                continue
            ranking.setdefault(parts[0], []).append((parts[2], float(parts[4])))
    return ranking


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--collection", default="sci-2026-train")
    parser.add_argument("--qrels", default=None)
    args = parser.parse_args()

    collection = datasets.load_collections()[args.collection]
    if not collection.scoreable:
        raise SystemExit(f"{collection.id} has no qrels: {collection.blocked_reason}")
    variant = args.qrels or collection.default_qrels
    dataset = datasets.load_dataset(collection, variant)

    ranking = read_run(args.run)
    print(f"run:        {args.run.name}")
    print(f"collection: {collection.snapshot} (qrels={variant})")
    print(f"queries:    {len(ranking)}")
    for name, value in sorted(scoring.score(ranking, dataset).items()):
        print(f"  {name:<12} {value:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

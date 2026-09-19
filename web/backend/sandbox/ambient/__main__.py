"""``python -m sandbox.ambient <command>`` — see :mod:`sandbox.ambient`.

* ``world``    — build the plants and print their counts (no database).
* ``converse`` — have the model write the conversations; cached to ``--corpus``.
* ``run``      — seed the world, ingest the cached conversations, run Plan 04,
  and score it.
* ``all``      — ``converse`` (reusing the cache when present) then ``run``.
* ``nights``   — ``run``, then eight weeks of nights with simulated answers,
  then the exploration themes on a templated paper corpus (EXP-2026-09-014).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from sandbox.collab import bootstrap


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m sandbox.ambient")
    parser.add_argument(
        "command", choices=["world", "converse", "run", "all", "nights"]
    )
    parser.add_argument("--seed", type=int, default=20260919)
    parser.add_argument("--labs", type=int, default=3)
    parser.add_argument("--people", type=int, default=6)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--corpus", help="Where generated conversations are cached.")
    parser.add_argument("--out", help="Write the metrics JSON here.")
    parser.add_argument("--fresh", action="store_true", help="Regenerate the corpus.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    from . import world as world_mod

    world = world_mod.build(args.seed, labs=args.labs, people=args.people)
    conversations = world_mod.conversations(world)
    corpus = Path(
        args.corpus
        or f"/app/data/sandbox/ambient-{args.seed}-{args.labs}x{args.people}.json"
    )
    if args.command == "world":
        print(
            json.dumps(
                {
                    "plants": len(world.plants),
                    "conversations": len(conversations),
                    "by_kind": {
                        k: sum(1 for p in world.plants if p.kind == k)
                        for k in world_mod.EXPECTED
                    },
                },
                indent=2,
            )
        )
        return 0

    bootstrap.setup()
    from . import converse, run, score

    timings: dict[str, float] = {}
    if args.command in ("converse", "all", "nights"):
        if corpus.exists() and not args.fresh:
            written = json.loads(corpus.read_text())
        else:
            started = time.monotonic()
            written = converse.write_all(world, conversations, workers=args.workers)
            timings["converse_s"] = round(time.monotonic() - started, 1)
            corpus.parent.mkdir(parents=True, exist_ok=True)
            corpus.write_text(json.dumps(written, indent=1))
        if args.command == "converse":
            dropped = sum(len(c["dropped"]) for c in written)
            print(
                json.dumps(
                    {
                        "conversations": len(written),
                        "plants_dropped": dropped,
                        **timings,
                    }
                )
            )
            return 0
    else:
        written = json.loads(corpus.read_text())

    run.configure(args.workers)
    started = time.monotonic()
    seeded = run.seed(world)
    ingested = run.ingest(world, written)
    timings["seed_ingest_s"] = round(time.monotonic() - started, 1)
    result = run.pipeline()
    metrics = score.score(world, written, ingested)
    if args.command == "nights":
        from . import nights
        from . import world as world_mod

        started = time.monotonic()
        metrics["nights"] = nights.simulate(world, seed=args.seed)
        timings["nights_s"] = round(time.monotonic() - started, 1)
        started = time.monotonic()
        metrics["corpus_items"] = nights.seed_corpus(world_mod.POOL)
        metrics["drift"] = nights.drift(world)
        timings["drift_s"] = round(time.monotonic() - started, 1)
    report = {
        "seed": args.seed,
        "workers": args.workers,
        "seeded": seeded,
        "pipeline": result,
        "timings": {**timings, **result["timings"]},
        "metrics": metrics,
    }
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

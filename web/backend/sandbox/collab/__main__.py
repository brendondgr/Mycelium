"""``python -m sandbox.collab <command>`` — see :mod:`sandbox.collab`."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from . import bootstrap


def _paths(args) -> Path:
    return Path(
        args.corpus or f"/app/data/sandbox/collab-{args.seed}-{args.people}.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m sandbox.collab")
    parser.add_argument(
        "command",
        choices=["world", "corpus", "seed", "run", "score", "all", "sweep", "calls"],
    )
    parser.add_argument(
        "--thresholds",
        default="0.80,0.85,0.88,0.90,0.92,0.95",
        help="For sweep: merge thresholds to relink at, comma-separated.",
    )
    parser.add_argument("--people", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260918)
    parser.add_argument("--corpus", help="Where generated abstracts are cached.")
    parser.add_argument("--out", help="Write the metrics JSON here.")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--calls", type=int, default=150, help="For calls: how many.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    bootstrap.setup()
    from . import corpus as corpus_mod
    from . import run as run_mod
    from . import score as score_mod
    from . import seed as seed_mod
    from . import world as world_mod

    world = world_mod.build(seed=args.seed, people=args.people)
    report: dict = {
        "seed": args.seed,
        "people": len(world.people),
        "papers": len(world.papers),
        "labs": len(world.labs),
        "projects": len(world.projects),
    }
    corpus_path = _paths(args)
    if args.command == "world":
        print(json.dumps(report))
        return 0

    started = time.monotonic()
    corpus = corpus_mod.generate(world, corpus_path, workers=args.workers)
    report["corpus_seconds"] = round(time.monotonic() - started, 1)
    report["corpus_path"] = str(corpus_path)
    if args.command == "corpus":
        print(json.dumps(report))
        return 0

    if args.command in ("seed", "all"):
        seed_mod.reset()
        report["seeded"] = seed_mod.seed(world, corpus)
    if args.command == "calls":
        from . import calls as calls_mod

        planted = calls_mod.build(seed=args.seed, n=args.calls)
        started = time.monotonic()
        texts = calls_mod.generate(
            planted,
            Path(f"/app/data/sandbox/calls-{args.seed}-{args.calls}.json"),
            workers=args.workers,
        )
        report["calls_corpus_seconds"] = round(time.monotonic() - started, 1)
        items = calls_mod.seed(planted, texts)
        run = calls_mod.run(items, world)
        metrics = calls_mod.score(world, planted, texts, items, run)
        report["metrics"] = metrics
        report["invariant_failures"] = calls_mod.failures(metrics)
        text = json.dumps(report, indent=1, sort_keys=True, default=str)
        if args.out:
            Path(args.out).write_text(text)
        print(text)
        return 1 if report["invariant_failures"] else 0

    if args.command == "sweep":
        rows = []
        for value in [float(v) for v in args.thresholds.split(",")]:
            relinked = run_mod.relink(value)
            metrics = score_mod.score_cn02(world, corpus, {})
            rows.append(
                {
                    **relinked,
                    **{
                        key: metrics[key]
                        for key in (
                            "method_split_total",
                            "wrong_merge_total",
                            "wrong_merges",
                            "q2_declared_and_demonstrated_recall",
                            "q2_undeclared_method_shown_recall",
                            "field_ruler_accuracy",
                            "q1_recall",
                            "q1_precision",
                            "concepts_global",
                        )
                    },
                }
            )
        report["sweep"] = rows
        text = json.dumps(report, indent=1, sort_keys=True, default=str)
        if args.out:
            Path(args.out).write_text(text)
        print(text)
        return 0

    run = {}
    if args.command in ("run", "all"):
        run = run_mod.run_cn02()
    if args.command in ("score", "run", "all"):
        metrics = score_mod.score_cn02(world, corpus, run)
        report["metrics"] = metrics
        report["invariant_failures"] = score_mod.failures(metrics)
    text = json.dumps(report, indent=1, sort_keys=True, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
    print(text)
    return 1 if report.get("invariant_failures") else 0


if __name__ == "__main__":
    raise SystemExit(main())

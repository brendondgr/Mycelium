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
        choices=[
            "world",
            "corpus",
            "seed",
            "run",
            "score",
            "all",
            "sweep",
            "calls",
            "consent",
            "match",
            "panel",
            "browser-prep",
        ],
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
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="For calls: keep the seeded calls and their slots; only re-mark.",
    )
    parser.add_argument(
        "--coverage-cosine", type=float, help="Override COLLAB_COVERAGE_COSINE."
    )
    parser.add_argument(
        "--seekers", type=int, default=120, help="For panel: how many seekers."
    )
    parser.add_argument(
        "--read-calls",
        type=int,
        default=30,
        help="For panel: how many seeded calls to read requirements from.",
    )
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
    if args.command == "match":
        from django.conf import settings

        from . import consent_sim, match_sim

        settings.COLLAB_SEARCH_ENABLED = True
        settings.BILLING_ENFORCE_ENTITLEMENTS = False
        planned = consent_sim.plan(world, args.seed)
        applied = consent_sim.apply(world, planned)
        conversation = match_sim.plant_conversation(
            world, applied["users"], seed=args.seed
        )
        report["conversation_planted"] = len(conversation)
        settings.COLLAB_APPEARANCE_CAP = 10**6  # quality first, the cap separately
        started = time.monotonic()
        report["quality_institution"] = match_sim.quality(
            world, planned, applied, conversation, scope="institution"
        )
        settings.COLLAB_MAX_SCOPE = "anywhere"
        report["quality_anywhere"] = match_sim.quality(
            world, planned, applied, conversation, scope="anywhere"
        )
        report["quality_seconds"] = round(time.monotonic() - started, 1)
        report["load_capped"] = match_sim.load(
            world, planned, applied, searches=300, cap=10, seed=args.seed
        )
        report["load_uncapped"] = match_sim.load(
            world, planned, applied, searches=300, cap=None, seed=args.seed
        )
        failures = []
        for section in ("quality_institution", "quality_anywhere", "load_capped"):
            for key, value in report[section].items():
                if key.startswith("violations") and value:
                    failures.append(f"{section}.{key} = {value}")
        report["invariant_failures"] = failures
        text = json.dumps(report, indent=1, sort_keys=True, default=str)
        if args.out:
            Path(args.out).write_text(text)
        print(text)
        return 1 if failures else 0

    if args.command == "browser-prep":
        import os

        from . import panel_sim

        report["browser"] = panel_sim.prepare_browser(
            world,
            seed=args.seed,
            password=os.environ.get("SANDBOX_PASSWORD", "sandbox-only"),
        )
        print(json.dumps(report, indent=1, default=str))
        return 0

    if args.command == "panel":
        from . import panel_sim

        report.update(panel_sim.main(world, args))
        text = json.dumps(report, indent=1, sort_keys=True, default=str)
        if args.out:
            Path(args.out).write_text(text)
        print(text)
        return 1 if report["invariant_failures"] else 0

    if args.command == "consent":
        from . import consent_sim

        planned = consent_sim.plan(world, args.seed)
        started = time.monotonic()
        applied = consent_sim.apply(world, planned)
        report["apply_seconds"] = round(time.monotonic() - started, 1)
        started = time.monotonic()
        metrics = consent_sim.check(world, planned, applied, seed=args.seed)
        report["check_seconds"] = round(time.monotonic() - started, 1)
        report["metrics"] = metrics
        report["invariant_failures"] = [
            f"{k} = {v}"
            for k, v in metrics.items()
            if k.startswith("violations_") and v
        ]
        text = json.dumps(report, indent=1, sort_keys=True, default=str)
        if args.out:
            Path(args.out).write_text(text)
        print(text)
        return 1 if report["invariant_failures"] else 0

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
        if args.coverage_cosine is not None:
            from django.conf import settings

            settings.COLLAB_COVERAGE_COSINE = args.coverage_cosine
            report["coverage_cosine"] = args.coverage_cosine
        if args.reuse:
            items = calls_mod.existing(planted)
        else:
            items = calls_mod.seed(planted, texts)
        run = calls_mod.run(items, world, read=not args.reuse)
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

#!/usr/bin/env python3
"""Run every manual recommendation pipeline, in order, for all users.

This is the one-command "do the whole daily run now" button. It executes the same
three backend pipelines the schedulers run — search, opportunity matching, then
refitting — one after another, synchronously, for *all* active users, against the
running Docker stack. Each stage streams its run log to the console; if any stage
fails the run stops and returns that stage's exit code.

Stages, in order:
    1. run_daily_suggestions  — scan → fuse → suggest research papers (the search)
    2. run_daily_opportunities — refresh → prune → match grants/conferences/
                                 fellowships (the "sending" of opportunities)
    3. run_refitting          — re-personalize every area's stored top results
                                 through the LLM (the refit) over the freshly
                                 surfaced corpus

Each stage always runs for all users with its default settings — this script takes
no pass-through flags on purpose, so "run everything for everyone" stays a single
predictable command. For a targeted run (one user, --dry-run, --no-llm, subsets,
etc.) call the per-stage scripts in utils/manual/ directly.

Usage:
    python manual_all.py        # search → opportunities → refit, all users
    python manual_all.py --help # this message

The stack must be up first (``python run.py up``). Requires Docker Compose.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "utils" / "manual"))
from _runner import ensure_ready, run_manage  # noqa: E402

# (management command, human-facing intro), in execution order.
STAGES = [
    ("run_daily_suggestions", "1/3 · Searching research papers for all users…"),
    ("run_daily_opportunities", "2/3 · Matching grants/conferences/fellowships for all users…"),
    ("run_refitting", "3/3 · Refitting the personalized layer for all users…"),
]


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    if sys.argv[1:]:
        sys.exit(
            "manual_all.py takes no arguments; it always runs every stage for all "
            "users.\nFor a targeted run, call the per-stage scripts in utils/manual/ "
            "directly (e.g. python utils/manual/manual_search.py --user <username>)."
        )

    # Resolve Compose and confirm the stack is up once, up front, so we don't get
    # halfway through the run before discovering the backend is down.
    base = ensure_ready()

    for command, intro in STAGES:
        print(f"\n=== {intro} ===", flush=True)
        code = run_manage(command, intro=intro, base=base)
        if code != 0:
            print(
                f"\nStage '{command}' exited with code {code}; stopping before the "
                "remaining stages.",
                file=sys.stderr,
                flush=True,
            )
            return code

    print("\nAll stages completed: search → opportunities → refit, for all users.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

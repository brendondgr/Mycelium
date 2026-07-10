#!/usr/bin/env python3
"""Manually trigger the daily research search for every user.

Runs the same scan → fuse → suggest pipeline that Celery Beat runs on a schedule,
on demand, against the running Docker stack. By default it runs for *all* active
users, synchronously, and streams the run log to the console.

This is a thin wrapper around the backend's ``run_daily_suggestions`` management
command (the one code path Beat, the CLI, and this script all share), executed
inside the ``backend`` container so it uses the real Postgres, Redis, and the
embedding model. Any extra arguments are passed straight through to that command.

Usage:
    python utils/manual/manual_search.py                    # all users, synchronous
    python utils/manual/manual_search.py --user brendondgr  # just one user (repeatable)
    python utils/manual/manual_search.py --no-llm           # deterministic fallback, no model
    python utils/manual/manual_search.py --dry-run          # run but don't persist scores
    python utils/manual/manual_search.py --async            # hand off to the Celery worker
    python utils/manual/manual_search.py --help             # full list of pass-through flags

The stack must be up first (``python run.py up``). Requires Docker Compose.

To run search, opportunity matching, and refitting back to back for everyone in
one shot, use the root ``manual_all.py`` orchestrator instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _runner import run_manage  # noqa: E402


def main() -> int:
    return run_manage(
        "run_daily_suggestions",
        sys.argv[1:],
        intro="Triggering the daily research search for all users…",
    )


if __name__ == "__main__":
    raise SystemExit(main())

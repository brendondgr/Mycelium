#!/usr/bin/env python3
"""Manually trigger the daily grants/conferences matching for every user.

Runs the same refresh → prune → match pipeline that Celery Beat runs at 1am, on
demand, against the running Docker stack. By default it runs for *all* active
users, synchronously, and streams the run log to the console.

This is a thin wrapper around the backend's ``run_daily_opportunities`` management
command (the one code path Beat, the CLI, and this script all share), executed
inside the ``backend`` container so it uses the real Postgres, Redis, and the
embedding model. Any extra arguments are passed straight through to that command.

Usage:
    python utils/manual/manual_opportunities.py                   # all users, synchronous
    python utils/manual/manual_opportunities.py --user brendondgr # just one user (repeatable)
    python utils/manual/manual_opportunities.py --no-prune        # keep expired listings
    python utils/manual/manual_opportunities.py --no-llm          # deterministic fallback scoring
    python utils/manual/manual_opportunities.py --dry-run         # run but don't persist
    python utils/manual/manual_opportunities.py --async           # hand off to the Celery worker
    python utils/manual/manual_opportunities.py --help            # full list of pass-through flags

The stack must be up first (``python run.py up``). Requires Docker Compose. This
command never scrapes: the open-source opportunity collector populates the
grants/conferences corpus on its own schedule (a separate run, not this command —
see docs/plans/open-opportunity-collector.md), so if the store is empty this
command has nothing to match against. An earlier ``--no-ingest`` flag existed here
purely as a pass-through to a same-named, always-inert parameter on the backend
command; both were removed together rather than kept as flags with no effect.

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
        "run_daily_opportunities",
        sys.argv[1:],
        intro="Triggering the daily grants/conferences matching for all users…",
    )


if __name__ == "__main__":
    raise SystemExit(main())

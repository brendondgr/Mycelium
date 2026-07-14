#!/usr/bin/env python3
"""Manually refit users' personalized layer over the existing top results.

"Refitting" re-runs only the *personalization* half of the daily pipelines: it
takes the top results already stored for each area (research papers, grants,
conferences, fellowships) and re-scores them through the LLM to refresh each user's
personalized layer — with **no** literature scan and **no** Pivot re-scrape. Use it
after a profile edit, or to re-personalize on demand without paying the full ingest
cost.

This is a thin wrapper around the backend's ``run_refitting`` management command
(the one code path this script and any future scheduler share), executed inside the
``backend`` container so it uses the real Postgres, Redis, embedding model, and LLM.
Any extra arguments are passed straight through to that command.

``--max`` caps how many users are refit — a number or ``all``. Because each refit
issues a round of LLM calls, keep ``--max`` small when smoke-testing so you don't
overwhelm the model host.

By default only each area's top 10 surfaced items go to the model (the rest are
filled deterministically). ``--llm-limit all`` sends *every* surfaced item to the
model instead — use it to give a user full LLM feedback after an LLM outage, at a
higher GPU cost.

Usage:
    python utils/manual/manual_refitting.py                              # all users, top-10 LLM
    python utils/manual/manual_refitting.py --user brendondgr --max 1    # one user, one refit
    python utils/manual/manual_refitting.py --user brendondgr --llm-limit all  # full LLM coverage
    python utils/manual/manual_refitting.py --max 5                      # first 5 active users
    python utils/manual/manual_refitting.py --no-llm                     # deterministic fallback
    python utils/manual/manual_refitting.py --dry-run                    # run but don't persist
    python utils/manual/manual_refitting.py --areas papers grants        # subset of areas
    python utils/manual/manual_refitting.py --help                       # full flag list

The stack must be up first (``python run.py up``). Requires Docker Compose. Refitting
matches the *existing* corpus, so seed papers/opportunities first (``scan_literature``
/ ``ingest_pivot`` and the daily jobs) if the store is empty.

Refitting is **on-demand only**: the root ``manual_all.py`` daily orchestrator
deliberately does not refit, because a refit is the whole-corpus *replace* pass —
it re-scores (and can rewrite or drop) recommendations Mylo already wrote, which
the daily run must never do. Run this script only when a full re-personalization
is actually wanted, e.g. after a profile edit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _runner import run_manage  # noqa: E402


def main() -> int:
    return run_manage(
        "run_refitting",
        sys.argv[1:],
        intro="Refitting the personalized layer for all users…",
    )


if __name__ == "__main__":
    raise SystemExit(main())

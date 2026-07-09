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
    python manual_refitting.py                          # all users, top-10 LLM
    python manual_refitting.py --user brendondgr --max 1  # one user, one refit
    python manual_refitting.py --user brendondgr --llm-limit all  # full LLM coverage
    python manual_refitting.py --max 5                  # first 5 active users
    python manual_refitting.py --no-llm                 # deterministic fallback
    python manual_refitting.py --dry-run                # run but don't persist
    python manual_refitting.py --areas papers grants    # subset of areas
    python manual_refitting.py --help                   # full flag list

The stack must be up first (``python run.py up``). Requires Docker Compose. Refitting
matches the *existing* corpus, so seed papers/opportunities first (``scan_literature``
/ ``ingest_pivot`` and the daily jobs) if the store is empty.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = ROOT / "compose.yaml"
BACKEND_SERVICE = "backend"

# The management command as invoked inside the backend container (matches the
# service's own ``uv run`` entrypoint in compose.yaml).
MANAGE_CMD = [
    "uv",
    "run",
    "--project",
    "web/backend",
    "python",
    "web/backend/manage.py",
    "run_refitting",
]


def compose_cmd() -> list[str]:
    """Return the available Docker Compose invocation, or exit with guidance."""
    if shutil.which("docker"):
        probe = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    sys.exit(
        "Docker Compose was not found. Install Docker Desktop or the Docker "
        "Compose plugin, then re-run this script."
    )


def backend_is_running(base: list[str]) -> bool:
    """True if the backend service has a running container."""
    probe = subprocess.run(
        [*base, "ps", "-q", BACKEND_SERVICE],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0 and bool(probe.stdout.strip())


def main() -> int:
    if not COMPOSE_FILE.exists():
        sys.exit(f"compose.yaml not found at {COMPOSE_FILE}. Run this from the repo root.")

    base = compose_cmd()
    passthrough = sys.argv[1:]

    if not backend_is_running(base):
        sys.exit(
            "The backend service is not running. Start the stack first:\n"
            "    python run.py up"
        )

    # Allocate no TTY when we're not attached to one (e.g. piped or CI), so
    # `docker compose exec` doesn't fail with "the input device is not a TTY".
    exec_flags = [] if sys.stdin.isatty() else ["-T"]
    cmd = [*base, "exec", *exec_flags, BACKEND_SERVICE, *MANAGE_CMD, *passthrough]

    if not passthrough:
        print("Refitting the personalized layer for all users…", flush=True)
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())

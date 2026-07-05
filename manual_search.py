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
    python manual_search.py                     # all users, synchronous
    python manual_search.py --user brendondgr   # just one user (repeatable)
    python manual_search.py --no-llm            # deterministic fallback, no model
    python manual_search.py --dry-run           # run but don't persist scores
    python manual_search.py --async             # hand off to the Celery worker
    python manual_search.py --help              # full list of pass-through flags

The stack must be up first (``python run.py up``). Requires Docker Compose.
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
    "run_daily_suggestions",
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
        print("Triggering the daily research search for all users…", flush=True)
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())

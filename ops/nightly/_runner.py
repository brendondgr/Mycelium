"""Shared plumbing for the manual pipeline triggers.

Every ``manual_*.py`` wrapper in this directory — and ``ops/nightly/manual_all.py``
orchestrator — does the same thing: run one backend ``manage.py`` command inside
the running ``backend`` container via Docker Compose, so it uses the real
Postgres, Redis, embedding model, and LLM. This module centralizes Compose
discovery, the "is the stack up?" guard, and command execution so the wrappers
stay thin and behave identically.

The repository root is two levels up (this file lives at
``<root>/ops/nightly/_runner.py``).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "compose.yaml"
BACKEND_SERVICE = "backend"

# The command prefix as invoked inside the backend container (matches the
# service's own ``uv run`` entrypoint in compose.yaml). Append the management
# command name and any pass-through flags to build the full invocation.
MANAGE_PREFIX = [
    "uv",
    "run",
    "--project",
    "web/backend",
    "python",
    "web/backend/manage.py",
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


def ensure_ready() -> list[str]:
    """Verify the repo layout and that the backend stack is up; return the base
    Compose command. Exits with actionable guidance if either check fails."""
    if not COMPOSE_FILE.exists():
        sys.exit(f"compose.yaml not found at {COMPOSE_FILE}. Run this from the repo root.")

    base = compose_cmd()
    if not backend_is_running(base):
        sys.exit(
            "The backend service is not running. Start the stack first:\n"
            "    mycelium start"
        )
    return base


def have_uv() -> bool:
    """True if the ``uv`` launcher is available on PATH (needed for host runs)."""
    return shutil.which("uv") is not None


def run_host(command: list[str], intro: str | None = None) -> int:
    """Run a command on the host, from the repo root — NOT inside a container.

    Used for the Illinois fellowship scrape (``scrape_fellowships.py``), whose
    Playwright/Chromium browser lives on the host rather than in the backend
    container. Returns the command's exit code; the caller decides whether a
    non-zero result is fatal.
    """
    if intro:
        print(intro, flush=True)
    print(f"\n$ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


def run_manage(
    command: str,
    passthrough: list[str] | None = None,
    intro: str | None = None,
    *,
    base: list[str] | None = None,
) -> int:
    """Run a single ``manage.py`` command inside the backend container.

    ``passthrough`` is forwarded verbatim to the management command. ``intro`` is
    a human-facing line printed only when no pass-through args were given (so the
    default "for all users" run explains itself). Pass a pre-resolved ``base`` to
    skip re-checking Compose when running several commands in a row.
    """
    passthrough = passthrough or []
    if base is None:
        base = ensure_ready()

    # Allocate no TTY when we're not attached to one (e.g. piped or CI), so
    # `docker compose exec` doesn't fail with "the input device is not a TTY".
    exec_flags = [] if sys.stdin.isatty() else ["-T"]
    cmd = [*base, "exec", *exec_flags, BACKEND_SERVICE, *MANAGE_PREFIX, command, *passthrough]

    if intro and not passthrough:
        print(intro, flush=True)
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode

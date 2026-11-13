#!/usr/bin/env python3
"""Create (or promote) a Mycelium superuser admin. `make admin NAME=<user>` runs this.

A thin wrapper over the ``create_admin`` management command, run inside the
running ``backend`` container so it uses the real Postgres. The password reaches
that command as ``ADMIN_USER_PASS`` in the environment of that one ``docker
compose exec`` — never as a command-line argument, and never left behind in
``.env`` or the container's own environment.

Where the password comes from, in order:

1. ``ADMIN_USER_PASS`` in this process's environment (``make setup`` passes the
   one it generated, and prints it itself);
2. ``ADMIN_USER_PASS`` in ``.env`` (an older setup put it there): used once,
   then removed from ``.env``;
3. in a terminal, a prompt (leave it blank to generate one);
4. otherwise a generated one.

A password this script generated is printed once. Re-running is safe: an
existing user is promoted to staff+superuser and given the new password.

Usage:
    python ops/setup/create_admin.py <username>
    python ops/setup/create_admin.py alice --email alice@example.org --first-name Alice
    python ops/setup/create_admin.py --help

The stack must be up (``make up``).
"""

from __future__ import annotations

import getpass
import os
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nightly"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_steps  # noqa: E402
from _runner import BACKEND_SERVICE, MANAGE_PREFIX, ROOT, ensure_ready  # noqa: E402


def choose_password() -> tuple[str, str]:
    """``(password, source)``: source is "env", "dotenv", "prompt" or "generated"."""
    preset = os.environ.get("ADMIN_USER_PASS", "").strip()
    if preset:
        return preset, "env"
    stored = host_steps.read_env(host_steps.ENV).get("ADMIN_USER_PASS", "").strip()
    if stored:
        return stored, "dotenv"
    if sys.stdin.isatty():
        first = getpass.getpass("New admin password (blank to generate one): ")
        if first:
            if getpass.getpass("Again: ") != first:
                sys.exit("The two passwords differ; nothing was changed.")
            return first, "prompt"
    return secrets.token_urlsafe(18), "generated"


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0
    if not argv or argv[0].startswith("-"):
        print(
            "A username is required. Example:\n"
            "    python ops/setup/create_admin.py alice\n"
            "See --help for details.",
            file=sys.stderr,
        )
        return 2

    base = ensure_ready()
    password, source = choose_password()
    print("Creating/promoting the superuser admin…", flush=True)
    # `-e ADMIN_USER_PASS` with no value hands the variable over from this
    # process's environment, so the password is never in the command line.
    cmd = [*base, "exec", "-T", "-e", "ADMIN_USER_PASS", BACKEND_SERVICE,
           *MANAGE_PREFIX, "create_admin", *argv]
    env = {**os.environ, "ADMIN_USER_PASS": password}
    code = subprocess.run(cmd, cwd=ROOT, env=env).returncode
    if code != 0:
        return code
    if source == "dotenv":
        host_steps.update_env(host_steps.ENV, {}, remove={"ADMIN_USER_PASS"})
        print("Removed ADMIN_USER_PASS from .env; the running containers drop it at "
              "the next `make restart`.")
    if source == "generated":
        print(f"\nThe password for {argv[0]!r}, shown once and stored nowhere:\n\n"
              f"    {password}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

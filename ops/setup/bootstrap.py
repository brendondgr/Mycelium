#!/usr/bin/env python3
"""First-time setup for a fresh clone: ``make setup`` runs this.

Steps, each safe to re-run:

1. Check that Docker Compose is installed.
2. Write ``.env`` if it does not exist. Compose already loads ``.env.example``
   for every default, so ``.env`` holds only what is yours: generated secrets
   (Django secret key, the sign-up code, the Discord token-encryption key, the
   first admin's password) and the language-model endpoint, which nothing can
   guess. An existing ``.env`` is never touched.
3. Write ``.env-mylo`` from ``.env-mylo.example`` if it does not exist. It only
   matters if you run Mylo in Discord; blank values leave the bot off.
4. Build and start the stack with ``ops/mycelium build``, which waits for the
   API and applies migrations.
5. Create the first admin account with ``ops/setup/create_admin.py``.

Usage:
    python3 ops/setup/bootstrap.py                  # interactive
    python3 ops/setup/bootstrap.py --yes            # take defaults, ask nothing
    python3 ops/setup/bootstrap.py --env-only       # write .env files, start nothing
    python3 ops/setup/bootstrap.py --admin alice --email alice@example.org

The model endpoint can also come from the environment, which is how an agent
should pass it: ``LLM_BASE_URL``, ``LLM_API_KEY`` and ``LLM_MODEL``.
"""

from __future__ import annotations

import argparse
import base64
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"
ENV_MYLO = ROOT / ".env-mylo"
ENV_MYLO_EXAMPLE = ROOT / ".env-mylo.example"
GATEWAY = "http://localhost:11050"

LLM_DEFAULTS = {
    "LLM_BASE_URL": "http://host.docker.internal:4000/v1",
    "LLM_API_KEY": "EMPTY",
    "LLM_MODEL": "",
}
LLM_PROMPTS = {
    "LLM_BASE_URL": "OpenAI-compatible /v1 endpoint (vLLM, Ollama, LiteLLM, OpenAI...)",
    "LLM_API_KEY": "API key for that endpoint (EMPTY if it needs none)",
    "LLM_MODEL": "Model name the endpoint serves",
}


def say(text: str) -> None:
    print(f"\033[1m{text}\033[0m" if sys.stdout.isatty() else text, flush=True)


def check_prerequisites() -> bool:
    if shutil.which("docker") is None:
        print("  ✗ docker is not installed. Install Docker Engine with the Compose plugin.")
        return False
    probe = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
    if probe.returncode != 0:
        print("  ✗ `docker compose` is unavailable. Install the Docker Compose plugin.")
        return False
    print("  ✓ docker compose")
    if shutil.which("uv") is None:
        print("  · uv not found. The stack runs without it; host tools (make nightly, tests) need it.")
    else:
        print("  ✓ uv")
    return True


def ask(key: str, interactive: bool) -> str:
    preset = os.environ.get(key)
    if preset is not None:
        return preset
    default = LLM_DEFAULTS[key]
    if not interactive:
        return default
    shown = f" [{default}]" if default else ""
    answer = input(f"  {LLM_PROMPTS[key]}{shown}: ").strip()
    return answer or default


def fernet_key() -> str:
    # The format cryptography.fernet.Fernet.generate_key() produces, without the import.
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def write_env(interactive: bool) -> None:
    if ENV.exists():
        print("  · .env exists, leaving it as it is")
        return
    llm = {key: ask(key, interactive) for key in LLM_DEFAULTS}
    lines = [
        "# Your overrides. Compose loads .env.example first and this file second,",
        "# so anything not set here keeps the default documented in .env.example.",
        "# Written by ops/setup/bootstrap.py. Never commit this file.",
        "",
        f"DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}",
        "",
        "# The code a new account needs to sign up. Share it with your lab.",
        f"SIGNUP_ACCESS_CODE={secrets.token_hex(4)}",
        "",
        "# Encrypts Discord OAuth tokens at rest.",
        f"DISCORD_TOKEN_ENC_KEY={fernet_key()}",
        "",
        "# The first admin's password, read by ops/setup/create_admin.py.",
        f"ADMIN_USER_PASS={secrets.token_urlsafe(18)}",
        "",
        "# Language model (any OpenAI-compatible endpoint).",
    ]
    lines += [f"{key}={value}" for key, value in llm.items() if value]
    ENV.write_text("\n".join(lines) + "\n")
    ENV.chmod(0o600)
    print("  ✓ wrote .env (secrets generated; the sign-up code and admin password are in it)")
    if not llm["LLM_MODEL"]:
        print("  · No model named, so the .env.example placeholder is used and profile")
        print("    synthesis and write-ups fall back to deterministic drafts until a real")
        print("    endpoint answers. Set LLM_* in .env, then `make restart`.")


def write_env_mylo() -> None:
    if ENV_MYLO.exists():
        print("  · .env-mylo exists, leaving it as it is")
        return
    shutil.copyfile(ENV_MYLO_EXAMPLE, ENV_MYLO)
    ENV_MYLO.chmod(0o600)
    print("  ✓ wrote .env-mylo (blank, so Mylo stays out of Discord until you add a bot token)")


def run(cmd: list[str]) -> int:
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="First-time setup for a fresh clone.")
    parser.add_argument("--yes", "-y", action="store_true", help="ask nothing; take defaults and environment values")
    parser.add_argument("--env-only", action="store_true", help="write the .env files and stop")
    parser.add_argument("--admin", default="admin", help="username for the first admin (default: admin)")
    parser.add_argument("--email", default="", help="email for the first admin")
    args = parser.parse_args()
    interactive = sys.stdin.isatty() and not args.yes

    say("1/4  Prerequisites")
    if not check_prerequisites():
        return 1

    say("2/4  Configuration")
    write_env(interactive)
    write_env_mylo()
    if args.env_only:
        print("\nDone. Start the stack with `make up`.")
        return 0

    say("3/4  Build and start the stack (the first build takes several minutes)")
    if run([sys.executable, "ops/mycelium", "build"]) != 0:
        print("\n  ✗ The stack did not come up. `make logs` shows why.")
        return 1

    say("4/4  First admin account")
    admin_cmd = [sys.executable, "ops/setup/create_admin.py", args.admin]
    if args.email:
        admin_cmd += ["--email", args.email]
    if run(admin_cmd) != 0:
        print("  ✗ Could not create the admin. Fix the cause, then run `make admin USER=<name>`.")
        return 1

    print(
        f"\nMycelium is running at {GATEWAY}\n"
        f"  Sign in as '{args.admin}' with ADMIN_USER_PASS from .env;"
        " new accounts sign up with SIGNUP_ACCESS_CODE.\n"
        "  `make help` lists everything else."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""First-time setup for a fresh clone: ``make setup`` runs this.

Steps, each safe to re-run:

1. Check that Docker Compose is installed.
2. Write ``mycelium.toml`` for a deployment profile if it does not exist
   (``--profile``, ``MYCELIUM_PROFILE``, a question, or ``lab``).
3. Write ``.env`` (mode 0600) if it does not exist, asking in a terminal for
   the public hostname (or local only) and the language model (a server, a
   hosted API key, or none for now). Every secret is generated: the Django
   key, the Postgres and Redis passwords, the sign-up code, the Discord
   token-encryption key. An existing ``.env`` keeps every value it has; only
   missing generated secrets are added.
4. Write ``.env-mylo`` from ``.env-mylo.example`` if it does not exist. It only
   matters if you run Mylo in Discord; a blank token leaves the bot off.
5. Build and start the production stack with ``ops/mycelium build``, which
   waits for the API and applies migrations.
6. Create the first admin with a generated password, printed once at the end
   and stored nowhere.

It never calls sudo. What needs root (the systemd timer for the daily
collection, the Discord bot) is printed at the end as commands to run
yourself; ``make status`` repeats them until they are done.

Usage:
    python3 ops/setup/bootstrap.py                  # interactive
    python3 ops/setup/bootstrap.py --yes            # ask nothing; read the environment
    python3 ops/setup/bootstrap.py --env-only       # write the config files, start nothing
    python3 ops/setup/bootstrap.py --admin alice --email alice@example.org
    python3 ops/setup/bootstrap.py --profile personal   # just you

Without a terminal (or with ``--yes``) the answers come from the environment,
which is how an agent should pass them: ``PUBLIC_HOSTNAME``; ``LLM_BASE_URL``,
``LLM_MODEL`` and ``LLM_API_KEY``; ``BIND_ADDR`` and ``NGINX_PORT``; the profile
from ``--profile`` or ``MYCELIUM_PROFILE``. With no model named, the instance
runs without one on purpose (``llm.enabled = false``). ``ops/mycelium config``
changes anything afterwards.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_cli  # noqa: E402  (stdlib-only; reads web/backend/config/instance.py)
import host_steps  # noqa: E402

ENV = host_steps.ENV
ENV_MYLO = host_steps.ENV_MYLO
ENV_MYLO_EXAMPLE = ROOT / ".env-mylo.example"

#: The hosted APIs setup offers, with the variable each key lives in.
CLOUD_PROVIDERS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "deepseek": "DeepSeek",
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
        print("  · uv not found. The stack runs without it; the host timer for the")
        print("    daily collection and the Discord bot need it (see the end of setup).")
    else:
        print("  ✓ uv")
    return True


def fernet_key() -> str:
    # The format cryptography.fernet.Fernet.generate_key() produces, without the import.
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def password() -> str:
    """A password that is safe unquoted in a URL, a shell and a .env file."""
    return secrets.token_hex(24)


# --------------------------------------------------------------------------- #
# Questions
# --------------------------------------------------------------------------- #


def _input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def ask_hostname(interactive: bool) -> str:
    preset = os.environ.get("PUBLIC_HOSTNAME")
    if preset is not None or not interactive:
        return clean_hostname(preset or "")
    print("  Where will people reach this instance?")
    print("    A hostname served over HTTPS by a proxy or tunnel in front of this")
    print("    machine (e.g. mycelium.lab.example.edu), or blank for local only.")
    return clean_hostname(_input("  Public hostname [local only]: "))


def clean_hostname(raw: str) -> str:
    host = raw.strip()
    for prefix in ("https://", "http://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix):]
    return host.split("/", 1)[0].strip()


def ask_model(interactive: bool) -> dict:
    """``{"env": {...}, "toml": {...}, "summary": str}`` for the model choice."""
    env_url = os.environ.get("LLM_BASE_URL", "").strip()
    env_model = os.environ.get("LLM_MODEL", "").strip()
    if not interactive or env_model:
        if env_url and env_model:
            return _server_choice(env_url, env_model, os.environ.get("LLM_API_KEY", "").strip())
        missing = [n for n, v in (("LLM_BASE_URL", env_url), ("LLM_MODEL", env_model)) if not v]
        return {
            "env": {}, "toml": {"llm.enabled": False},
            "summary": f"no model ({', '.join(missing)} unset): running without one "
                       "on purpose (llm.enabled = false)",
        }
    print("  Language model. Mycelium writes its summaries, profile drafts and")
    print("  answers with one; without it everything still runs on plain drafts.")
    print("    1. A server you run (vLLM, Ollama, llama.cpp, LiteLLM: any")
    print("       OpenAI-compatible /v1 address)")
    print("    2. A hosted API with a key (OpenAI, Anthropic, Gemini, DeepSeek)")
    print("    3. None for now")
    choice = _input("  Choose 1-3 [3]: ") or "3"
    if choice == "1":
        print("  The server must be reachable from inside Docker: for one on this")
        print("  machine use host.docker.internal instead of localhost.")
        url = _input("  Base URL (e.g. http://host.docker.internal:8001/v1): ")
        for loopback in ("://localhost", "://127.0.0.1"):
            if loopback in url:
                url = url.replace(loopback, "://host.docker.internal")
                print(f"  · using {url} (localhost inside a container is the container)")
        model = _input("  Model name the server serves: ")
        key = getpass.getpass("  API key (blank if it needs none): ").strip()
        if url and model:
            return _server_choice(url, model, key)
        print("  · base URL or model missing; continuing without a model")
    elif choice == "2":
        names = list(CLOUD_PROVIDERS)
        for index, name in enumerate(names, 1):
            print(f"    {index}. {CLOUD_PROVIDERS[name]}")
        picked = _input(f"  Provider 1-{len(names)}: ")
        provider = names[int(picked) - 1] if picked.isdigit() and 1 <= int(picked) <= len(names) else ""
        model = _input("  Model name (as the provider lists it): ") if provider else ""
        key = getpass.getpass("  API key: ").strip() if provider else ""
        if provider and model and key:
            key_env = config_cli.inst.LLM_DEFAULT_KEY_ENV[provider]
            return {
                "env": {key_env: key},
                "toml": {
                    f"llm.providers.{provider}.kind": provider,
                    f"llm.providers.{provider}.model": model,
                    f"llm.providers.{provider}.api_key_env": key_env,
                    "llm.default": provider,
                    "llm.allow_cloud": True,
                },
                "summary": f"{CLOUD_PROVIDERS[provider]} ({model}); text you send it "
                           "leaves this machine",
            }
        print("  · provider, model or key missing; continuing without a model")
    return {"env": {}, "toml": {"llm.enabled": False},
            "summary": "none for now (llm.enabled = false)"}


def _server_choice(url: str, model: str, key: str) -> dict:
    return {
        "env": {"LLM_BASE_URL": url, "LLM_MODEL": model, "LLM_API_KEY": key or "EMPTY"},
        "toml": {},
        "summary": f"{model} at {url}",
    }


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #


def host_urls(values: dict[str, str]) -> dict[str, str]:
    """The services as the host (the Mylo bot) reaches them: loopback ports."""
    pg = values["POSTGRES_PASSWORD"]
    redis = values["REDIS_PASSWORD"]
    return {
        "DATABASE_URL": f"postgres://mycelium:{pg}@127.0.0.1:"
                        f"{values.get('POSTGRES_PORT') or 11450}/mycelium",
        "REDIS_URL": f"redis://:{redis}@127.0.0.1:{values.get('REDIS_PORT') or 11550}/0",
        "AMBIENT_CACHE_URL": f"redis://:{redis}@127.0.0.1:"
                             f"{values.get('AMBIENT_REDIS_PORT') or 11551}/0",
    }


def generated_secrets() -> dict[str, str]:
    return {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "POSTGRES_PASSWORD": password(),
        "REDIS_PASSWORD": password(),
        "SIGNUP_ACCESS_CODE": secrets.token_urlsafe(16),
        "DISCORD_TOKEN_ENC_KEY": fernet_key(),
        "NEO4J_PASSWORD": password(),
        "MINIO_ROOT_PASSWORD": password(),
    }


def write_env(interactive: bool) -> tuple[bool, dict]:
    """Write a new .env, or add what an existing one lacks. ``(ok, model)``."""
    if ENV.exists():
        return update_existing_env(), {}
    hostname = ask_hostname(interactive)
    model = ask_model(interactive)
    values = generated_secrets()
    network = {key: os.environ[key].strip() for key in ("BIND_ADDR", "NGINX_PORT",
                                                          "POSTGRES_PORT", "REDIS_PORT",
                                                          "AMBIENT_REDIS_PORT")
               if os.environ.get(key, "").strip()}
    lines = [
        "# Your overrides. Compose loads .env.example first and this file second,",
        "# so anything not set here keeps the default documented in .env.example.",
        "# Written by ops/setup/bootstrap.py. Never commit or share this file.",
        "",
        "# Production: DEBUG off. `make dev` turns it on for its own containers.",
        "DJANGO_DEBUG=False",
        f"DJANGO_SECRET_KEY={values['DJANGO_SECRET_KEY']}",
        "",
        "# The account the containers run as (yours), so nothing they write is root's.",
        f"UID={os.getuid()}",
        f"GID={os.getgid()}",
        "",
        "# Where nginx listens. 127.0.0.1 keeps it on this machine; see",
        "# docs/configuration.md for a TLS front end.",
        *[f"{key}={value}" for key, value in network.items()],
        "",
        "# The public hostname, served over HTTPS by a proxy in front. Blank: local only.",
        f"PUBLIC_HOSTNAME={hostname}",
        "",
        "# Database and Redis passwords. compose builds the containers' URLs from",
        "# these; the URLs below are the same services as seen from this host.",
        f"POSTGRES_PASSWORD={values['POSTGRES_PASSWORD']}",
        f"REDIS_PASSWORD={values['REDIS_PASSWORD']}",
        *[f"{key}={value}" for key, value in host_urls({**values, **network}).items()],
        "",
        "# The code a new account needs to sign up (signup.mode = \"code\").",
        f"SIGNUP_ACCESS_CODE={values['SIGNUP_ACCESS_CODE']}",
        "",
        "# Encrypts Discord OAuth tokens at rest. Losing it means relinking Discord.",
        f"DISCORD_TOKEN_ENC_KEY={values['DISCORD_TOKEN_ENC_KEY']}",
        "",
        "# Only for `docker compose --profile experimental` (Neo4j, MinIO; unused).",
        f"NEO4J_PASSWORD={values['NEO4J_PASSWORD']}",
        f"MINIO_ROOT_PASSWORD={values['MINIO_ROOT_PASSWORD']}",
    ]
    if model["env"]:
        lines += ["", "# Language model."]
        lines += [f"{key}={value}" for key, value in model["env"].items()]
    host_steps.write_private(ENV, "\n".join(lines) + "\n")
    print("  ✓ wrote .env (mode 0600; every secret generated)")
    print(f"  · public hostname: {hostname or 'none (local only)'}")
    print(f"  · language model: {model['summary']}")
    if not interactive and not hostname:
        print("  · PUBLIC_HOSTNAME unset: serving this machine only "
              "(set it in .env to serve a domain)")
    return True, model


def update_existing_env() -> bool:
    """Leave every value alone; add the generated secrets an older .env lacks."""
    current = host_steps.read_env(ENV)
    add: dict[str, str] = {}
    fresh = generated_secrets()
    for key in ("REDIS_PASSWORD", "NEO4J_PASSWORD", "MINIO_ROOT_PASSWORD",
                "DISCORD_TOKEN_ENC_KEY"):
        if not current.get(key):
            add[key] = fresh[key]
    if not current.get("DJANGO_SECRET_KEY") or current["DJANGO_SECRET_KEY"] in ("change-me",):
        add["DJANGO_SECRET_KEY"] = fresh["DJANGO_SECRET_KEY"]
    if "DJANGO_DEBUG" not in current:
        add["DJANGO_DEBUG"] = "False"
    for key, value in (("UID", str(os.getuid())), ("GID", str(os.getgid()))):
        if key not in current:
            add[key] = value
    if not current.get("POSTGRES_PASSWORD"):
        if postgres_volume_exists():
            print("  ✗ .env has no POSTGRES_PASSWORD, and a database already exists")
            print("    (created with the old built-in password). Give it a generated one:")
            print("      python3 ops/mycelium rotate-db-password")
            print("    then run `make setup` again.")
            return False
        add["POSTGRES_PASSWORD"] = fresh["POSTGRES_PASSWORD"]
    merged = {**current, **add}
    if add.get("POSTGRES_PASSWORD") or add.get("REDIS_PASSWORD"):
        urls = host_urls(merged)
        for key, value in urls.items():
            if key == "DATABASE_URL" and not add.get("POSTGRES_PASSWORD"):
                continue
            if key != "DATABASE_URL" and not add.get("REDIS_PASSWORD"):
                continue
            add[key] = value
    if add:
        host_steps.update_env(ENV, add, comment="Added by ops/setup/bootstrap.py.")
        print(f"  ✓ .env existed; added {', '.join(sorted(add))}")
    else:
        print("  · .env exists and has everything; leaving it as it is")
    return True


def postgres_volume_exists() -> bool:
    """Whether this checkout's Postgres volume was already initialised."""
    env = {**os.environ, "POSTGRES_PASSWORD": "x", "REDIS_PASSWORD": "x"}
    probe = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    if probe.returncode != 0:
        return False
    import json

    try:
        project = json.loads(probe.stdout)["name"]
    except (ValueError, KeyError):
        return False
    volumes = subprocess.run(
        ["docker", "volume", "ls", "-q",
         "--filter", f"label=com.docker.compose.project={project}",
         "--filter", "label=com.docker.compose.volume=postgres-data"],
        capture_output=True, text=True,
    )
    return bool(volumes.stdout.strip())


def write_config(interactive: bool, profile: str | None) -> None:
    if config_cli.CONFIG.exists():
        print(f"  · {config_cli.CONFIG.name} exists, leaving it as it is")
        return
    instance = config_cli.inst
    chosen = profile or os.environ.get("MYCELIUM_PROFILE", "").strip()
    if not chosen and interactive:
        print("  Who will use this instance?")
        for index, name in enumerate(instance.PROFILE_NAMES, 1):
            mark = " (default)" if name == instance.DEFAULT_PROFILE else ""
            print(f"    {index}. {name:<12} {instance.PROFILE_HELP[name]}{mark}")
        answer = _input("  Choose 1-4 or a name [lab]: ").lower()
        if answer.isdigit() and 1 <= int(answer) <= len(instance.PROFILE_NAMES):
            chosen = instance.PROFILE_NAMES[int(answer) - 1]
        else:
            chosen = answer
    chosen = chosen or instance.DEFAULT_PROFILE
    if chosen not in instance.PROFILES:
        print(f"  · unknown profile {chosen!r}; using {instance.DEFAULT_PROFILE}")
        chosen = instance.DEFAULT_PROFILE
    config_cli.CONFIG.write_text(instance.render(chosen))
    print(f"  ✓ wrote {config_cli.CONFIG.name} ({chosen} profile — "
          "`ops/mycelium config show` to review, `config set` to change)")


def apply_model_config(model: dict) -> None:
    """The model choice's mycelium.toml half (servers, llm.enabled)."""
    changes = model.get("toml") or {}
    if not changes or not config_cli.CONFIG.exists():
        return
    text = config_cli.CONFIG.read_text()
    config_cli.CONFIG.write_text(config_cli.edit_file(text, changes, set()))


def sign_up_hint() -> str:
    try:
        cfg = config_cli.resolve()
    except config_cli.inst.ConfigError:
        return ""
    return {
        "closed": "sign-up is closed; create accounts with `make admin NAME=…`.",
        "invite": "others join through an invite from inside the app.",
        "code": "new accounts sign up with SIGNUP_ACCESS_CODE from .env.",
        "domain": "anyone at signup.allowed_domains can sign up.",
        "open": "anyone who can reach it can sign up.",
    }[cfg["signup.mode"]]


def write_env_mylo() -> None:
    if ENV_MYLO.exists():
        print("  · .env-mylo exists, leaving it as it is")
        return
    host_steps.write_private(ENV_MYLO, ENV_MYLO_EXAMPLE.read_text(encoding="utf-8"))
    print("  ✓ wrote .env-mylo (blank, so Mylo stays out of Discord until you add a bot token)")


def run(cmd: list[str], env: dict | None = None) -> int:
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def gateway_url() -> str:
    values = host_steps.read_env(ENV)
    hostname = values.get("PUBLIC_HOSTNAME", "").strip()
    port = values.get("NGINX_PORT", "").strip() or "11050"
    local = f"http://localhost:{port}"
    return f"https://{hostname} (this machine: {local})" if hostname else local


def main() -> int:
    parser = argparse.ArgumentParser(description="First-time setup for a fresh clone.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="ask nothing; take defaults and environment values")
    parser.add_argument("--env-only", action="store_true",
                        help="write the config files and stop")
    parser.add_argument("--admin", default="admin", help="username for the first admin (default: admin)")
    parser.add_argument("--email", default="", help="email for the first admin")
    parser.add_argument(
        "--profile",
        choices=config_cli.inst.PROFILE_NAMES,
        help="deployment profile for a new mycelium.toml (default: lab)",
    )
    args = parser.parse_args()
    interactive = sys.stdin.isatty() and not args.yes

    say("1/5  Prerequisites")
    if not check_prerequisites():
        return 1

    say("2/5  Configuration")
    write_config(interactive, args.profile)
    ok, model = write_env(interactive)
    if not ok:
        return 1
    apply_model_config(model)
    write_env_mylo()
    for path in host_steps.tighten_secret_files():
        print(f"  ✓ {path.name} was readable by others; now 0600")
    host_steps.ensure_dirs()
    if args.env_only:
        print("\nDone. Start the stack with `make up`.")
        return 0

    say("3/5  Build and start the stack (the first build takes several minutes)")
    if run([sys.executable, "ops/mycelium", "build"]) != 0:
        print("\n  ✗ The stack did not come up. `make logs` shows why; `make doctor` checks the rest.")
        return 1

    say("4/5  First admin account")
    admin_password = secrets.token_urlsafe(18)
    admin_cmd = [sys.executable, "ops/setup/create_admin.py", args.admin]
    if args.email:
        admin_cmd += ["--email", args.email]
    if run(admin_cmd, env={**os.environ, "ADMIN_USER_PASS": admin_password}) != 0:
        print(f"  ✗ Could not create the admin. Fix the cause, then run `make admin NAME={args.admin}`.")
        return 1

    say("5/5  Ready")
    print(
        f"\nMycelium is running at {gateway_url()}\n"
        f"  Sign in as '{args.admin}' with this password. It is shown once and stored\n"
        f"  nowhere; `make admin NAME={args.admin}` sets a new one.\n\n"
        f"      {admin_password}\n\n"
        f"  {sign_up_hint()}\n"
        "  Next: `make nightly` runs the first collection now (it takes a while);\n"
        "  `make doctor` checks the instance; `make help` lists everything else.\n"
    )
    lines = host_steps.render_root_steps(
        host_steps.root_steps(),
        bold=lambda t: f"\033[1m{t}\033[0m" if sys.stdout.isatty() else t,
        dim=lambda t: f"\033[2m{t}\033[0m" if sys.stdout.isatty() else t,
    )
    if lines:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

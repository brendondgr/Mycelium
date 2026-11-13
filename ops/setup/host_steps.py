"""Host-side helpers shared by ``bootstrap.py`` and ``ops/mycelium``.

Standard library only: this runs before the stack (or ``uv``) exists.

- ``.env`` editing that keeps comments, and the 0600 rule for secret files.
- The directories the containers write to, created by the checkout's owner
  before Docker can create them as root, and a check for root-owned leftovers
  from an older stack that ran as root.
- The steps that need root (systemd units), which setup never runs itself: it
  prints them, with why and how to check, and ``ops/mycelium status`` repeats
  them until they are done.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env"
ENV_MYLO = ROOT / ".env-mylo"
SECRET_FILES = (ENV, ENV_MYLO)
SYSTEMD_DIR = Path("/etc/systemd/system")

#: Written by the containers (bind mounts). Created here, by the checkout's
#: owner, so Docker never creates them as root.
WRITABLE_DIRS = (
    "data",
    "data/static",
    "data/models",
    "data/logs",
    "data/cache",
    "data/venv",
    "data/backups",
    "data/empty",
    "web/backend/media",
)
#: Where an older stack that ran as root left root-owned files. The services
#: now run as the checkout's owner and cannot write over them.
OWNERSHIP_PATHS = (
    "data",
    "web/backend/media",
    "web/backend/.venv",
    "web/app/.next",
    "web/app/public",
    "web/landing/public/images",
    "web/landing/.astro",
    "web/landing/dist",
)


# --------------------------------------------------------------------------- #
# .env files
# --------------------------------------------------------------------------- #


def read_env(path: Path = ENV) -> dict[str, str]:
    """``KEY=value`` lines, the way Compose reads them (no expansion)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def write_private(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` readable by its owner only, from the first byte."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    path.chmod(0o600)


def update_env(path: Path, values: dict[str, str], *, remove: set[str] | None = None,
               comment: str = "") -> None:
    """Set ``values`` in place (replacing an existing line), append the rest,
    and drop the keys in ``remove``. Comments and order are kept; mode 0600."""
    remove = set(remove or ())
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    pending = dict(values)
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remove:
            continue
        if key in pending:
            out.append(f"{key}={pending.pop(key)}")
            continue
        out.append(line)
    if pending:
        if out and out[-1].strip():
            out.append("")
        if comment:
            out.extend(f"# {row}" if row else "#" for row in comment.splitlines())
        out.extend(f"{key}={value}" for key, value in pending.items())
    write_private(path, "\n".join(out) + "\n")


def loose_secret_files() -> list[tuple[Path, int]]:
    """Secret files readable by anyone but their owner, with their mode."""
    loose = []
    for path in SECRET_FILES:
        if path.is_file():
            mode = path.stat().st_mode & 0o777
            if mode & 0o077:
                loose.append((path, mode))
    return loose


def tighten_secret_files() -> list[Path]:
    """chmod 0600 every secret file this account owns; return what changed."""
    changed = []
    for path, _mode in loose_secret_files():
        try:
            path.chmod(0o600)
        except OSError:
            continue
        changed.append(path)
    return changed


# --------------------------------------------------------------------------- #
# Directories and ownership
# --------------------------------------------------------------------------- #


def ensure_dirs() -> None:
    for rel in WRITABLE_DIRS:
        try:
            (ROOT / rel).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # reported by root_owned() below


def root_owned() -> list[str]:
    """Paths an older, root-run stack left that this account cannot write.

    Checks each path and its direct children: enough to catch a root-owned
    data/ subdirectory without walking a corpus of many thousand files.
    """
    if os.geteuid() == 0:
        return []
    found: list[str] = []
    for rel in OWNERSHIP_PATHS:
        base = ROOT / rel
        if not base.exists():
            continue
        candidates = [base]
        if base.is_dir():
            try:
                candidates += list(base.iterdir())
            except OSError:
                found.append(rel)
                continue
        for path in candidates:
            try:
                if path.lstat().st_uid == 0:
                    found.append(rel)
                    break
            except OSError:
                continue
    return found


def chown_command(paths: list[str]) -> str:
    return f"sudo chown -R $(id -u):$(id -g) {' '.join(paths)}"


# --------------------------------------------------------------------------- #
# Steps that need root
# --------------------------------------------------------------------------- #


@dataclass
class RootStep:
    title: str
    why: str
    commands: list[str]
    check: str
    notes: list[str] = field(default_factory=list)


def _systemctl(*args: str) -> bool:
    if not shutil.which("systemctl"):
        return False
    return subprocess.run(["systemctl", *args], capture_output=True).returncode == 0


def bot_token_set() -> bool:
    return bool(read_env(ENV_MYLO).get("DISCORD_API_KEY", "").strip())


def root_steps() -> list[RootStep]:
    """What still needs an administrator, in order. Empty when nothing does."""
    if not (SYSTEMD_DIR.is_dir() and shutil.which("systemctl")):
        return [RootStep(
            title="Run the daily collection on a schedule",
            why="Mycelium collects new papers and opportunities once a day. "
                "This machine has no systemd, so schedule it yourself.",
            commands=[f"cd {ROOT} && make nightly    # from cron or launchd, once a day"],
            check="data/logs/mylo-last-run.json is rewritten every day",
        )]
    steps: list[RootStep] = []
    timer_installed = (SYSTEMD_DIR / "mylo-daily.timer").exists()
    bot_installed = (SYSTEMD_DIR / "mylo-bot.service").exists()
    venv_ready = (ROOT / ".venv" / "bin" / "python").exists()
    if not timer_installed:
        commands = []
        notes = []
        if not venv_ready:
            if shutil.which("uv") is None:
                notes.append("Install uv first (https://docs.astral.sh/uv/); it "
                             "builds the small host environment the units run.")
            commands.append(f"cd {ROOT} && uv sync    # no sudo: builds .venv for the host units")
        commands += [
            f"sudo python3 {ROOT}/ops/mycelium install-service",
            "sudo systemctl start mylo-daily.timer",
        ]
        steps.append(RootStep(
            title="Install the daily collection timer and start-at-boot",
            why="New papers, grants and fellowships arrive through a run once a "
                "day from a systemd timer on this machine. Without it nothing new "
                "arrives after the first `make nightly`. The same step starts the "
                "stack when the machine boots. Installing into /etc/systemd needs root.",
            commands=commands,
            check="systemctl list-timers mylo-daily.timer    # shows the next run",
            notes=notes,
        ))
    elif not _systemctl("is-enabled", "--quiet", "mylo-daily.timer"):
        steps.append(RootStep(
            title="Turn the daily collection timer back on",
            why="The timer is installed but disabled, so nothing new arrives.",
            commands=["sudo systemctl enable --now mylo-daily.timer"],
            check="systemctl list-timers mylo-daily.timer",
        ))
    if bot_token_set() and timer_installed:
        if not bot_installed:
            steps.append(RootStep(
                title="Install the Mylo Discord bot",
                why="A bot token is in .env-mylo, but the bot's unit is not installed.",
                commands=[f"sudo python3 {ROOT}/ops/mycelium install-service",
                          "sudo systemctl start mylo-bot.service"],
                check="systemctl status mylo-bot.service",
            ))
        elif not _systemctl("is-active", "--quiet", "mylo-bot.service"):
            steps.append(RootStep(
                title="Start the Mylo Discord bot",
                why="A bot token is in .env-mylo, but the bot is not running, so "
                    "Mylo is offline in Discord.",
                commands=["sudo systemctl enable --now mylo-bot.service"],
                check="systemctl status mylo-bot.service    # then: journalctl -u mylo-bot -f",
            ))
    return steps


def render_root_steps(steps: list[RootStep], *, bold=str, dim=str) -> list[str]:
    if not steps:
        return []
    lines = [bold("You need to run these yourself") +
             dim("  (they need root, so setup does not run them)")]
    for number, step in enumerate(steps, 1):
        lines.append("")
        lines.append(bold(f"  {number}. {step.title}"))
        lines += textwrap.wrap(f"Why: {step.why}", 78, initial_indent="     ",
                               subsequent_indent="          ")
        for note in step.notes:
            lines += textwrap.wrap(f"Note: {note}", 78, initial_indent="     ",
                                   subsequent_indent="           ")
        for command in step.commands:
            lines.append(f"       {command}")
        lines.append(dim(f"     Check: {step.check}"))
    lines.append("")
    lines.append(dim("  `make status` shows this list until every step is done."))
    return lines

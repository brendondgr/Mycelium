"""Shared vocabulary for the research-record tools.

One place that knows where `docs/research/` is, how an experiment directory is
named, and how to read a manifest. Every other script in this folder imports
from here so that a layout change is a one-file change.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH = REPO_ROOT / "docs" / "research"
EXPERIMENTS = RESEARCH / "experiments"
TEMPLATES = RESEARCH / "templates"
SCHEMA_PATH = Path(__file__).resolve().parent / "manifest.schema.json"

DIR_RE = re.compile(r"^EXP-(\d{4})-(\d{2})-(\d{3})-([a-z0-9]+(?:-[a-z0-9]+)*)$")
HASH_RE = re.compile(r"\b(sha256|sha1|md5|git|crc32):[0-9a-fA-F]{7,}\b")
# The one accepted alternative to a hash. Spelled out rather than allowed as a
# run of zeros, so that "no hash was taken" is a visible admission with a reason
# attached instead of a value that merely looks like a hash.
NOT_HASHED_RE = re.compile(r"\bnot-hashed:\s*\S+")

REQUIRED_FILES = ("manifest.yaml", "PROTOCOL.md", "RESULTS.md")


@dataclass(frozen=True)
class Experiment:
    """One experiment directory, parsed but not yet validated."""

    path: Path
    manifest: dict[str, Any]

    @property
    def dir_name(self) -> str:
        return self.path.name

    @property
    def id(self) -> str:
        return str(self.manifest.get("id", self.dir_name[:15]))

    @property
    def status(self) -> str:
        return str(self.manifest.get("status", "unknown"))

    def rel(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()


def _isoformat_dates(value: Any) -> Any:
    """YAML parses a bare `2026-08-04` into a `date`, which no JSON Schema
    string check will accept. Coerce back to ISO text rather than making every
    manifest quote its dates — an unquoted date is the natural thing to write,
    and a validator that rejects it teaches the wrong lesson."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _isoformat_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_isoformat_dates(v) for v in value]
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    """Read a manifest, returning {} for a missing or empty file."""
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _isoformat_dates(loaded) if isinstance(loaded, dict) else {}


def iter_experiments() -> list[Experiment]:
    """Every experiment directory, in ID order."""
    if not EXPERIMENTS.is_dir():
        return []
    found = []
    for entry in sorted(EXPERIMENTS.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        found.append(Experiment(entry, load_manifest(entry / "manifest.yaml")))
    return found


def primary_metric(manifest: dict[str, Any]) -> str:
    """Render the primary metric as `name mean±std (n=k)`, or `—`."""
    metrics = manifest.get("metrics") or {}
    name = metrics.get("primary")
    values = metrics.get("values") or {}
    if not name or name not in values:
        return "—"
    value = values[name]
    if isinstance(value, dict):
        mean = value.get("mean")
        std = value.get("std")
        n = value.get("n")
        numeric = isinstance(mean, int | float)
        rendered = f"{name} {mean:.4f}" if numeric else f"{name} ?"
        if isinstance(std, int | float) and std:
            rendered += f" ± {std:.4f}"
        if n:
            rendered += f" (n={n})"
        return rendered
    if isinstance(value, int | float):
        return f"{name} {value:.4f}"
    return f"{name} {value}"


def git(*args: str) -> str:
    """Run a git command from the repository root, returning stripped stdout."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return result.stdout.strip()


def git_state() -> tuple[str, str, bool]:
    """`(short_sha, branch, dirty)` for the working tree, best effort."""
    sha = git("rev-parse", "--short", "HEAD") or "unknown"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    dirty = bool(git("status", "--porcelain"))
    return sha, branch, dirty

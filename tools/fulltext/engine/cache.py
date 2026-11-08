"""The engine's on-disk response cache: one file per key, written atomically.

Every provider answer the engine fetches (lookups, XML, downloaded PDFs) is
kept here so a repeat costs nothing. PubMedExtraction kept some of these as one
JSON map per kind, rewritten whole after each batch; with several workers that
races, so here every key is its own file and every write goes through a
temporary file and ``os.replace``. This is an internal cache, never what a
reader is handed: the tool copies a paper's original into its own store.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

_MISSING = object()


def atomic_write(path: Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` so a concurrent reader sees all of it or none."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def safe_name(key: str) -> str:
    """A file name for ``key``: readable when short, hashed when long."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    if len(safe) <= 150:
        return safe
    return safe[:100] + "_" + hashlib.sha1(key.encode()).hexdigest()


class DiskCache:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, namespace: str, key: str, ext: str) -> Path:
        d = self.root / namespace
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{safe_name(key)}.{ext}"

    # -- JSON values (None is a value: "asked, and the answer was nothing") --- #
    def _load(self, namespace: str, key: str):
        p = self.path(namespace, key, "json")
        try:
            return json.loads(p.read_text(encoding="utf-8"))["v"]
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            return _MISSING

    def get_json(self, namespace: str, key: str, default=None):
        value = self._load(namespace, key)
        return default if value is _MISSING else value

    def has_json(self, namespace: str, key: str) -> bool:
        return self._load(namespace, key) is not _MISSING

    def put_json(self, namespace: str, key: str, value) -> None:
        payload = json.dumps({"v": value}).encode("utf-8")
        atomic_write(self.path(namespace, key, "json"), payload)

    # -- text and bytes ------------------------------------------------------ #
    def read_text(self, namespace: str, key: str, ext: str) -> str | None:
        p = self.path(namespace, key, ext)
        try:
            return p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def write_text(self, namespace: str, key: str, ext: str, text: str) -> Path:
        return atomic_write(self.path(namespace, key, ext), text.encode("utf-8"))

    def write_bytes(self, namespace: str, key: str, ext: str, data: bytes) -> Path:
        return atomic_write(self.path(namespace, key, ext), data)

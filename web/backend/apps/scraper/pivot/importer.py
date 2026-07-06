"""Read the ProQuest tool's scraped output into ``(area, raw_record)`` pairs.

The unattended-safe ingest source: instead of driving a browser, read the tool's
already-scraped JSON (``pivot_funding_results.json`` / ``pivot_conferences.json``
or a ``*_recommendations.json``) or its shared SQLite store (``pivot.db``). The
records come out in the tool's native schema; :mod:`.records` maps them to
``ContentItem`` shape and :mod:`.ingest` upserts them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

# SQLite table shape (mirrors the tool's ``db.py``). ``timeline`` is JSON-encoded.
_SQLITE_AREAS = {
    "grants": {"table": "grants", "json": set()},
    "conferences": {"table": "conferences", "json": {"timeline"}},
}


def _records_from_json_blob(blob) -> list[dict]:
    """Extract the record list from any of the tool's JSON output shapes."""
    if isinstance(blob, list):
        return blob
    if isinstance(blob, dict):
        for key in ("records", "results", "items"):
            if isinstance(blob.get(key), list):
                return blob[key]
    return []


def load_json(path: Path, area: str | None = None) -> list[tuple[str, dict]]:
    """Read one JSON file. ``area`` is inferred from the file when possible."""
    blob = json.loads(Path(path).read_text())
    if area is None and isinstance(blob, dict):
        blob_area = blob.get("area")
        if blob_area in ("grants", "conferences"):
            area = blob_area
    if area not in ("grants", "conferences"):
        raise ValueError(
            f"cannot infer area for {path}; pass area='grants' or 'conferences'"
        )
    return [(area, rec) for rec in _records_from_json_blob(blob)]


def load_sqlite(path: Path, area: str | None = None) -> list[tuple[str, dict]]:
    """Read the grants and/or conferences tables from a ``pivot.db``."""
    areas = [area] if area in ("grants", "conferences") else list(_SQLITE_AREAS)
    out: list[tuple[str, dict]] = []
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        for a in areas:
            spec = _SQLITE_AREAS[a]
            try:
                rows = conn.execute(f"SELECT * FROM {spec['table']}").fetchall()
            except sqlite3.OperationalError:
                continue  # table absent — skip that area
            for row in rows:
                rec = dict(row)
                for f in spec["json"]:
                    raw = rec.get(f)
                    if raw:
                        try:
                            rec[f] = json.loads(raw)
                        except (ValueError, TypeError):
                            pass
                out.append((a, rec))
    finally:
        conn.close()
    return out


def load_pivot(path: str | Path, area: str | None = None) -> list[tuple[str, dict]]:
    """Dispatch on file type: ``.db`` -> SQLite, otherwise JSON."""
    path = Path(path)
    if path.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
        return load_sqlite(path, area)
    return load_json(path, area)


def iter_pivot(paths, area: str | None = None) -> Iterator[tuple[str, dict]]:
    """Flatten several source files into one stream of ``(area, record)``."""
    for path in paths:
        yield from load_pivot(path, area)

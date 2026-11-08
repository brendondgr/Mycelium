"""Where stage 1 writes and stage 2 reads.

The whole point of the split is that fetch and parse never touch each other. Stage
1 writes raw payloads to disk and does nothing else; stage 2 reads them back with
no network access at all. When a parse bug surfaces you re-run stage 2 over
yesterday's payloads in seconds instead of re-hitting five APIs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LATEST = "latest"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class RawBundle:
    """One source's complete fetch output for one run."""

    source: str
    run_id: str
    fetched_at: str
    records: list[dict[str, Any]]
    #: Anything the adapter needs at parse time that is not per-record — hit
    #: counts, the query used, an endpoint version.
    meta: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "run_id": self.run_id,
            "fetched_at": self.fetched_at,
            "meta": self.meta,
            "records": self.records,
        }


class RawStore:
    """Run-scoped directories of raw payloads, with a ``latest`` pointer."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def write(self, bundle: RawBundle) -> Path:
        directory = self.run_dir(bundle.run_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{bundle.source}.json"
        path.write_text(json.dumps(bundle.to_json(), ensure_ascii=False), encoding="utf-8")
        self._mark_latest(bundle.run_id)
        return path

    def _mark_latest(self, run_id: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "LATEST").write_text(run_id, encoding="utf-8")

    def latest_run_id(self) -> str | None:
        pointer = self.root / "LATEST"
        if pointer.exists():
            run_id = pointer.read_text(encoding="utf-8").strip()
            if run_id and self.run_dir(run_id).is_dir():
                return run_id
        runs = sorted(p.name for p in self.root.glob("*") if p.is_dir())
        return runs[-1] if runs else None

    def resolve(self, run_id: str | None) -> str | None:
        if run_id in (None, LATEST):
            return self.latest_run_id()
        return run_id if self.run_dir(run_id).is_dir() else None

    def read(self, run_id: str, source: str) -> RawBundle | None:
        path = self.run_dir(run_id) / f"{source}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RawBundle(
            source=payload["source"],
            run_id=payload["run_id"],
            fetched_at=payload["fetched_at"],
            records=payload.get("records") or [],
            meta=payload.get("meta") or {},
        )

    def sources_in(self, run_id: str) -> list[str]:
        directory = self.run_dir(run_id)
        if not directory.is_dir():
            return []
        return sorted(p.stem for p in directory.glob("*.json"))

    def prune_runs(self, keep: int) -> list[str]:
        """Keep the N most recent run directories; delete the rest."""
        runs = sorted(p for p in self.root.glob("*") if p.is_dir())
        removed: list[str] = []
        for directory in runs[:-keep] if keep > 0 else runs:
            for child in directory.glob("*"):
                child.unlink()
            directory.rmdir()
            removed.append(directory.name)
        return removed

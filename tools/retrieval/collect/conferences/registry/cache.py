"""The local registry cache the resolve stage reads instead of the live APIs.

Two reasons this is a cache and not a live call, and both are load-bearing:

* **The resolve stage must run offline.** Trust thresholds get tuned constantly
  and the briefing is explicit that re-running resolve must not require
  re-fetching.
* **The upstream hosts punish repetition.** dblp's search host answers 429 on
  the fourth request inside 1.4 seconds and then refuses TCP connections
  host-wide for minutes, with continued probing extending the ban. Rankings
  change every few years. Neither should be touched on a normal run.

Both halves are pulled on a slow schedule by ``registry/dblp.py`` and
``registry/core_rankings.py`` and land here as plain JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DBLP_FILE = "dblp_venues.json"
CORE_FILE = "core_rankings.json"


class RegistryCache:
    """Read-only view over the cached registry. Never opens a socket."""

    def __init__(self, directory: Path | str | None) -> None:
        self.directory = Path(directory) if directory else None
        self.venues: dict[str, dict[str, Any]] = {}
        #: Acronym -> [venue keys]. Deliberately a *list*: 420 acronyms map to
        #: more than one venue, and collapsing them to one would be the silent
        #: deletion this whole design exists to avoid.
        self.by_acronym: dict[str, list[str]] = {}
        self.rankings_by_acronym: dict[str, dict[str, Any]] = {}
        self.rankings_by_dblp: dict[str, dict[str, Any]] = {}
        #: Pairs dblp explicitly asserts are *not* the same venue. A hand-curated
        #: do-not-merge list, honoured before any similarity heuristic runs.
        self.different_from: dict[str, set[str]] = {}
        self._loaded = False

    @property
    def available(self) -> bool:
        return bool(self.venues or self.rankings_by_acronym)

    def load(self) -> RegistryCache:
        if self._loaded or self.directory is None:
            return self
        self._loaded = True
        self._load_dblp(self.directory / DBLP_FILE)
        self._load_core(self.directory / CORE_FILE)
        return self

    def _load_dblp(self, path: Path) -> None:
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        for venue in payload.get("venues", []):
            key = venue.get("key")
            if not key:
                continue
            self.venues[key] = venue
            for acronym in venue.get("acronyms") or []:
                normalized = _normalize(acronym)
                if normalized:
                    self.by_acronym.setdefault(normalized, []).append(key)
            for other in venue.get("different_from") or []:
                self.different_from.setdefault(key, set()).add(other)

    def _load_core(self, path: Path) -> None:
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("rankings", []):
            entry = {
                "core": {
                    "rank": row.get("rank", ""),
                    "bucket": row.get("bucket", ""),
                    "edition": row.get("edition", ""),
                    "field_codes": ",".join(row.get("field_codes") or []),
                }
            }
            acronym = _normalize(row.get("acronym"))
            if acronym:
                # First writer wins: the export is sorted by title and 15
                # acronyms collide, so later rows would silently overwrite.
                self.rankings_by_acronym.setdefault(acronym, entry)
            if row.get("dblp_key"):
                self.rankings_by_dblp.setdefault(row["dblp_key"], entry)

    # -- lookups ----------------------------------------------------------

    def venue(self, key: str) -> dict[str, Any] | None:
        return self.venues.get(key)

    def candidates_for_acronym(self, acronym: str) -> list[dict[str, Any]]:
        """Every venue claiming this acronym. Often more than one, by design."""
        if not acronym:
            return []
        return [
            self.venues[key] for key in self.by_acronym.get(acronym, []) if key in self.venues
        ]

    def ranking_for(self, record) -> dict[str, Any]:
        """CORE's rank for a series, joined on the dblp key where possible.

        The dblp key is the reliable join: CORE publishes its own dblp URL and
        11 of 48 sampled venues have a key that is nothing like their acronym
        (``EC`` -> ``sigecom``, ``ISS`` -> ``tabletop``), which no amount of
        string similarity recovers.
        """
        if record.dblp_key and record.dblp_key in self.rankings_by_dblp:
            return self.rankings_by_dblp[record.dblp_key]
        acronym = _normalize(record.acronym)
        if acronym in self.rankings_by_acronym:
            return self.rankings_by_acronym[acronym]
        for variant in record.acronym_variants:
            normalized = _normalize(variant)
            if normalized in self.rankings_by_acronym:
                return self.rankings_by_acronym[normalized]
        return {}

    def asserts_different(self, left: str, right: str) -> bool:
        return right in self.different_from.get(left, ()) or left in self.different_from.get(
            right, ()
        )


def _normalize(value: object) -> str:
    import re

    text = str(value or "").strip().upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def write_cache(directory: Path, name: str, payload: dict[str, Any]) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path

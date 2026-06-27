"""Google Scholar retriever (optional ``scholarly`` dependency).

The one behavior change from a naive "fill everything" scrape: select the 10
most-cited + 10 most-recent publications, deduplicate, and fill abstracts only
for that ≤20-paper union. This is the relevance filter *and* the main thing that
keeps ``scholarly`` from getting rate-limited (per-paper detail requests drop
from N to ≤20).

``select_publications`` is pure (no network) and is the unit under test. The
network entry point, :func:`fetch_author`, lazily imports ``scholarly`` so this
module loads cheaply and offline; a fake ``scholarly_api`` can be injected.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from ..errors import AuthorImportError


def _pub_key(pub: dict[str, Any]) -> str:
    """scholarly's stable per-author publication id; fall back to title."""
    return pub.get("author_pub_id") or pub.get("bib", {}).get("title", "")


def _year_val(pub: dict[str, Any]) -> int:
    try:
        return int(pub.get("bib", {}).get("pub_year"))
    except (TypeError, ValueError):
        return -1  # unknown years sink to the bottom, never count as "recent"


def select_publications(
    pubs: Sequence[dict[str, Any]],
    top_cited: int = 10,
    most_recent: int = 10,
) -> list[dict[str, Any]]:
    """Top-N cited + top-M recent, deduplicated on a stable key."""

    by_cites = sorted(pubs, key=lambda p: p.get("num_citations", 0), reverse=True)
    cited = by_cites[:top_cited]
    by_year = sorted(pubs, key=_year_val, reverse=True)
    recent = by_year[:most_recent]
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for pub in cited + recent:
        key = _pub_key(pub)
        if key not in seen:
            seen.add(key)
            out.append(pub)
    return out


def _import_scholarly() -> Any:
    try:
        from scholarly import scholarly
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise AuthorImportError(
            "Google Scholar import needs the optional 'scholarly' package; "
            "install the 'scrapers' extra (uv sync --extra scrapers)."
        ) from exc
    return scholarly


def fetch_author(
    scholar_id: str,
    *,
    scholarly_api: Any | None = None,
    delay: float = 1.0,
    fill_abstracts: bool = True,
) -> dict[str, Any]:
    """Fetch an author and the chosen ≤20 publications (filled abstracts)."""

    api = scholarly_api or _import_scholarly()
    author = api.search_author_id(scholar_id)
    api.fill(author, sections=["basics", "indices", "interests", "publications"])

    pubs = select_publications(author.get("publications", []))
    if fill_abstracts:
        for pub in pubs:
            api.fill(pub)
            if delay:
                time.sleep(delay)  # keep scholarly under the rate limit

    author = {**author, "publications": pubs}
    return {"author": author, "publications": pubs}

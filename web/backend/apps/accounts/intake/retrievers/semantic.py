"""Semantic Scholar retriever — cross-check / fallback source.

Pulls the author plus their papers (fields-of-study become areas). An optional
API key is sent as ``x-api-key`` for higher rate limits.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._http import fetch_json

S2_BASE = "https://api.semanticscholar.org/graph/v1"
AUTHOR_FIELDS = "name,affiliations,externalIds,homepage"
PAPER_FIELDS = (
    "title,year,fieldsOfStudy,s2FieldsOfStudy,citationCount,authors,abstract"
)
MAX_PAPERS = 100


def fetch_author(
    author_id: str,
    *,
    fetch: Callable[..., Any] = fetch_json,
    api_key: str | None = None,
    max_papers: int = MAX_PAPERS,
) -> dict[str, Any]:
    headers = {"x-api-key": api_key} if api_key else None

    author = fetch(
        f"{S2_BASE}/author/{author_id}?fields={AUTHOR_FIELDS}", headers=headers
    )
    papers = fetch(
        f"{S2_BASE}/author/{author_id}/papers"
        f"?fields={PAPER_FIELDS}&limit={min(max_papers, 1000)}",
        headers=headers,
    )
    return {"author": author, "papers": papers.get("data") or []}

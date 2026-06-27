"""OpenAlex retriever — the primary, license-clean path.

Resolves the author record, then pulls their works filtered on ``author.id`` (or
``author.orcid`` for an ORCID-resolved id), most-cited first. OpenAlex auto-tags
each work with topics and keywords, which the normalizer turns into areas and
keywords.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable, Mapping
from typing import Any

from ._http import fetch_json

OPENALEX_BASE = "https://api.openalex.org"
MAX_WORKS = 50


def _url(path: str, params: Mapping[str, str]) -> str:
    query = urllib.parse.urlencode(params)
    return f"{OPENALEX_BASE}{path}" + (f"?{query}" if query else "")


def _bare_id(value: Any) -> str:
    if not value:
        return ""
    return str(value).rstrip("/").rsplit("/", 1)[-1]


def fetch_author(
    canonical_id: str,
    *,
    fetch: Callable[..., Any] = fetch_json,
    api_key: str | None = None,
    mailto: str | None = None,
    max_works: int = MAX_WORKS,
) -> dict[str, Any]:
    common: dict[str, str] = {}
    if mailto:
        common["mailto"] = mailto
    if api_key:
        common["api_key"] = api_key

    author = fetch(_url(f"/authors/{canonical_id}", common))

    if canonical_id.lower().startswith("orcid:"):
        works_filter = f"author.orcid:{canonical_id.split(':', 1)[1]}"
    else:
        works_filter = f"author.id:{_bare_id(author.get('id')) or canonical_id}"

    works = fetch(
        _url(
            "/works",
            {
                **common,
                "filter": works_filter,
                "per_page": str(min(max_works, 200)),
                "sort": "cited_by_count:desc",
            },
        )
    )
    results = works.get("results") or []
    return {"author": author, "works": results[:max_works]}

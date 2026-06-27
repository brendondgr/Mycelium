"""The import facade: ``(identifier, source) -> AuthorProfileDraft``.

Wires resolve -> retrieve -> normalize -> aggregate. The source adapters are
injectable so the whole pipeline runs offline in tests (pass ``adapters=`` with
fakes); production builds them from Django settings (API keys, polite mailto).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .aggregate import aggregate
from .drafts import AuthorProfileDraft
from .errors import AuthorImportError
from .normalizers import openalex as openalex_norm
from .normalizers import scholar as scholar_norm
from .normalizers import semantic as semantic_norm
from .resolve import ResolvedAuthor, resolve
from .retrievers import openalex as openalex_ret
from .retrievers import scholar as scholar_ret
from .retrievers import semantic as semantic_ret

__all__ = ["AuthorImportError", "SourceAdapter", "default_adapters", "import_author"]


@dataclass(frozen=True)
class SourceAdapter:
    """A retriever (id -> raw payload) paired with its normalizer."""

    retrieve: Callable[[str], dict[str, Any]]
    normalize: Callable[[dict[str, Any]], AuthorProfileDraft]


def default_adapters(settings: Any | None = None) -> dict[str, SourceAdapter]:
    """Build the production adapters, reading API keys from Django settings."""

    if settings is None:
        from django.conf import settings as settings  # noqa: PLW0127

    openalex_key = getattr(settings, "OPENALEX_API_KEY", "") or None
    openalex_mailto = getattr(settings, "OPENALEX_MAILTO", "") or None
    semantic_key = getattr(settings, "SEMANTIC_SCHOLAR_API_KEY", "") or None

    return {
        "openalex": SourceAdapter(
            retrieve=lambda cid: openalex_ret.fetch_author(
                cid, api_key=openalex_key, mailto=openalex_mailto
            ),
            normalize=openalex_norm.normalize,
        ),
        "semantic": SourceAdapter(
            retrieve=lambda cid: semantic_ret.fetch_author(cid, api_key=semantic_key),
            normalize=semantic_norm.normalize,
        ),
        "scholar": SourceAdapter(
            retrieve=lambda cid: scholar_ret.fetch_author(cid),
            normalize=scholar_norm.normalize,
        ),
    }


def import_author(
    identifier: str,
    source: str,
    *,
    adapters: Mapping[str, SourceAdapter] | None = None,
    settings: Any | None = None,
) -> AuthorProfileDraft:
    """Resolve, fetch, normalize, and aggregate one author into a draft."""

    resolved: ResolvedAuthor = resolve(identifier, source)
    adapters = adapters if adapters is not None else default_adapters(settings)
    adapter = adapters.get(resolved.source)
    if adapter is None:
        raise AuthorImportError(f"no adapter registered for source {resolved.source!r}")

    raw = adapter.retrieve(resolved.canonical_id)
    draft = adapter.normalize(raw)
    return aggregate(draft)

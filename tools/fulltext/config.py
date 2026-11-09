"""The instance's configuration, turned into what the engine takes.

The engine reads credentials from a plain mapping with its own names
(``tools/fulltext/engine/sources.py``). This module is the one place that maps
Mycelium's settings onto them: the tool's own keys, plus the literature-scan
keys and contact address the platform and the retrieval tool already hold, so
an operator never sets the same key twice.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from tools._framework.discovery import REPO_ROOT

from .engine import sources as S
from .engine.pipeline import Engine
from .engine.state import State


def _get(name: str, default=""):
    return getattr(settings, name, default) or default


def contact_email() -> str:
    return (
        _get("FULLTEXT_CONTACT_EMAIL")
        or _get("SCRAPER_CONTACT_EMAIL")
        or _get("OPENALEX_MAILTO")
    )


def credentials() -> dict[str, str]:
    """The engine's credential mapping, from this instance's settings."""
    return {
        "CONTACT_EMAIL": contact_email(),
        # Shared with the literature scan (retrieval tool / platform settings).
        "PUBMED_API_KEY": _get("PUBMED_API_KEY"),
        "OPEN_ALEX_API_KEY": _get("OPENALEX_API_KEY"),
        "SEMANTIC_SCHOLAR_API_KEY": _get("SEMANTIC_SCHOLAR_API_KEY"),
        # This tool's own.
        "CORE_API_KEY": _get("CORE_API_KEY"),
        "ELSEVIER_API_KEY": _get("ELSEVIER_API_KEY"),
        "ELSEVIER_INST_TOKEN": _get("ELSEVIER_INST_TOKEN"),
        "SPRINGER_API_KEY": _get("SPRINGER_API_KEY"),
        "WILEY_TDM_TOKEN": _get("WILEY_TDM_TOKEN"),
    }


def source_order() -> list[str]:
    """The configured order. Unknown names are an error (see :func:`problems`)."""
    return list(_get("FULLTEXT_SOURCES", S.DEFAULT_ORDER))


def problems() -> list[str]:
    """Configuration mistakes that should stop the tool loading."""
    out = []
    unknown = [s for s in source_order() if s not in S.SOURCES]
    if unknown:
        out.append(
            f"[tools.fulltext] sources names unknown source(s) "
            f"{', '.join(unknown)}; known: {', '.join(S.SOURCES)}"
        )
    if int(_get("FULLTEXT_MIN_CHARS", 500)) < 1:
        out.append("[tools.fulltext] min_chars must be at least 1")
    if int(_get("FULLTEXT_CONCURRENCY", 4)) < 1:
        out.append("[tools.fulltext] concurrency must be at least 1")
    return out


def data_root() -> Path:
    """Where the tool keeps its files: gitignored ``data/fulltext/`` at the
    repository root (never relative to the working directory)."""
    return REPO_ROOT / "data" / "fulltext"


def cache_dir() -> Path:
    return data_root() / "cache"


def engine(*, state: State | None = None, retry: bool = False) -> Engine:
    """An :class:`Engine` configured for this instance."""
    return Engine(
        credentials(),
        cache_dir(),
        state=state,
        order=source_order(),
        min_chars=int(_get("FULLTEXT_MIN_CHARS", 500)),
        workers=int(_get("FULLTEXT_CONCURRENCY", 4)),
        retry=retry,
        disable_ttl=float(_get("FULLTEXT_DISABLE_TTL_HOURS", 6.0)) * 3600,
    )

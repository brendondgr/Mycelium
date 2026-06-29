"""Source registry + Django-settings-backed config.

Replaces the reference tool's dotenv ``Config`` with one populated from Django
settings, and maps short source names to scraper classes so callers can select a
subset (e.g. ``["openalex", "pubmed"]``).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from .base import BaseScraper
from .openalex import OpenAlexScraper
from .pubmed import PubMedScraper
from .semanticscholar import SemanticScholarScraper

# Short name -> scraper class. The short name is what callers pass to select
# sources; ``order`` preserves a stable, deterministic iteration order.
SCRAPERS: dict[str, type[BaseScraper]] = {
    "openalex": OpenAlexScraper,
    "pubmed": PubMedScraper,
    "semanticscholar": SemanticScholarScraper,
}

DEFAULT_SOURCES = tuple(SCRAPERS.keys())


@dataclass(frozen=True)
class ScraperConfig:
    """API keys + etiquette contact info, read from Django settings."""

    openalex_api_key: str = ""
    semanticscholar_api_key: str = ""
    pubmed_api_key: str = ""
    # Contact info is required/recommended by both OpenAlex and NCBI etiquette.
    contact_email: str = ""
    tool_name: str = "Mycelium"

    @classmethod
    def from_settings(cls) -> ScraperConfig:
        return cls(
            openalex_api_key=getattr(settings, "OPENALEX_API_KEY", "") or "",
            semanticscholar_api_key=(
                getattr(settings, "SEMANTIC_SCHOLAR_API_KEY", "") or ""
            ),
            pubmed_api_key=getattr(settings, "PUBMED_API_KEY", "") or "",
            contact_email=(
                getattr(settings, "SCRAPER_CONTACT_EMAIL", "")
                or getattr(settings, "OPENALEX_MAILTO", "")
                or ""
            ),
            tool_name=getattr(settings, "SCRAPER_TOOL_NAME", "Mycelium") or "Mycelium",
        )


def resolve_sources(sources: list[str] | tuple[str, ...] | None) -> list[str]:
    """Normalize a requested source list to known short names (order-stable).

    ``None`` selects every source. Unknown names raise ``ValueError`` so a typo
    in a trigger fails loudly instead of silently scanning nothing.
    """
    if not sources:
        return list(DEFAULT_SOURCES)
    resolved: list[str] = []
    for name in sources:
        key = name.strip().lower()
        if key not in SCRAPERS:
            raise ValueError(
                f"Unknown source {name!r}. Known sources: {', '.join(SCRAPERS)}."
            )
        if key not in resolved:
            resolved.append(key)
    return resolved


def build_scrapers(
    session, config: ScraperConfig, sources: list[str]
) -> list[BaseScraper]:
    """Instantiate the requested scrapers against a shared aiohttp session."""
    return [SCRAPERS[name](session, config) for name in sources]

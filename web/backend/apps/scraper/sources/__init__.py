"""Source scrapers ported from the ResearchScraper reference tool.

Each concrete scraper subclasses :class:`~apps.scraper.sources.base.BaseScraper`
and maps a source's native payload onto the shared
:class:`~apps.scraper.sources.record.Record`, so the orchestrator can dedup and
ingest results uniformly regardless of origin.
"""

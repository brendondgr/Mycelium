"""Source scrapers ported from the ResearchScraper reference tool.

Each concrete scraper subclasses :class:`~tools.retrieval.sources.base.BaseScraper`
and maps a source's native payload onto the shared
:class:`~tools.retrieval.sources.record.Record`, so the orchestrator can dedup and
ingest results uniformly regardless of origin.
"""

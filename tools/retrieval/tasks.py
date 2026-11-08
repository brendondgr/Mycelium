"""Celery trigger for the literature scan.

This is a *placeholder*: it is registered and ready, but wired to no Beat
schedule and to no per-user profile yet. Call it directly to trigger a scan ::

    from tools.retrieval.tasks import scan_literature
    scan_literature.delay(["agentic ai in healthcare", "quantum cybersecurity"])

Later phases will schedule it and feed it queries aggregated from member
profiles / WatchPreferences.
"""

from __future__ import annotations

import logging

from celery import shared_task

from tools.retrieval.ingest import scan

logger = logging.getLogger(__name__)


@shared_task(name="apps.scraper.scan_literature")
def scan_literature(
    queries: list[str],
    *,
    months_back: int = 2,
    months_forward: int = 1,
    sources: list[str] | None = None,
    embed: bool = True,
) -> dict:
    """Run a scan and return its summary as a plain dict (Celery-serializable)."""
    summary = scan(
        queries,
        months_back=months_back,
        months_forward=months_forward,
        sources=sources,
        embed=embed,
    )
    logger.info(
        "literature scan: %s new of %s unique (%s embedded) over %s",
        summary.new,
        summary.unique,
        summary.embedded,
        summary.window,
    )
    return summary.as_dict()

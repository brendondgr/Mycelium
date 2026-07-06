"""Pivot-RP (ProQuest) grants & conferences ingestion.

Vendored from the standalone ``ProQuest`` tool. This package is the **collect**
side of the opportunity pipeline: it turns Pivot funding/papers-invited data into
:class:`apps.content.models.ContentItem` rows (``type`` grant/conference) that the
``content`` app then matches per user — mirroring how ``apps.scraper.ingest``
feeds paper suggestions.

Two entry surfaces:

* **Import** (no browser) — :mod:`.importer` reads the tool's already-scraped
  JSON / SQLite output; :mod:`.ingest` upserts + embeds + prunes into
  ``ContentItem``. This is the tested, unattended-safe path.
* **Scrape** (best-effort) — :mod:`.scrape` drives the vendored Playwright
  scrapers when a valid saved session exists, else it is a no-op. Playwright is an
  optional extra (``uv sync --extra pivot`` + ``playwright install chromium``) and
  is imported lazily, so import/match never depend on it.

Pure helpers (:mod:`.normalize`, :mod:`.deadlines`, :mod:`.status`) carry no DB or
network dependency and are shared by both the collect side and the ``content``
matching side.
"""

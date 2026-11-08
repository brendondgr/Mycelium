"""Collect currently-open research funding opportunities from free public sources.

Five stages, one canonical record shape, three layers of deduplication.
Vendored from the standalone ``research-collector`` project's
``utils/grants/collect/`` (see ``docs/plans/open-opportunity-collector.md`` for
the adapter-by-adapter probe findings this package was built on). The
retrieval/ranking half of that project (``rank.py``, and everything under
``utils/grants/{retrieval,embedding,suggest,...}``) was deliberately dropped —
Mycelium has its own ranking stack in ``apps.content``.
"""

from tools.retrieval.collect.grants.pipeline import CollectConfig, Pipeline
from tools.retrieval.collect.grants.record import Opportunity
from tools.retrieval.collect.grants.store import Store

__all__ = ["CollectConfig", "Opportunity", "Pipeline", "Store"]

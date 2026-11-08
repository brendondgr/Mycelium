"""The retrieval write door: how the corpus changes.

Collecting and ingesting (papers, grants, conferences, fellowships), resolving
a link someone pasted into a corpus item, merging duplicates, and keeping
deadlines and liveness current. Retrieval publishes events
(``tools/retrieval/events.py``) and never calls into what is built on it.
"""

from tools.retrieval.collect.ingest import prune_expired, upsert_items
from tools.retrieval.deadlines_projection import rebuild_all, rebuild_deadlines_for
from tools.retrieval.dedupe import dedupe_papers, merge_content_items
from tools.retrieval.fellowships.ingest import ingest_fellowships
from tools.retrieval.ingest import scan
from tools.retrieval.resolver import ResolveError, resolve_external

__all__ = [
    "ResolveError",
    "dedupe_papers",
    "ingest_fellowships",
    "merge_content_items",
    "prune_expired",
    "rebuild_all",
    "rebuild_deadlines_for",
    "resolve_external",
    "scan",
    "upsert_items",
]

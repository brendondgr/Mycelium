"""The full-text engine: resolve an identifier, route it, fetch it, convert it.

Plain Python with no Django imports, so it can be tested alone and used from
the evaluation harness. The Django side of the tool (``tools/fulltext/*.py``)
builds the credentials and the shared state, and decides where files live.

Ported from the PubMedExtraction project (``server/`` and
``pipeline/fulltext.py``) with three changes: PDFs convert with ``pypdf``
instead of the AGPL-licensed ``pymupdf4llm``; the per-process switch-offs,
throttles and remembered answers sit behind :mod:`.state` so several workers
can share them; and on-disk caches are written atomically, one file per key.
"""

"""Events the retrieval tool publishes (``tools._framework.events``).

Retrieval is the foundation: it never calls into what is built on it. Whoever
keeps rows that point at a ``ContentItem`` subscribes here instead.

``retrieval.items_merging``
    ``survivor``, ``loser`` (``ContentItem``). Published by
    :func:`tools.retrieval.dedupe.merge_content_items` inside its transaction,
    before the loser is deleted. A handler repoints its own rows from the loser
    to the survivor, reconciling any unique constraint. A handler that raises
    aborts the whole merge.
"""

ITEMS_MERGING = "retrieval.items_merging"

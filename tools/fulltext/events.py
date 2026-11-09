"""Events fulltext publishes (``tools._framework.events.publish``).

``fulltext.retrieved`` — a paper's full text was fetched and stored for the
first time. Payload: ``document`` (a ``FulltextDocument``) and
``content_item`` (the corpus ``ContentItem`` it is the full text of, or None
when the paper is not in the corpus). Not published when a request is answered
from the store.
"""

RETRIEVED = "fulltext.retrieved"

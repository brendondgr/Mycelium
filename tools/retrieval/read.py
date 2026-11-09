"""The retrieval read door: what other tools and the platform read from the corpus.

Retrieval knows nothing about people. Everything here answers a question about
the corpus itself — what an item is, what is near a vector, what matches a
query, whether an opportunity is still live.

The names below are the stable surface. The modules listed in the tool's
``exports`` are still imported directly by code that predates the doors; new
code reads through this module.
"""

from tools.retrieval.embeddings import embed_text, embed_texts
from tools.retrieval.geography import ONLINE, Place, item_continent, place_for
from tools.retrieval.index import PgVectorIndex, latest_gather_date, retrieve_for_vector
from tools.retrieval.liveness import is_expired, is_live, is_stale
from tools.retrieval.models import ContentDeadline, ContentItem
from tools.retrieval.protocols import Retrievable, VectorIndex
from tools.retrieval.query_embedding import embed_query
from tools.retrieval.search import SearchFilters, SearchResult, run_search

__all__ = [
    "ContentDeadline",
    "ContentItem",
    "ONLINE",
    "Place",
    "PgVectorIndex",
    "Retrievable",
    "VectorIndex",
    "embed_query",
    "embed_text",
    "embed_texts",
    "is_expired",
    "is_live",
    "is_stale",
    "item_continent",
    "latest_gather_date",
    "place_for",
    "retrieve_for_vector",
    "run_search",
    "SearchFilters",
    "SearchResult",
]

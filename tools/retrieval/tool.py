"""The retrieval tool: the grounded corpus everything else is built on.

Standard library and spec imports only (see tools/README.md).
"""

from tools._framework.spec import Setting, Stage, Tool


class RetrievalTool(Tool):
    name = "retrieval"
    #: The corpus tables and their whole migration history were created under
    #: the ``content`` app label, and the platform's own migrations depend on
    #: that history, so this tool keeps it.
    label = "content"
    summary = (
        "The grounded corpus: paper sources, the grant, conference and "
        "fellowship collectors, deduplication, embeddings, deadlines, and search "
        "over it. Knows nothing about people."
    )
    core = True
    exports = (
        "read",
        "service",
        "events",
        # Imported directly from outside this tool today (the boundary test
        # checks every such import is listed here). New code uses the doors.
        "collect",
        "deadlines_projection",
        "dedupe",
        "embedding",
        "embeddings",
        "fellowships",
        "index",
        "ingest",
        "lexical",
        "liveness",
        "models",
        "protocols",
        "query_embedding",
        "resolver",
        "search",
        "window",
    )
    settings = (
        # Literature sources. Keys are secrets: environment only. (The OpenAlex
        # and Semantic Scholar keys stay platform settings: author import in
        # apps.accounts reads them too.)
        Setting("pubmed_api_key", "str", "",
                "PubMed API key; optional, it only raises the NCBI rate limit.",
                env="PUBMED_API_KEY", django="PUBMED_API_KEY", secret=True),
        # Embeddings.
        Setting("embedding_model", "str", "BAAI/bge-small-en-v1.5",
                "The corpus embedding model (fastembed; the `embeddings` extra).",
                env="SCRAPER_EMBEDDING_MODEL", django="SCRAPER_EMBEDDING_MODEL"),
        Setting("embedding_device", "str", "auto",
                "auto runs on a CUDA GPU when ONNX Runtime exposes one (needs the "
                "embeddings-gpu extra), else the CPU; cuda demands the GPU; cpu "
                "pins the CPU.",
                env="EMBEDDING_DEVICE", django="EMBEDDING_DEVICE"),
        Setting("embedding_device_id", "str", "",
                "Which GPU on a multi-GPU host.",
                env="EMBEDDING_DEVICE_ID", django="EMBEDDING_DEVICE_ID"),
        Setting("embedding_batch_size_cpu", "int", 64, "fastembed batch on a CPU.",
                env="EMBEDDING_BATCH_SIZE_CPU", django="EMBEDDING_BATCH_SIZE_CPU"),
        Setting("embedding_batch_size_gpu", "int", 256, "fastembed batch on a GPU.",
                env="EMBEDDING_BATCH_SIZE_GPU", django="EMBEDDING_BATCH_SIZE_GPU"),
        # Liveness.
        Setting("opportunity_stale_days", "int", 60,
                "Days after its source stops listing it before an opportunity "
                "is treated as stale.",
                env="OPPORTUNITY_STALE_DAYS", django="OPPORTUNITY_STALE_DAYS"),
        # Search over the corpus.
        Setting("search_candidate_pool", "int", 500,
                "How deep the relevance ranking of a search goes.",
                env="SEARCH_CANDIDATE_POOL", django="SEARCH_CANDIDATE_POOL"),
        Setting("search_page_size", "int", 20, "Search results per page.",
                env="SEARCH_PAGE_SIZE", django="SEARCH_PAGE_SIZE"),
        Setting("search_max_page_size", "int", 50, "Largest page a client may ask for.",
                env="SEARCH_MAX_PAGE_SIZE", django="SEARCH_MAX_PAGE_SIZE"),
        Setting("search_low_confidence_cosine", "float", 0.35,
                "Below this, a semantic match is shown as low-confidence.",
                env="SEARCH_LOW_CONFIDENCE_COSINE",
                django="SEARCH_LOW_CONFIDENCE_COSINE"),
        Setting("search_semantic_floor", "float", 0.30,
                "Inclusion gate for the semantic search channel.",
                env="SEARCH_SEMANTIC_FLOOR", django="SEARCH_SEMANTIC_FLOOR"),
        Setting("search_fuzzy_enabled", "bool", True,
                "Fuzzy (trigram) title matching in search.",
                env="SEARCH_FUZZY_ENABLED", django="SEARCH_FUZZY_ENABLED"),
        Setting("search_fuzzy_pool", "int", 200, "Fuzzy-match candidates considered.",
                env="SEARCH_FUZZY_POOL", django="SEARCH_FUZZY_POOL"),
    )
    stages = (
        Stage("prune_opportunities", "prune", "Pruning expired opportunities…"),
    )

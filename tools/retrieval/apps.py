from tools._framework.appconfig import ToolAppConfig


class RetrievalConfig(ToolAppConfig):
    """The retrieval tool. It keeps the ``content`` app label: the corpus tables
    (``content_contentitem`` …) and their whole migration history were created
    under it, and the platform's own migrations depend on that history."""

    name = "tools.retrieval"
    label = "content"
    verbose_name = "Retrieval"

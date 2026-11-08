from django.apps import AppConfig


class ContentConfig(AppConfig):
    """The matching and delivery code still waiting to become tools.

    Its models and migrations moved to the retrieval tool (``tools/retrieval``),
    which kept the ``content`` app label and table names; this app therefore has
    its own label and no models.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content"
    label = "content_app"

    def ready(self) -> None:
        # Wire the prune → reminder-stale signal (R2).
        from tools._framework import events
        from tools.retrieval.events import ITEMS_MERGING

        from . import (
            merge_handlers,
            signals,  # noqa: F401
        )

        for handler in merge_handlers.HANDLERS:
            events.subscribe(ITEMS_MERGING, handler)

from tools._framework.appconfig import ToolAppConfig


class DeliveryConfig(ToolAppConfig):
    name = "tools.delivery"
    label = "delivery"
    verbose_name = "Delivery"

    def ready(self) -> None:
        super().ready()
        from tools._framework import events

        # Wire the prune → reminder-stale signal (R2).
        from tools.delivery import announce, merge_handlers, signals  # noqa: F401
        from tools.recommendation.service import register_department_source
        from tools.retrieval.events import ITEMS_MERGING

        # Repoint saves, shares, seen marks, collections and suggestions when
        # retrieval merges two duplicate items.
        for handler in merge_handlers.HANDLERS:
            events.subscribe(ITEMS_MERGING, handler)

        # Departments are scored only for their announcement channels; tell the
        # recommendation tool which ones (it never imports this code).
        register_department_source(announce.enabled_departments)

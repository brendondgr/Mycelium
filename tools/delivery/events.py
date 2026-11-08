"""Events the delivery tool publishes (``tools._framework.events``).

None yet. Delivery subscribes to ``retrieval.items_merging`` (its
``merge_handlers.py``), registers its announcement departments with the
recommendation tool (``register_department_source``), and listens to Django's
``pre_delete`` on ``ContentItem`` to mark reminders stale (``signals.py``).
"""

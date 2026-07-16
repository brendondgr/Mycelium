from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content"
    label = "content"

    def ready(self) -> None:
        # Wire the prune → reminder-stale signal (R2).
        from . import signals  # noqa: F401

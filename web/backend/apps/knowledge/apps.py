from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
    label = "knowledge"
    verbose_name = "Knowledge core"

    def ready(self) -> None:
        from . import signals  # noqa: F401 - connects the save hooks

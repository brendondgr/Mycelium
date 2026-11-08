from django.apps import AppConfig


class ToolsFrameworkConfig(AppConfig):
    """The framework itself: ``manage.py tools`` and ``GET /api/tools/``."""

    name = "tools._framework"
    label = "tools"
    verbose_name = "Tools framework"
    default_auto_field = "django.db.models.BigAutoField"

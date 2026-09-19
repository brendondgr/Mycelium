from django.apps import AppConfig


class CollabConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.collab"
    label = "collab"
    verbose_name = "Collaboration network"

    def ready(self) -> None:
        from apps.accounts.signals import email_verified

        from .affiliation import on_email_verified

        email_verified.connect(on_email_verified, dispatch_uid="collab_affiliation")

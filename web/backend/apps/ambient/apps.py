from django.apps import AppConfig


class AmbientConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ambient"
    label = "ambient"

    def ready(self) -> None:
        # Mylo chat reaches the ledger through an event, so the platform never
        # imports the agent tool; with the tool absent, nothing publishes it.
        from tools._framework import events

        events.subscribe(
            "agent.thread_quiet", "apps.ambient.adapters.agent_chat:on_thread_quiet"
        )
        events.subscribe(
            "agent.thread_deleted",
            "apps.ambient.adapters.agent_chat:on_thread_deleted",
        )

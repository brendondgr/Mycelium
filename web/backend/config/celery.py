import os

from celery import Celery, signals

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("mycelium")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@signals.worker_ready.connect
def _warm_llm_servers(**_kwargs):
    """Ask each model server what it serves once, so the first lookup is
    cached (apps.core.llm_servers). Runs in the background; never fails a
    worker."""
    from apps.core import llm_servers

    llm_servers.warm()

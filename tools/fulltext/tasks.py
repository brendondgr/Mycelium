"""Celery tasks: run full-text requests on a worker, off the web request."""

from __future__ import annotations

from celery import shared_task

from .models import FulltextRequest


@shared_task(name="tools.fulltext.run_requests")
def run_requests(request_ids: list[str]) -> int:
    """Run the given requests (any not yet finished). Returns how many ran."""
    from . import jobs

    todo = [
        r for r in FulltextRequest.objects.filter(pk__in=request_ids) if not r.finished
    ]
    jobs.run(todo)
    return len(todo)

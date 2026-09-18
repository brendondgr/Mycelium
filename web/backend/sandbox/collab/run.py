"""Run the real pipeline over the seeded sandbox, timed and counted."""

from __future__ import annotations

import time

from apps.knowledge import papers, projection, works


class CountingModel:
    """The configured model, with every call counted and timed."""

    def __init__(self, complete=None) -> None:
        self.complete = complete or works._settings_complete
        self.calls = 0
        self.seconds = 0.0
        self.failures = 0

    def __call__(self, system: str, user: str) -> str | None:
        self.calls += 1
        started = time.monotonic()
        try:
            return self.complete(system, user)
        except Exception:
            self.failures += 1
            raise
        finally:
            self.seconds += time.monotonic() - started


def run_cn02() -> dict:
    out: dict = {}
    started = time.monotonic()
    out["projection"] = projection.sweep().as_dict()
    out["projection_seconds"] = round(time.monotonic() - started, 1)

    model = CountingModel()
    started = time.monotonic()
    out["first_pass"] = papers.refresh_pending(
        limit=10**9, lookups=0, complete=model
    ).as_dict()
    out["first_pass_seconds"] = round(time.monotonic() - started, 1)
    out["model_calls"] = model.calls
    out["model_failures"] = model.failures
    out["model_seconds_total"] = round(model.seconds, 1)
    out["model_seconds_mean"] = (
        round(model.seconds / model.calls, 2) if model.calls else None
    )

    # The same pass again must read nothing and call nothing.
    second = CountingModel()
    out["second_pass"] = papers.refresh_pending(
        limit=10**9, lookups=0, complete=second
    ).as_dict()
    out["second_pass_model_calls"] = second.calls
    again = projection.sweep()
    out["second_projection_writes"] = again.created + again.updated + again.deleted
    return out


def relink(threshold: float) -> dict:
    """Rebuild every concept and edge at another merge threshold, from the
    facets already stored — no model calls. How the linking trade-off (a split
    idea against two ideas merged into one) moves with the threshold."""
    from django.conf import settings
    from django.contrib.auth import get_user_model

    from apps.knowledge import demonstrated
    from apps.knowledge.models import Concept, ConceptMerge, Edge

    from .bootstrap import assert_sandboxed

    assert_sandboxed()
    Edge.objects.all().delete()
    ConceptMerge.objects.all().delete()
    Concept.objects.all().delete()
    settings.KNOWLEDGE_MERGE_COSINE = threshold
    started = time.monotonic()
    projection.sweep()
    for user in get_user_model().objects.filter(author_works__isnull=False).distinct():
        demonstrated.record_person(user)
    return {"threshold": threshold, "seconds": round(time.monotonic() - started, 1)}

"""Core-app models. Currently just the LLM usage ledger.

``apps.core`` had no models until now — it carried the shared LLM client, the
exactly-one-FK helper, and the health endpoint. The daily-run analytics report
needs to answer "how much did the model actually do last night?", and no single
process can answer it: the nightly run is a chain of separate management
commands, each in its own process, so an in-memory counter dies with the stage
that incremented it. The number has to be persisted as it happens.

:class:`LLMUsageDaily` is a **daily aggregate**, not a per-call log. A per-call
table would be the richer artifact, but a busy night is thousands of calls and
the report only ever reads sums, so one row per (day, component) keeps the table
permanently small and makes the read a trivial scan.
"""

from __future__ import annotations

from django.db import models


class LLMUsageDaily(models.Model):
    """One day's LLM call and token totals for one component on one server.

    ``component`` is the label the caller passed to
    :func:`apps.core.llm.build_llm_client` — ``papers``, ``briefing``,
    ``opportunities``, ``intake.clusters``, and so on. It is a plain string
    rather than a choices field on purpose: a new LLM-backed feature should be
    able to start reporting usage by naming itself, without a migration.

    Counters are incremented with ``F()`` expressions so concurrent stages
    (or Celery workers) accumulate instead of clobbering each other.
    """

    day = models.DateField(db_index=True)
    component = models.CharField(
        max_length=60,
        help_text="Which caller made the requests — 'papers', 'briefing', …",
    )
    server = models.CharField(
        max_length=60,
        default="local",
        help_text="Which model server answered — a [llm.providers] name; 'local' "
        "is the .env endpoint.",
    )
    calls = models.PositiveIntegerField(default=0)
    failures = models.PositiveIntegerField(
        default=0,
        help_text="Calls that raised — an unreachable endpoint, a timeout, or a "
        "response the client could not parse.",
    )
    # BigInteger: a full night across every user runs to millions of tokens, and
    # a wrapped counter is worse than no counter.
    prompt_tokens = models.BigIntegerField(default=0)
    completion_tokens = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day", "component", "server"]
        constraints = [
            models.UniqueConstraint(
                fields=["day", "component", "server"],
                name="core_llm_usage_unique_day_component_server",
            ),
        ]
        verbose_name = "LLM daily usage"
        verbose_name_plural = "LLM daily usage"

    @property
    def total_tokens(self) -> int:
        return int(self.prompt_tokens) + int(self.completion_tokens)

    def __str__(self) -> str:
        return f"{self.day} · {self.component}: {self.calls} call(s)"

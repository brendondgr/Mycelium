"""Record LLM calls and token spend into :class:`~apps.core.models.LLMUsageDaily`.

This is the write half of the LLM ledger the daily analytics report reads. It
sits directly inside :meth:`apps.core.llm.LLMClient.complete`, which is the one
seam every LLM-backed feature in the backend goes through, so a component gets
counted by naming itself and nothing else.

The single hard rule: **recording must never change what the caller sees.** An
LLM call that succeeded must not turn into an error because the counter could
not be written, and a call that failed must still raise its original exception.
So :func:`record` swallows everything — a missing table during a migration, a
closed connection in a teardown, a read-only replica — and logs at debug level.

The counter is deliberately outside any caller transaction semantics: if a
caller's transaction rolls back after a successful LLM call, the tokens were
still spent, and the ledger should still say so.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

#: Used when a client was built without naming itself. Showing up in the report
#: as "unlabelled" is the point — it makes an unlabelled call site findable.
UNKNOWN_COMPONENT = "unlabelled"

#: Both spellings appear across OpenAI-compatible servers.
_PROMPT_KEYS = ("prompt_tokens", "input_tokens")
_COMPLETION_KEYS = ("completion_tokens", "output_tokens")


def _token_count(usage: Mapping[str, Any] | None, keys: tuple[str, ...]) -> int:
    """Read a token count out of an OpenAI-style ``usage`` mapping."""
    if not usage:
        return 0
    for key in keys:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 0


def split_usage(usage: Mapping[str, Any] | None) -> tuple[int, int]:
    """Return ``(prompt_tokens, completion_tokens)`` from a usage mapping."""
    return (
        _token_count(usage, _PROMPT_KEYS),
        _token_count(usage, _COMPLETION_KEYS),
    )


def record(
    component: str,
    *,
    ok: bool,
    usage: Mapping[str, Any] | None = None,
    day: date | None = None,
) -> None:
    """Add one call (and its tokens) to today's ledger row. Never raises."""
    try:
        from django.db.models import F
        from django.utils import timezone

        from apps.core.models import LLMUsageDaily

        prompt_tokens, completion_tokens = split_usage(usage)
        row_day = day or timezone.localdate()
        label = (component or UNKNOWN_COMPONENT).strip()[:60] or UNKNOWN_COMPONENT

        # get_or_create then a targeted UPDATE: the update is a single atomic
        # statement, so parallel stages accumulate rather than overwrite.
        LLMUsageDaily.objects.get_or_create(day=row_day, component=label)
        LLMUsageDaily.objects.filter(day=row_day, component=label).update(
            calls=F("calls") + 1,
            failures=F("failures") + (0 if ok else 1),
            prompt_tokens=F("prompt_tokens") + prompt_tokens,
            completion_tokens=F("completion_tokens") + completion_tokens,
        )
    except Exception:  # noqa: BLE001 — accounting must never break a real call
        logger.debug("LLM usage not recorded for %r", component, exc_info=True)

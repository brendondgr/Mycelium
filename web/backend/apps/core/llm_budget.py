"""The nightly run's model-call budget (``nightly.model_calls`` in mycelium.toml).

An operator on a paid model API sets one number — the most language-model
calls a nightly run may make — and the run degrades past it instead of billing
on: every caller of :meth:`apps.core.llm.LLMClient.complete` already treats a
failed call as "write the deterministic version" (a ranking without a model
write-up, a briefing without the model's paragraph), so refusing the call is
all a budget needs to do.

**Scope: the nightly run only.** The budget counts from a starting point the
nightly orchestrator (``ops/nightly/manual_all.py``) records before its first
stage and hands to every stage as two environment variables:

``MYCELIUM_NIGHTLY_SINCE``     the date the run started (ISO)
``MYCELIUM_NIGHTLY_BASELINE``  calls already in the LLM ledger since that date

A process without them — a person onboarding, an admin running a command by
hand — is never budgeted, so a spent budget can never lock someone out of the
app during the day.

Usage is read from :class:`~apps.core.models.LLMUsageDaily`, the ledger every
call already writes, so parallel stages and threads share one count with no
extra bookkeeping. It is a ceiling, not an exact meter: calls in flight when the
line is crossed still finish.
"""

from __future__ import annotations

import logging
import os
from datetime import date

from django.conf import settings

logger = logging.getLogger(__name__)

ENV_SINCE = "MYCELIUM_NIGHTLY_SINCE"
ENV_BASELINE = "MYCELIUM_NIGHTLY_BASELINE"

_warned = False


class LLMBudgetExceeded(RuntimeError):
    """The nightly run has made as many model calls as the instance allows."""


def limit() -> int | None:
    """``nightly.model_calls``; ``None`` = unlimited."""
    return getattr(settings, "NIGHTLY_MODEL_CALLS", None)


def calls_since(day: date) -> int:
    """Every model call recorded in the ledger on or after ``day``."""
    from django.db.models import Sum

    from apps.core.models import LLMUsageDaily

    total = LLMUsageDaily.objects.filter(day__gte=day).aggregate(n=Sum("calls"))["n"]
    return int(total or 0)


def start(today: date | None = None) -> dict[str, str]:
    """The environment a nightly run hands its stages (see the module docstring)."""
    from django.utils import timezone

    day = today or timezone.localdate()
    return {ENV_SINCE: day.isoformat(), ENV_BASELINE: str(calls_since(day))}


def _window() -> tuple[date, int] | None:
    since = os.environ.get(ENV_SINCE, "").strip()
    if not since:
        return None
    try:
        return date.fromisoformat(since), int(os.environ.get(ENV_BASELINE, "0") or 0)
    except ValueError:
        logger.warning("ignoring malformed %s=%r", ENV_SINCE, since)
        return None


def used() -> int | None:
    """Model calls this nightly run has made, or ``None`` outside a nightly run."""
    window = _window()
    if window is None:
        return None
    since, baseline = window
    return max(0, calls_since(since) - baseline)


def check() -> None:
    """Raise :class:`LLMBudgetExceeded` once a nightly run has spent its budget."""
    global _warned
    cap = limit()
    if cap is None:
        return
    spent = used()
    if spent is None or spent < cap:
        return
    if not _warned:
        logger.warning(
            "nightly.model_calls budget of %d reached; the rest of this run "
            "continues without model calls",
            cap,
        )
        _warned = True
    raise LLMBudgetExceeded(
        f"the nightly model-call budget ({cap}) is spent; continuing without "
        "the model"
    )

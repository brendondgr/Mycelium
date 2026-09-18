"""The team-fit line, stored with each grant a target is shown (plan CN-03).

Computed at scoring time for every (target, grant) pair the nightly run already
scored, and kept on that pair's ``RelevanceScore.signals["team_fit"]`` — the
same storage rule the member-fit layer follows — so the feed reads it in the
query it already makes. Only coverage counts and usernames are stored; display
names resolve at read time.

Never fatal: the feed is written before this runs, and a failure here costs
the line, not the feed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from apps.content.models import RelevanceScore

from . import coverage

logger = logging.getLogger(__name__)

SIGNAL = "team_fit"


def _assess(target, content_ids) -> dict:
    kwargs = target.persist_kwargs
    if kwargs.get("target_user") is not None:
        return coverage.for_user(kwargs["target_user"], content_ids)
    if kwargs.get("target_lab") is not None:
        return coverage.for_lab(kwargs["target_lab"], content_ids)
    if kwargs.get("target_project") is not None:
        return coverage.for_project(kwargs["target_project"], content_ids)
    return {}


def annotate_target(target, *, log: Callable[[str], None] | None = None) -> int:
    """Write (or clear) the team-fit signal on every grant this target was shown.

    Returns how many rows changed. Idempotent: an unchanged fit writes nothing.
    """
    try:
        rows = list(
            RelevanceScore.objects.filter(
                **target.persist_kwargs, content__type="grant"
            ).only("pk", "content_id", "signals")
        )
        if not rows:
            return 0
        fits = _assess(target, [row.content_id for row in rows])
        changed = 0
        for row in rows:
            signals = dict(row.signals or {})
            fit = fits.get(str(row.content_id))
            wanted = fit.as_dict() if fit is not None and fit.slots else None
            if signals.get(SIGNAL) == wanted:
                continue
            if wanted is None:
                signals.pop(SIGNAL, None)
            else:
                signals[SIGNAL] = wanted
            row.signals = signals
            row.save(update_fields=["signals"])
            changed += 1
        if log and changed:
            log(f"team fit: {changed} grant(s) updated for {target.key}")
        return changed
    except Exception:  # pragma: no cover - defensive; the feed is already written
        logger.warning("team-fit annotation failed for %s", target.key, exc_info=True)
        return 0

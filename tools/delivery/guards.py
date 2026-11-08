"""Precondition guards for the relevance/scoring stage.

Scoring is not built yet, but its preconditions are enforceable now so work
cannot run out of order (brief test 8): a target may only be scored once it has
an embedding. The embedding hook (brief Phase F) persists the canonical text and,
once the scoring phase locks a dimension, the vector — until then targets are
not scorable.
"""

from __future__ import annotations

from typing import Any


class TargetNotScorable(ValueError):
    """Raised when a scoring target has no embedding yet."""


def is_scorable(target: Any) -> bool:
    return getattr(target, "embedding", None) is not None


def ensure_embedding_ready(target: Any) -> Any:
    """Return ``target`` if it has an embedding, else raise ``TargetNotScorable``."""
    if not is_scorable(target):
        raise TargetNotScorable(
            f"{target!r} has no embedding; it cannot be scored until the "
            f"scoring phase populates one."
        )
    return target

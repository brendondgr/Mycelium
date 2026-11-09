"""The tool's load-time health check: configuration only, no network."""

from __future__ import annotations

from . import config


def check() -> None:
    """Raise when the configuration is unusable. Missing keys are not an error:
    a keyed source without its key is simply off."""
    problems = config.problems()
    if problems:
        raise RuntimeError("; ".join(problems))

"""Standalone multi-source conference CFP collection.

Six stages -- fetch, parse, normalize, resolve, deduplicate, persist -- each
independently re-runnable from the previous stage's stored output. The resolve
stage is the one that does not exist in the funding pipeline and the one that
makes the output safe to show anyone.
"""

from apps.scraper.collect.conferences.record import (
    ConferenceInstance,
    ConferenceSeries,
    Deadline,
)

__all__ = ["ConferenceInstance", "ConferenceSeries", "Deadline"]

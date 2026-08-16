"""Collection machinery that does not know what it is collecting.

Two subsystems collect from public sources on the same terms — funding
opportunities in ``apps.scraper.collect.grants`` and conference calls for papers in
``apps.scraper.collect.conferences`` — and the parts of that job that are genuinely
content-agnostic live here: a deliberately slow HTTP client, run-scoped raw
payload storage, and pure text/date helpers.

The split is not tidiness. Every source these subsystems touch is a small
volunteer-run or publicly-funded service, and two divergent politeness
implementations is how one of them ends up blocking our IP. There is one
client, and its defaults are conservative.

Vendored from the standalone ``research-collector`` project's ``utils/collect_core/``.
The original repo kept backwards-compatible re-export shims at
``utils/grants/collect/http.py`` and ``rawstore.py`` so old import paths kept
working; those shims were not carried over here — every caller in this tree
imports from ``apps.scraper.collect.core`` directly.
"""

from __future__ import annotations

from apps.scraper.collect.core.http import (
    DEFAULT_CONTACT,
    DEFAULT_MIN_INTERVAL,
    RETRY_STATUS,
    USER_AGENT,
    FetchError,
    PoliteClient,
    Response,
)
from apps.scraper.collect.core.rawstore import RawBundle, RawStore, new_run_id, utc_now
from apps.scraper.collect.core.text import (
    clean_text,
    compact_json,
    dedupe_preserving_order,
    html_to_text,
    is_past,
    join_description,
    normalize_title,
    soonest_future,
    to_iso_date,
)

__all__ = [
    "DEFAULT_CONTACT",
    "DEFAULT_MIN_INTERVAL",
    "RETRY_STATUS",
    "USER_AGENT",
    "FetchError",
    "PoliteClient",
    "RawBundle",
    "RawStore",
    "Response",
    "clean_text",
    "compact_json",
    "dedupe_preserving_order",
    "html_to_text",
    "is_past",
    "join_description",
    "new_run_id",
    "normalize_title",
    "soonest_future",
    "to_iso_date",
    "utc_now",
]

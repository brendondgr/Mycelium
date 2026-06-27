"""Minimal JSON-over-HTTP helper, matching the stdlib pattern in apps/grants."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping
from typing import Any

DEFAULT_TIMEOUT = 30
USER_AGENT = "Mycelium intake (+https://mycelium.test)"


def fetch_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    merged_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        **(headers or {}),
    }
    request = urllib.request.Request(url, headers=merged_headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)

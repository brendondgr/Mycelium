"""Retrieve active project samples from NIH RePORTER."""

from __future__ import annotations

import json
import urllib.request

ENDPOINT = "https://api.reporter.nih.gov/v2/projects/search"
TIMEOUT_SECONDS = 30
USER_AGENT = "Mycelium grant prototype"
FISCAL_YEAR = 2026


def retrieve(limit: int) -> list[dict]:
    payload = {
        "criteria": {
            "include_active_projects": True,
            "fiscal_years": [FISCAL_YEAR],
        },
        "limit": limit,
        "offset": 0,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        response_data = json.load(response)

    records = response_data.get("results") or []
    if not isinstance(records, list):
        raise ValueError("NIH RePORTER response results was not a list")
    return [record for record in records if isinstance(record, dict)]

"""Retrieve active opportunity samples from Grants.gov."""

from __future__ import annotations

import json
import urllib.request

ENDPOINT = "https://api.grants.gov/v1/api/search2"
TIMEOUT_SECONDS = 30
USER_AGENT = "Mycelium grant prototype"


def retrieve(limit: int) -> list[dict]:
    payload = {
        "oppStatuses": "forecasted|posted",
        "rows": limit,
        "startRecordNum": 0,
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

    data = response_data.get("data") or {}
    records = data.get("oppHits") or []
    if not isinstance(records, list):
        raise ValueError("Grants.gov response data.oppHits was not a list")
    return [record for record in records if isinstance(record, dict)]

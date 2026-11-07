"""Retrieve active award samples from the NSF Award Search API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

ENDPOINT = "https://api.nsf.gov/services/v1/awards.json"
TIMEOUT_SECONDS = 30
USER_AGENT = "Mycelium grant prototype"
PRINT_FIELDS = (
    "id,title,abstractText,program,fundProgramName,transType,dirAbbr,divAbbr,"
    "expDate,estimatedTotalAmt,awardeeName,startDate,date,pdPIName,piEmail"
)


def retrieve(limit: int) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "ActiveAwards": "true",
            "rpp": str(limit),
            "offset": "0",
            "printFields": PRINT_FIELDS,
        }
    )
    request = urllib.request.Request(
        f"{ENDPOINT}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        response_data = json.load(response)

    response = response_data.get("response") or {}
    records = response.get("award") or []
    if not isinstance(records, list):
        raise ValueError("NSF response.award was not a list")
    return [record for record in records if isinstance(record, dict)]

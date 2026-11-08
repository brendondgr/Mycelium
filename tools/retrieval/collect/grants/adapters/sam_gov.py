"""SAM.gov contract opportunities — Broad Agency Announcements and research contracts.

This source is worth the trouble for one reason: these are **procurement
instruments, not grants**, so they never appear on Grants.gov. That makes it a
genuine, non-overlapping coverage gap rather than another duplicate feed — the
defense and defense-adjacent research offices publish BAAs here and nowhere else
in this system.

It needs a free API key from a self-registered account. Without one the adapter
stays off and says so, rather than failing mid-run or silently contributing zero
records that get mistaken for "no BAAs are open".
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from tools.retrieval.collect.core.http import PoliteClient
from tools.retrieval.collect.core.rawstore import RawBundle, new_run_id, utc_now
from tools.retrieval.collect.grants.adapters.base import BaseAdapter
from tools.retrieval.collect.grants.normalize import (
    clean_text,
    dedupe_preserving_order,
    join_description,
    to_iso_date,
)
from tools.retrieval.collect.grants.record import Opportunity

SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
VIEW_URL = "https://sam.gov/opp/{notice_id}/view"
API_KEY_ENV = "SAM_API_KEY"

PAGE_SIZE = 500
MAX_PAGES = 20
#: The API requires an explicit posted-date window and rejects open-ended queries.
LOOKBACK_DAYS = 365


class SAMGovAdapter(BaseAdapter):
    name = "sam_gov"
    funder_native = True
    phase = 6

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get(API_KEY_ENV, "")

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, f"no API key: set {API_KEY_ENV} (free, self-service registration)"
        return True, ""

    # -- stage 1 ----------------------------------------------------------

    def fetch(self, client: PoliteClient, *, limit: int | None = None) -> RawBundle:
        enabled, reason = self.available()
        if not enabled:
            raise RuntimeError(reason)

        run_id = new_run_id()
        today = date.today()
        window_start = today - timedelta(days=LOOKBACK_DAYS)
        collected: list[dict[str, Any]] = []
        offset = 0

        for _ in range(MAX_PAGES):
            remaining = None if limit is None else limit - len(collected)
            if remaining is not None and remaining <= 0:
                break
            size = PAGE_SIZE if remaining is None else min(PAGE_SIZE, remaining)

            url = (
                f"{SEARCH_URL}?api_key={self.api_key}&limit={size}&offset={offset}"
                f"&postedFrom={window_start:%m/%d/%Y}&postedTo={today:%m/%d/%Y}"
            )
            payload = client.get(url).json()
            if not isinstance(payload, dict):
                break
            page = [row for row in (payload.get("opportunitiesData") or []) if isinstance(row, dict)]
            collected.extend(page)
            if len(page) < size:
                break
            offset += len(page)

        return self.bundle(self.name, run_id, utc_now(), collected, window_start=str(window_start))

    # -- stage 2 ----------------------------------------------------------

    def parse(self, bundle: RawBundle) -> list[Opportunity]:
        records: list[Opportunity] = []
        for row in bundle.records:
            if not isinstance(row, dict):
                continue
            if not _is_research_notice(row):
                continue
            if clean_text(row.get("active")).lower() == "no":
                continue
            records.append(self._parse_one(row))
        return records

    def _parse_one(self, row: dict[str, Any]) -> Opportunity:
        notice_id = clean_text(row.get("noticeId"))
        deadline = row.get("responseDeadLine")
        office = row.get("officeAddress") or {}

        return Opportunity(
            source=self.name,
            source_record_id=notice_id,
            source_url=clean_text(row.get("uiLink")) or VIEW_URL.format(notice_id=notice_id),
            opportunity_number=clean_text(row.get("solicitationNumber")),
            record_kind="standalone",
            title=clean_text(row.get("title")),
            funder=clean_text(row.get("fullParentPathName", "").split(".")[0] or row.get("department")),
            funder_subunit=clean_text(row.get("subTier") or office.get("city")),
            description=join_description(row.get("description"), row.get("additionalInfoLink")),
            # Instrument type and the NAICS/classification codes are their own
            # columns now; none of them is a subject.
            categories=[],
            status="open",
            posted_date=to_iso_date(row.get("postedDate")),
            close_date=to_iso_date(deadline),
            close_date_text=clean_text(deadline),
            currency="USD",
            # These are procurement instruments, not grants — which is the whole
            # reason the adapter exists, so it is worth stating in a field rather
            # than leaving a reader to infer it from the source name.
            funding_instruments=["Procurement Contract"],
            opportunity_category=clean_text(row.get("baseType") or row.get("type")),
            assistance_listings=dedupe_preserving_order(
                [clean_text(row.get("naicsCode")), clean_text(row.get("classificationCode"))]
            ),
            eligibility=join_description(row.get("typeOfSetAsideDescription")),
            raw=row,
        )


def _is_research_notice(row: dict[str, Any]) -> bool:
    base = clean_text(row.get("baseType") or row.get("type")).lower()
    if not base:
        return False
    if "award" in base or "justification" in base:
        return False
    return True

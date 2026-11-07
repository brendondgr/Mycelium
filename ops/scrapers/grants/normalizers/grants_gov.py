"""Normalize Grants.gov opportunity records."""

from __future__ import annotations

from typing import Any

from normalizers.common import base_row, join_tags, stringify, utc_timestamp


def normalize_records(records: list[dict]) -> list[dict[str, str]]:
    retrieved_at = utc_timestamp()
    return [normalize_record(record, retrieved_at) for record in records]


def normalize_record(record: dict[str, Any], retrieved_at: str) -> dict[str, str]:
    row = base_row("grants_gov", record, retrieved_at)
    row.update(
        {
            "source_record_id": stringify(record.get("id")),
            "source_opportunity_number": stringify(record.get("number")),
            "title": stringify(record.get("title")),
            "agency": stringify(record.get("agency")),
            "agency_code": stringify(record.get("agencyCode")),
            "opportunity_type": stringify(
                record.get("fundingInstrumentType")
                or record.get("fundingInstrument")
                or record.get("docType")
            ),
            "status": stringify(record.get("oppStatus")),
            "deadline": stringify(record.get("closeDate")),
            "start_date": stringify(record.get("openDate")),
            "tags": join_tags(
                record.get("cfdaList"),
                record.get("categoryOfFundingActivity"),
                record.get("fundingActivityCategory"),
                record.get("fundingInstrumentType"),
            ),
        }
    )
    return row

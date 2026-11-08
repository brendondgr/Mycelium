"""Normalize NSF award records."""

from __future__ import annotations

from typing import Any

from normalizers.common import base_row, join_tags, stringify, utc_timestamp


def normalize_records(records: list[dict]) -> list[dict[str, str]]:
    retrieved_at = utc_timestamp()
    return [normalize_record(record, retrieved_at) for record in records]


def normalize_record(record: dict[str, Any], retrieved_at: str) -> dict[str, str]:
    research_domain = join_tags(
        record.get("dirAbbr"),
        record.get("divAbbr"),
        record.get("program"),
        record.get("fundProgramName"),
    )

    row = base_row("nsf_awards", record, retrieved_at)
    row.update(
        {
            "source_record_id": stringify(record.get("id")),
            "title": stringify(record.get("title")),
            "agency": "NSF",
            "agency_code": stringify(record.get("agency") or record.get("awardAgencyCode")),
            "opportunity_type": stringify(record.get("transType")),
            "research_domain": research_domain,
            "organization": stringify(record.get("awardeeName")),
            "principal_investigator": stringify(record.get("pdPIName")),
            "deadline": stringify(record.get("expDate")),
            "start_date": stringify(record.get("startDate")),
            "end_date": stringify(record.get("expDate")),
            "amount": stringify(record.get("estimatedTotalAmt")),
            "abstract": stringify(record.get("abstractText")),
            "tags": join_tags(
                record.get("dirAbbr"),
                record.get("divAbbr"),
                record.get("program"),
                record.get("fundProgramName"),
                record.get("transType"),
            ),
        }
    )
    return row

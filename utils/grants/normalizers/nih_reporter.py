"""Normalize NIH RePORTER project records."""

from __future__ import annotations

from typing import Any

from normalizers.common import base_row, join_tags, stringify, utc_timestamp


def normalize_records(records: list[dict]) -> list[dict[str, str]]:
    retrieved_at = utc_timestamp()
    return [normalize_record(record, retrieved_at) for record in records]


def normalize_record(record: dict[str, Any], retrieved_at: str) -> dict[str, str]:
    organization = record.get("organization")
    agency = record.get("agency_ic_admin") or record.get("agency_code")
    opportunity_type = join_tags(record.get("activity_code"), record.get("funding_mechanism"))
    research_domain = join_tags(
        record.get("spending_categories_desc"),
        record.get("terms"),
        record.get("pref_terms"),
    )

    row = base_row("nih_reporter", record, retrieved_at)
    row.update(
        {
            "source_record_id": stringify(record.get("appl_id")),
            "source_opportunity_number": stringify(record.get("opportunity_number")),
            "title": stringify(record.get("project_title")),
            "agency": stringify(agency),
            "agency_code": stringify(record.get("agency_code")),
            "opportunity_type": opportunity_type,
            "research_domain": research_domain,
            "eligibility": stringify(record.get("organization_type")),
            "organization": stringify(organization),
            "principal_investigator": stringify(record.get("contact_pi_name")),
            "deadline": stringify(record.get("project_end_date")),
            "start_date": stringify(record.get("project_start_date")),
            "end_date": stringify(record.get("project_end_date")),
            "amount": stringify(record.get("award_amount")),
            "url": stringify(record.get("project_detail_url")),
            "abstract": stringify(record.get("abstract_text")),
            "tags": join_tags(
                record.get("spending_categories"),
                record.get("spending_categories_desc"),
                record.get("terms"),
                record.get("pref_terms"),
                record.get("activity_code"),
            ),
        }
    )
    return row

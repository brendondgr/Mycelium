"""Shared normalization helpers and CSV field definitions."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

FIELDNAMES = [
    "source",
    "source_record_id",
    "source_opportunity_number",
    "title",
    "agency",
    "agency_code",
    "opportunity_type",
    "status",
    "research_domain",
    "eligibility",
    "organization",
    "principal_investigator",
    "deadline",
    "start_date",
    "end_date",
    "amount",
    "url",
    "abstract",
    "tags",
    "retrieved_at_utc",
    "raw_json",
]


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool | int | float):
        return str(value)
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, dict):
        compact = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return compact
    if isinstance(value, Iterable):
        return " | ".join(
            item
            for item in (stringify(child) for child in value)
            if item
        )
    return str(value).strip()


def compact_json(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def join_tags(*values: Any) -> str:
    tags: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for child_value in value.values():
                add(child_value)
            return
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, Iterable):
            for child in value:
                add(child)
            return
        else:
            candidates = [str(value)]

        for candidate in candidates:
            tag = candidate.strip()
            if tag and tag not in seen:
                tags.append(tag)
                seen.add(tag)

    for value in values:
        add(value)
    return " | ".join(tags)


def base_row(source: str, record: dict, retrieved_at: str) -> dict[str, str]:
    return {
        fieldname: ""
        for fieldname in FIELDNAMES
    } | {
        "source": source,
        "retrieved_at_utc": retrieved_at,
        "raw_json": compact_json(record),
    }

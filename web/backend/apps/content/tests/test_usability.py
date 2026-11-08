"""Usability checks on real collector records (plan Phase 2).

The fixtures are copied verbatim from the opportunity store: an EU Horizon call, a
US-only NSF programme, a small-business-only call, an NIH record missing its award
and applicant fields, a closed and an open fellowship, and a conference with two
submission rounds. Dates are pinned with an explicit ``today``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from tools.retrieval.models import ContentItem

from apps.content.usability import (
    BLOCK,
    OK,
    UNKNOWN,
    WARN,
    Reader,
    assess,
    blocking,
    summary,
    verdict,
)

RECORDS = json.loads(
    (Path(__file__).parent / "fixtures" / "usability_records.json").read_text()
)
UNIVERSITY_US = Reader(institution_type="higher_ed", country="US", buffer_days=14)
UNIVERSITY_DE = Reader(institution_type="higher_ed", country="DE", buffer_days=14)


def _item(key: str, kind: str = ContentItem.Type.GRANT) -> ContentItem:
    # Unsaved: the checks are pure and never touch the database.
    return ContentItem(type=kind, metadata=RECORDS[key])


def _by_key(checks):
    return {c.key: c for c in checks}


def test_eu_call_for_a_us_university_is_usable_with_a_warning() -> None:
    checks = _by_key(assess(_item("eu_horizon"), UNIVERSITY_US, date(2026, 8, 20)))
    assert checks["open"].status == OK
    assert checks["deadline"].status == OK
    assert "Tue, Sep 15, 2026" in checks["deadline"].label
    assert checks["feasible"].status == OK
    assert checks["country"].status == WARN
    assert "without EU funding" in checks["country"].label
    # Horizon topics list no applicant types; the text never mentions universities.
    assert checks["applicant"].status in (UNKNOWN, OK)


def test_eu_call_for_a_european_university_has_an_eligible_country() -> None:
    checks = _by_key(assess(_item("eu_horizon"), UNIVERSITY_DE, date(2026, 8, 20)))
    assert checks["country"].status == OK


def test_us_only_call_blocks_a_non_us_institution_with_the_quoted_field() -> None:
    reader = Reader(institution_type="higher_ed", country="GB")
    checks = _by_key(assess(_item("nsf_us_only"), reader, date(2026, 8, 20)))
    assert checks["country"].status == BLOCK
    assert checks["country"].field == "eligibility"


def test_us_only_call_is_open_to_a_us_university_from_its_text() -> None:
    checks = _by_key(assess(_item("nsf_us_only"), UNIVERSITY_US, date(2026, 8, 20)))
    assert checks["country"].status == OK
    # Applicant types say only "Others (see text)"; the text names IHEs.
    assert checks["applicant"].status == OK
    assert checks["applicant"].field == "eligibility"
    # A record with no deadline_date is not called "ok": it is unknown.
    assert checks["deadline"].status == UNKNOWN
    assert "feasible" not in checks


def test_small_business_call_blocks_a_university() -> None:
    checks = assess(_item("small_business_only"), UNIVERSITY_US, date(2026, 8, 20))
    held = blocking(checks)
    assert held is not None and held.key == "applicant"
    assert "small businesses" in held.label
    assert verdict(checks) == BLOCK


def test_missing_fields_give_unknown_never_ok() -> None:
    reader = Reader(institution_type="higher_ed", country="US", min_award=50_000)
    checks = _by_key(assess(_item("nih_missing_fields"), reader, date(2026, 8, 20)))
    assert checks["award"].status == UNKNOWN
    assert checks["applicant"].status == UNKNOWN
    assert checks["award"].field == "award_ceiling"


def test_a_round_that_closed_holds_the_item_back() -> None:
    checks = _by_key(assess(_item("eu_horizon"), UNIVERSITY_US, date(2026, 11, 5)))
    assert checks["deadline"].status == BLOCK
    assert checks["deadline"].label == "The last deadline has passed"


def test_inside_the_buffer_is_held_back() -> None:
    checks = _by_key(assess(_item("eu_horizon"), UNIVERSITY_US, date(2026, 9, 5)))
    assert checks["feasible"].status == BLOCK
    assert "inside your 14-day buffer" in checks["feasible"].label


def test_award_below_the_minimum_is_held_back() -> None:
    reader = Reader(min_award=100_000_000)
    checks = _by_key(assess(_item("eu_horizon"), reader, date(2026, 8, 20)))
    assert checks["award"].status == BLOCK
    assert "€93M" in checks["award"].label


def test_closed_fellowship_and_eligibility_counts() -> None:
    closed = _by_key(
        assess(
            _item("fellowship_closed", ContentItem.Type.FELLOWSHIP),
            Reader(fellowship_counts=(2, 5)),
            date(2026, 8, 20),
        )
    )
    assert closed["open"].status == BLOCK
    assert closed["eligibility"].label == "2 people may be eligible"

    nobody = _by_key(
        assess(
            _item("fellowship_open", ContentItem.Type.FELLOWSHIP),
            Reader(fellowship_counts=(0, 5)),
            date(2026, 8, 20),
        )
    )
    assert nobody["eligibility"].status == BLOCK
    assert nobody["open"].status == OK


def test_conference_reads_its_next_round_and_notices_when_all_passed() -> None:
    conf = _item("conference_two_rounds", ContentItem.Type.CONFERENCE)
    before = _by_key(assess(conf, Reader(buffer_days=14), date(2026, 8, 1)))
    assert before["deadline"].status == OK
    assert "Sep 10, 2026" in before["deadline"].label
    after = _by_key(assess(conf, Reader(buffer_days=14), date(2026, 10, 1)))
    assert after["deadline"].status == BLOCK
    assert after["deadline"].label == "The last deadline has passed"


@pytest.mark.parametrize(
    ("suited", "status"),
    [((), WARN), (("Ana R.",), OK), (("Ana R.", "Marco T."), OK)],
)
def test_team_coverage(suited, status) -> None:
    item = _item("eu_horizon")
    checks = _by_key(assess(item, Reader(suited=suited), date(2026, 8, 20)))
    assert checks["team"].status == status


def test_summary_carries_no_percentages_and_every_check_names_its_field() -> None:
    out = summary(assess(_item("eu_horizon"), UNIVERSITY_US, date(2026, 8, 20)))
    assert out["verdict"] == WARN
    for check in out["checks"]:
        assert check["field"]
        assert "%" not in check["label"]

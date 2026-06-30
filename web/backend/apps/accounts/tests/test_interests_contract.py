"""Phase A — the interests contract gate."""

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.interests import (
    CURRENT_VERSION,
    stamp_version,
    validate_interests,
)


def test_valid_v1_payload_accepted() -> None:
    data = {
        "version": 1,
        "statement": "I study cortical circuits.",
        "areas": ["computational neuroscience"],
        "keywords": ["cortex", "spiking"],
        "skills": ["Python"],
        "funding_needs": ["NIH"],
        "eligibility": {"citizenship": "any"},
        "seeking": ["postdoc"],
        "exclusions": ["pure theory"],
        "sources": {"openalex": "A123"},
    }
    validated = validate_interests(data)
    assert validated["version"] == 1
    assert validated["areas"] == ["computational neuroscience"]


def test_version_defaults_when_absent() -> None:
    validated = validate_interests({"areas": ["genomics"]})
    assert validated["version"] == CURRENT_VERSION


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        validate_interests({"areas": ["x"], "bogus": "nope"})
    assert "bogus" in str(exc.value)


def test_missing_areas_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        validate_interests({"skills": ["Python"]})
    assert "areas" in str(exc.value)


def test_unsupported_version_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_interests({"version": 99, "areas": ["x"]})


def test_areas_must_be_list_of_strings() -> None:
    with pytest.raises(ValidationError):
        validate_interests({"areas": "not-a-list"})


def test_stamp_version_wraps_legacy_row() -> None:
    stamped = stamp_version({"areas": ["x"], "skills": ["R"]})
    assert stamped["version"] == 1
    assert stamped["areas"] == ["x"]


def test_stamp_version_coerces_string_seeking_to_list() -> None:
    stamped = stamp_version({"areas": ["x"], "seeking": "PhD position"})
    assert stamped["seeking"] == ["PhD position"]


def test_stamp_version_on_empty_row() -> None:
    assert stamp_version({}) == {"version": 1}


def test_stamped_seeder_row_is_contract_valid() -> None:
    # What the updated seeder now writes for a student.
    row = {
        "version": 1,
        "areas": ["robotics"],
        "skills": ["Python", "deep learning"],
        "seeking": ["fellowship"],
    }
    assert validate_interests(row)["seeking"] == ["fellowship"]

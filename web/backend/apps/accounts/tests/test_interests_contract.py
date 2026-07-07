"""Phase A — the interests contract gate (including eligibility sub-contract)."""

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
        "eligibility": {"citizenship": "us", "stage": "doctoral_early"},
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


# ---- Eligibility sub-contract -----------------------------------------------


def test_eligibility_full_valid_block_accepted() -> None:
    data = {
        "areas": ["neuroscience"],
        "eligibility": {
            "citizenship": "us",
            "stage": "doctoral_early",
            "fields": ["Sciences/Engineering/Math", "Humanities"],
            "eligible_restrictions": ["Women"],
        },
    }
    validated = validate_interests(data)
    e = validated["eligibility"]
    assert e["citizenship"] == "us"
    assert e["stage"] == "doctoral_early"
    assert "Sciences/Engineering/Math" in e["fields"]
    assert "Women" in e["eligible_restrictions"]


def test_eligibility_defaults_when_absent() -> None:
    validated = validate_interests({"areas": ["x"]})
    assert "eligibility" not in validated   # optional field not defaulted when absent


def test_eligibility_empty_block_accepted() -> None:
    validated = validate_interests({"areas": ["x"], "eligibility": {}})
    e = validated["eligibility"]
    assert e["citizenship"] == "us"
    assert e["stage"] == ""
    assert e["fields"] == []
    assert e["eligible_restrictions"] == []


def test_eligibility_international_citizenship_accepted() -> None:
    validated = validate_interests({
        "areas": ["x"],
        "eligibility": {"citizenship": "international"},
    })
    assert validated["eligibility"]["citizenship"] == "international"


def test_eligibility_invalid_citizenship_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_interests({
            "areas": ["x"],
            "eligibility": {"citizenship": "alien"},
        })


def test_eligibility_invalid_stage_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_interests({
            "areas": ["x"],
            "eligibility": {"stage": "undergrad"},
        })


def test_eligibility_invalid_field_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_interests({
            "areas": ["x"],
            "eligibility": {"fields": ["Underwater Basket Weaving"]},
        })


def test_eligibility_invalid_restriction_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_interests({
            "areas": ["x"],
            "eligibility": {"eligible_restrictions": ["Race"]},
        })


def test_eligibility_career_stage_passthrough() -> None:
    """intake/agent.py writes career_stage inside eligibility; it must round-trip."""
    data = {
        "areas": ["x"],
        "eligibility": {
            "citizenship": "us",
            "stage": "doctoral_early",
            "career_stage": "phd",  # written by agent; not in formal vocab
        },
    }
    validated = validate_interests(data)
    assert validated["eligibility"]["career_stage"] == "phd"


def test_eligibility_unknown_extra_keys_passthrough() -> None:
    """Unknown keys inside eligibility pass through (backward compat)."""
    data = {
        "areas": ["x"],
        "eligibility": {
            "citizenship": "us",
            "university": "Florida State University",
            "is_illinois_student": False,
        },
    }
    validated = validate_interests(data)
    assert validated["eligibility"]["university"] == "Florida State University"
    assert validated["eligibility"]["is_illinois_student"] is False


def test_eligibility_fixture_profile_accepted() -> None:
    """The real fixture eligibility block from profile.json validates cleanly."""
    fixture_eligibility = {
        "citizenship": "us",
        "stage": "doctoral_early",
        "fields": ["Sciences/Engineering/Math"],
        "eligible_restrictions": [],
    }
    validated = validate_interests({
        "areas": ["Artificial Intelligence"],
        "eligibility": fixture_eligibility,
    })
    e = validated["eligibility"]
    assert e["citizenship"] == "us"
    assert e["stage"] == "doctoral_early"
    assert e["fields"] == ["Sciences/Engineering/Math"]

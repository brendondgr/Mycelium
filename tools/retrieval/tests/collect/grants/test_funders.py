"""Funder identity: one name per funder, and nothing merged that was not the same."""

from __future__ import annotations

from tools.retrieval.collect.grants.funders import (
    canonical_funder,
    department,
    funder_id,
)

# --- the measured split ---------------------------------------------------


def test_the_two_nsf_names_resolve_to_one():
    """144 records said one thing and 24 the other, so a filter lost part of NSF."""
    assert canonical_funder("U.S. National Science Foundation") == "National Science Foundation"
    assert canonical_funder("National Science Foundation") == "National Science Foundation"
    assert funder_id("U.S. National Science Foundation") == funder_id("National Science Foundation")


def test_nasa_headquarters_is_nasa():
    assert canonical_funder("NASA Headquarters") == "National Aeronautics and Space Administration"


# --- system markers -------------------------------------------------------


def test_aggregator_system_markers_are_stripped():
    """'- ERA' is Grants.gov's internal plumbing, not part of the CDC's name."""
    assert (
        canonical_funder("Centers for Disease Control and Prevention - ERA")
        == "Centers for Disease Control and Prevention"
    )
    assert canonical_funder("DOC NOAA - ERA Production") == "DOC NOAA"


def test_a_meaningful_suffix_is_not_stripped():
    """FEMA is who is funding it. A blanket 'drop anything after a dash' loses that."""
    assert (
        canonical_funder("Department of Homeland Security - FEMA")
        == "Department of Homeland Security - FEMA"
    )


# --- what must not happen -------------------------------------------------


def test_an_unknown_funder_is_left_alone_not_forced_onto_a_neighbour():
    """Forcing unrecognized names onto the nearest known one merges real funders."""
    assert canonical_funder("Bureau of Land Management") == "Bureau of Land Management"
    assert canonical_funder("Fish and Wildlife Service") == "Fish and Wildlife Service"


def test_two_different_bureaus_stay_different():
    assert funder_id("Bureau of Justice Assistance") != funder_id("Bureau of Land Management")


def test_a_missing_name_falls_back_to_the_agency_code():
    assert canonical_funder("", "NSF") == "National Science Foundation"
    assert canonical_funder("", "") == ""


# --- the department axis --------------------------------------------------


def test_department_gives_a_readable_label():
    assert department("HHS") == "Health and Human Services"
    assert department("EC") == "European Commission"


def test_an_unmapped_code_returns_itself_rather_than_nothing():
    """An unmapped agency is still consistently itself, just without a friendly name."""
    assert department("XYZ") == "XYZ"


def test_nih_is_not_rolled_up_into_its_department():
    """Grouping NIH's 665 records with FDA and CDC would make the facet worse.

    Operating unit and department are two axes, not one — collapsing them loses
    exactly the distinction a researcher filters on.
    """
    assert canonical_funder("National Institutes of Health", "HHS") == "National Institutes of Health"
    assert department("HHS") != "National Institutes of Health"

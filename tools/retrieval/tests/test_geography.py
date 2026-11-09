"""A conference's full location, country and continent (``geography.place_for``).

The records come in five shapes (measured on the live corpus, 2026-11-08): the
structured ``city`` + ``country``; only free ``place_text``; a venue name sitting
in ``city`` with the address in ``place_text``; nothing; and online-only. The post
used to show the venue alone for the third shape, and no continent for the second.
"""

from __future__ import annotations

import pytest

from tools.retrieval.geography import continent_for, place_for


def test_structured_city_and_country() -> None:
    place = place_for(
        {
            "city": "Montreal",
            "country_code": "CA",
            "country": "Canada",
            "place_text": "Montreal, Canada",
        }
    )
    assert place.display == "Montreal, Canada"
    assert (place.country, place.continent) == ("Canada", "North America")


def test_structured_without_place_text() -> None:
    place = place_for({"city": "", "country_code": "US", "country": "United States"})
    assert place.display == "United States"
    assert place.continent == "North America"


def test_a_venue_in_city_shows_the_full_address() -> None:
    place = place_for(
        {
            "city": "Royal Agricultural University (RAU)",
            "place_text": "Royal Agricultural University (RAU), Cirencester, UK.",
        }
    )
    assert place.display == "Royal Agricultural University (RAU), Cirencester, UK"
    assert place.continent == "Europe"


@pytest.mark.parametrize(
    ("text", "display", "continent"),
    [
        ("Ann Arbor, MI", "Ann Arbor, Michigan, United States", "North America"),
        ("Austin, Texas, USA", "Austin, Texas, USA", "North America"),
        ("Seoul, Republic of Korea", "Seoul, Republic of Korea", "Asia"),
        (
            "Providence, Rhode Island",
            "Providence, Rhode Island, United States",
            "North America",
        ),
        (
            "SLMath 17 Gauss Way Berkeley CA 94720",
            "SLMath 17 Gauss Way Berkeley CA 94720, United States",
            "North America",
        ),
        ("Brescia (Italy)", "Brescia (Italy)", "Europe"),
        ("Antalya, Turkiye", "Antalya, Turkiye", "Europe"),
        ("Leiden, the Netherlands", "Leiden, the Netherlands", "Europe"),
        ("Melbourne. Australia", "Melbourne. Australia", "Oceania"),
        (
            "Campo Grande, Mato Grosso do Sul - Brasil",
            "Campo Grande, Mato Grosso do Sul - Brasil",
            "South America",
        ),
        (
            "Rabat, Morocco — Hybrid Conference",
            "Rabat, Morocco — Hybrid Conference",
            "Africa",
        ),
        ("Lisbon, PT", "Lisbon, PT, Portugal", "Europe"),
        ("Athens,Greece", "Athens, Greece", "Europe"),
        ("Toronto, Ontario", "Toronto, Ontario, Canada", "North America"),
        ("Washington, D.C", "Washington, D.C, United States", "North America"),
    ],
)
def test_place_text_is_read_to_a_country(text, display, continent) -> None:
    place = place_for({"place_text": text})
    assert place.display == display
    assert place.continent == continent


@pytest.mark.parametrize(
    "text", ["Pittsburgh", "Atlanta, Georgia", "Riyadh, Saudi Arabi", "NeurIPS 2026"]
)
def test_an_unknown_tail_is_never_guessed(text) -> None:
    place = place_for({"place_text": text})
    assert place.display == text
    assert place.country == "" and place.continent == ""


def test_nothing_known() -> None:
    assert place_for({}).display == ""
    assert place_for({"place_text": "TBD"}).display == ""


def test_online_only_and_hybrid() -> None:
    assert place_for({"place_text": "Virtual"}).continent == "Online"
    assert place_for({"is_virtual": True}).display == "Online"
    hybrid = place_for(
        {
            "is_virtual": True,
            "is_hybrid": True,
            "city": "Paris",
            "country_code": "FR",
            "country": "France",
        }
    )
    assert hybrid.continent == "Europe"


def test_continent_for_codes_and_names() -> None:
    assert continent_for("JP") == "Asia"
    assert continent_for("", "United Kingdom") == "Europe"
    assert continent_for("ZZ", "Atlantis") == ""

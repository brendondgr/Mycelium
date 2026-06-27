"""Canned source payloads for intake tests — no network, fully deterministic.

Not collected as a test module (filename is not ``test_*``); imported by the
intake tests.
"""

from __future__ import annotations

from typing import Any

# --- OpenAlex: {author, works} ------------------------------------------------

OPENALEX_RAW: dict[str, Any] = {
    "author": {
        "id": "https://openalex.org/A5023888391",
        "display_name": "Ada Lovelace",
        "orcid": "https://orcid.org/0000-0002-1825-0097",
        "last_known_institutions": [
            {"display_name": "Analytical Engine Institute"}
        ],
    },
    "works": [
        {
            "id": "https://openalex.org/W1",
            "title": "Notes on the Analytical Engine",
            "publication_year": 2021,
            "cited_by_count": 120,
            "topics": [
                {
                    "display_name": "Computational Mathematics",
                    "subfield": {"display_name": "Numerical Analysis"},
                }
            ],
            "concepts": [
                {"display_name": "Computer Science", "level": 0},
                {"display_name": "Algorithm", "level": 2},
            ],
            "keywords": [{"display_name": "symbolic computation"}],
            "authorships": [
                {"author": {"display_name": "Ada Lovelace"}},
                {"author": {"display_name": "Charles Babbage"}},
            ],
        },
        {
            "id": "https://openalex.org/W2",
            "title": "On Recursive Operations",
            "publication_year": 2023,
            "cited_by_count": 55,
            "topics": [
                {
                    "display_name": "Theory of Computation",
                    "subfield": {"display_name": "Numerical Analysis"},
                }
            ],
            "concepts": [{"display_name": "Mathematics", "level": 0}],
            "keywords": [{"keyword": "recursion"}],
            "authorships": [
                {"author": {"display_name": "Ada Lovelace"}},
                {"author": {"display_name": "Luigi Menabrea"}},
            ],
        },
    ],
}

# --- Semantic Scholar: {author, papers} --------------------------------------

SEMANTIC_RAW: dict[str, Any] = {
    "author": {
        "authorId": "1741101",
        "name": "Ada Lovelace",
        "affiliations": ["Analytical Engine Institute"],
        "externalIds": {"ORCID": "0000-0002-1825-0097"},
    },
    "papers": [
        {
            "paperId": "p1",
            "title": "Notes on the Analytical Engine",
            "year": 2021,
            "citationCount": 120,
            "fieldsOfStudy": ["Computer Science", "Mathematics"],
            "s2FieldsOfStudy": [
                {"category": "Numerical Analysis", "source": "s2-fos-model"}
            ],
            "authors": [{"name": "Ada Lovelace"}, {"name": "Charles Babbage"}],
        },
        {
            "paperId": "p2",
            "title": "On Recursive Operations",
            "year": 2023,
            "citationCount": 55,
            "fieldsOfStudy": ["Computer Science"],
            "s2FieldsOfStudy": [{"category": "Theory of Computation"}],
            "authors": [{"name": "Ada Lovelace"}, {"name": "Luigi Menabrea"}],
        },
    ],
}

# --- Google Scholar (via scholarly): {author, publications} ------------------

SCHOLAR_RAW: dict[str, Any] = {
    "author": {
        "scholar_id": "abc123XYZ",
        "name": "Ada Lovelace",
        "affiliation": "Analytical Engine Institute",
        "interests": ["Computational Mathematics", "Theory of Computation"],
        "publications": [],
    },
    "publications": [
        {
            "author_pub_id": "abc123XYZ:pub1",
            "num_citations": 120,
            "bib": {
                "title": "Notes on the Analytical Engine",
                "pub_year": "2021",
                "author": "Ada Lovelace and Charles Babbage",
            },
        },
        {
            "author_pub_id": "abc123XYZ:pub2",
            "num_citations": 55,
            "bib": {
                "title": "On Recursive Operations",
                "pub_year": "2023",
                "author": "Ada Lovelace and Luigi Menabrea",
            },
        },
    ],
}


def scholar_selection_pubs() -> list[dict[str, Any]]:
    """30 synthetic publications for the select_publications test.

    Constructed so the most-cited are deliberately *not* the newest, with one
    paper that is both top-cited and most-recent (the overlap) and one
    missing-year paper that must never count as recent.
    """

    pubs: list[dict[str, Any]] = []

    # The overlap: highest citations AND newest year.
    pubs.append(
        {
            "author_pub_id": "OVERLAP",
            "num_citations": 10000,
            "bib": {"pub_year": "2030"},
        }
    )
    # Nine top-cited but old papers (citations 9000..1000, years 2000..2008).
    for i in range(9):
        pubs.append(
            {
                "author_pub_id": f"CITED{i}",
                "num_citations": 9000 - i * 1000,
                "bib": {"pub_year": str(2000 + i)},
            }
        )
    # Nine most-recent but low-cited papers (years 2029..2021, citations 10..90).
    for i in range(9):
        pubs.append(
            {
                "author_pub_id": f"RECENT{i}",
                "num_citations": 10 + i * 10,
                "bib": {"pub_year": str(2029 - i)},
            }
        )
    # A missing-year paper with mid citations (not top-10 cited, never recent).
    pubs.append(
        {
            "author_pub_id": "MISSING",
            "num_citations": 500,
            "bib": {"title": "no year"},
        }
    )
    # Ten filler papers in the mid range, in neither top list.
    for i in range(10):
        pubs.append(
            {
                "author_pub_id": f"FILL{i}",
                "num_citations": 100 + i * 30,
                "bib": {"pub_year": str(2010 + i)},
            }
        )
    return pubs

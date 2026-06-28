"""Abstracts are captured per source and flow into the LLM corpus."""

from apps.accounts.intake import build_corpus
from apps.accounts.intake.normalizers import openalex, scholar, semantic


def test_openalex_reconstructs_abstract_from_inverted_index() -> None:
    raw = {
        "author": {"id": "https://openalex.org/A1", "display_name": "Ada Lovelace"},
        "works": [
            {
                "title": "On Loops",
                "abstract_inverted_index": {
                    "Recursion": [0],
                    "drives": [1],
                    "computation": [2],
                },
            }
        ],
    }
    draft = openalex.normalize(raw)
    assert draft.evidence[0]["abstract"] == "Recursion drives computation"


def test_semantic_captures_abstract() -> None:
    raw = {
        "author": {"name": "Ada Lovelace"},
        "papers": [{"title": "On Loops", "abstract": "A study of recursion."}],
    }
    draft = semantic.normalize(raw)
    assert draft.evidence[0]["abstract"] == "A study of recursion."


def test_scholar_captures_abstract() -> None:
    raw = {
        "name": "Ada Lovelace",
        "publications": [
            {"bib": {"title": "On Loops", "abstract": "A study of recursion."}}
        ],
    }
    draft = scholar.normalize(raw)
    assert draft.evidence[0]["abstract"] == "A study of recursion."


def test_abstracts_reach_the_corpus() -> None:
    raw = {
        "author": {"name": "Ada Lovelace"},
        "papers": [{"title": "On Loops", "abstract": "A study of recursion."}],
    }
    draft = semantic.normalize(raw)
    corpus = build_corpus(draft, "")
    assert "A study of recursion." in corpus

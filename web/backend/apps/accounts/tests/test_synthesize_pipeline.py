"""The synthesize orchestration: corpus + LLM extraction + draft fallback."""

import json

from apps.accounts.intake import AuthorProfileDraft, build_corpus
from apps.accounts.intake.synthesize import synthesize_interests
from apps.accounts.interests import validate_interests


def _site_draft() -> AuthorProfileDraft:
    return AuthorProfileDraft(
        display_name="Ada Lovelace",
        institution="Analytical Engine Institute",
        areas=["computational mathematics"],
        keywords=["recursion"],
        external_ids={"openalex": "A1"},
        evidence=[{"title": "Notes on the Analytical Engine", "abstract": "On loops."}],
    )


# -- corpus -------------------------------------------------------------------


def test_corpus_includes_draft_signal_and_resume() -> None:
    corpus = build_corpus(_site_draft(), "Skills: Rust, Qiskit")
    assert "Notes on the Analytical Engine" in corpus
    assert "computational mathematics" in corpus
    assert "On loops." in corpus  # abstract included
    assert "Skills: Rust, Qiskit" in corpus


# -- LLM drives every field ---------------------------------------------------


def test_llm_fields_drive_the_interests() -> None:
    llm_json = json.dumps(
        {
            "statement": "I research quantum-safe cryptography.",
            "areas": ["post-quantum cryptography", "network security"],
            "keywords": ["lattice-based cryptography"],
            "methods": ["cryptanalysis"],
            "skills": ["Rust", "Qiskit"],
        }
    )
    _draft, interests = synthesize_interests(
        site_draft=_site_draft(), complete=lambda _p: llm_json
    )
    validate_interests(interests)  # contract-valid
    assert interests["statement"] == "I research quantum-safe cryptography."
    assert "post-quantum cryptography" in interests["areas"]
    assert interests["skills"] == ["Rust", "Qiskit"]
    # Provenance from the structured draft is preserved.
    assert interests["sources"]["openalex"] == "A1"


# -- deterministic fallback when no model -------------------------------------


def test_fallback_uses_structured_draft() -> None:
    # complete returns None -> extractor falls back to the draft's own signal.
    _draft, interests = synthesize_interests(
        site_draft=_site_draft(), complete=lambda _p: None
    )
    validate_interests(interests)
    assert "computational mathematics" in interests["areas"]
    assert interests["statement"]  # deterministic statement filled
    assert interests["sources"]["openalex"] == "A1"


def test_resume_only_fallback_extracts_skills() -> None:
    resume = (
        "Grace Hopper\nResearch Interests: compilers\nSkills: COBOL, assembly\n"
    )
    draft, interests = synthesize_interests(
        resume_text=resume, provenance={"resume": "uploaded"}, complete=lambda _p: None
    )
    assert "compilers" in interests["areas"]
    assert "COBOL" in interests["skills"]
    assert interests["sources"]["resume"] == "uploaded"
    assert draft.display_name == "Grace Hopper"

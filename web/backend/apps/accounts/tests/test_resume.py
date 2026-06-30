"""Résumé ingestion: text/PDF extraction, guards, and LLM/heuristic drafting."""

import json

import pytest

from apps.accounts.intake import (
    AuthorProfileDraft,
    draft_from_resume,
    extract_text,
    parse_resume,
)
from apps.accounts.intake.errors import AuthorImportError

RESUME_TEXT = """\
Ada Lovelace
Analytical Engine Institute

Research Interests: computational mathematics, theory of computation, analytical engines

Methods: formal proofs, numerical simulation

Technical Skills: Python, Rust, Fortran, symbolic computation

Keywords: recursion, algorithms, mechanical computation
"""


def _make_pdf(body_text: str) -> bytes:
    """Assemble a minimal but valid one-page PDF with correct xref offsets."""

    content = (
        b"BT /F1 12 Tf 72 720 Td (" + body_text.encode("latin-1") + b") Tj ET"
    )
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(content)).encode() + b">>\nstream\n" + content
        + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    size = len(objects) + 1
    out += b"xref\n0 " + str(size).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += b"trailer\n<</Size " + str(size).encode() + b"/Root 1 0 R>>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return out


# -- text extraction + guards -------------------------------------------------


def test_extract_text_from_plain_text() -> None:
    text = extract_text(RESUME_TEXT.encode("utf-8"), content_type="text/plain")
    assert "computational mathematics" in text


def test_extract_text_from_pdf() -> None:
    pdf = _make_pdf("Research Interests: robotics, control theory")
    text = extract_text(pdf, content_type="application/pdf", filename="cv.pdf")
    assert "robotics" in text.lower()


def test_extract_text_sniffs_pdf_by_magic_bytes() -> None:
    pdf = _make_pdf("Methods: kinematics, dynamics, and motion planning")
    # No content_type / filename hint — the %PDF- magic must still route to pypdf.
    text = extract_text(pdf)
    assert "kinematics" in text.lower()


def test_extract_text_rejects_empty() -> None:
    with pytest.raises(AuthorImportError):
        extract_text(b"")


def test_extract_text_rejects_oversize() -> None:
    with pytest.raises(AuthorImportError):
        extract_text(b"x" * (5 * 1024 * 1024 + 1), content_type="text/plain")


def test_extract_text_rejects_unsupported_type() -> None:
    with pytest.raises(AuthorImportError):
        extract_text(b"\x00\x01binary", content_type="image/png", filename="x.png")


def test_extract_text_rejects_textless_file() -> None:
    with pytest.raises(AuthorImportError):
        extract_text(b"hi", content_type="text/plain")  # under the min-length floor


def test_pdf_without_pypdf_fails_gracefully(monkeypatch) -> None:
    import sys

    # Simulate a backend whose deps are out of date (pypdf not installed): the
    # import must raise a handled AuthorImportError, never an uncaught 500.
    monkeypatch.setitem(sys.modules, "pypdf", None)
    pdf = _make_pdf("Research Interests: robotics, control theory")
    with pytest.raises(AuthorImportError):
        extract_text(pdf, content_type="application/pdf", filename="cv.pdf")


# -- heuristic drafting (no model) --------------------------------------------


def test_heuristic_extracts_sectioned_fields() -> None:
    draft = draft_from_resume(RESUME_TEXT, complete=lambda _p: None)
    assert isinstance(draft, AuthorProfileDraft)
    assert "computational mathematics" in draft.areas
    assert "Python" in draft.skills
    assert "recursion" in draft.keywords
    assert draft.display_name == "Ada Lovelace"
    assert "Analytical Engine Institute" in draft.institution


def test_heuristic_skills_reach_interests_contract() -> None:
    draft = draft_from_resume(RESUME_TEXT, complete=lambda _p: None)
    interests = draft.to_interests()
    assert "skills" in interests
    assert "Python" in interests["skills"]


# -- the LLM seam -------------------------------------------------------------


def test_llm_json_payload_is_used() -> None:
    payload = json.dumps(
        {
            "display_name": "Grace Hopper",
            "institution": "Harvard",
            "areas": ["compilers", "programming languages"],
            "keywords": ["COBOL"],
            "methods": ["language design"],
            "skills": ["assembly", "FLOW-MATIC"],
        }
    )
    draft = draft_from_resume("ignored", complete=lambda _p: f"```json\n{payload}\n```")
    assert draft.display_name == "Grace Hopper"
    assert "compilers" in draft.areas
    assert "assembly" in draft.skills


def test_unparseable_llm_answer_falls_back_to_heuristic() -> None:
    draft = draft_from_resume(RESUME_TEXT, complete=lambda _p: "sorry, no JSON here")
    assert "computational mathematics" in draft.areas  # heuristic recovered it


def test_llm_exception_falls_back_to_heuristic() -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("endpoint down")

    draft = draft_from_resume(RESUME_TEXT, complete=boom)
    assert "Python" in draft.skills


# -- end to end ---------------------------------------------------------------


def test_parse_resume_text_end_to_end() -> None:
    draft = parse_resume(
        RESUME_TEXT.encode("utf-8"),
        content_type="text/plain",
        filename="ada.txt",
        complete=lambda _p: None,
    )
    assert "theory of computation" in draft.areas

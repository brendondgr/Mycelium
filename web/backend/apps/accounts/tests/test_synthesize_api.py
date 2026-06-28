"""The synthesize endpoint: one site and/or a résumé -> draft + interests."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts import views
from apps.accounts.intake import AuthorProfileDraft

URL = "/api/auth/intake/synthesize/"

RESUME_TEXT = b"""\
Grace Hopper
Naval Postgraduate School

Research Interests: compilers, programming languages, distributed systems

Technical Skills: COBOL, assembly, FLOW-MATIC
"""


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(username="u", password="p")


def _site_draft() -> AuthorProfileDraft:
    return AuthorProfileDraft(
        display_name="Ada Lovelace",
        institution="Analytical Engine Institute",
        areas=["computational mathematics", "theory of computation"],
        keywords=["recursion"],
        external_ids={"openalex": "A1"},
        evidence=[{"title": "Notes on the Analytical Engine"}],
    )


def _resume_file() -> SimpleUploadedFile:
    return SimpleUploadedFile("cv.txt", RESUME_TEXT, content_type="text/plain")


def _resume_pdf() -> SimpleUploadedFile:
    """A minimal valid one-page PDF carrying a Research Interests line."""
    content = (
        b"BT /F1 12 Tf 72 720 Td (Research Interests: robotics, control theory) Tj ET"
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
    return SimpleUploadedFile("cv.pdf", out, content_type="application/pdf")


# -- validation ---------------------------------------------------------------


@pytest.mark.django_db
def test_requires_at_least_one_source(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(URL, {}, format="multipart")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_rejects_unknown_source(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(
        URL, {"source": "facebook", "identifier": "x"}, format="multipart"
    )
    assert resp.status_code == 400
    assert "source" in resp.data


@pytest.mark.django_db
def test_rejects_partial_site(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(URL, {"source": "openalex"}, format="multipart")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_rejects_bad_resume_type(client, user) -> None:
    client.force_authenticate(user)
    bad = SimpleUploadedFile("x.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
    resp = client.post(URL, {"resume": bad}, format="multipart")
    assert resp.status_code == 400
    assert "resume" in resp.data


# -- site only ----------------------------------------------------------------


@pytest.mark.django_db
def test_site_only_returns_statement_and_interests(client, user, monkeypatch) -> None:
    monkeypatch.setattr(views, "import_author", lambda i, s: _site_draft())
    client.force_authenticate(user)

    resp = client.post(
        URL, {"source": "openalex", "identifier": "A1"}, format="multipart"
    )
    assert resp.status_code == 200
    interests = resp.data["interests"]
    assert "computational mathematics" in interests["areas"]
    assert interests["statement"]  # natural-language statement filled
    assert interests["sources"]["openalex"] == "A1"


# -- résumé only --------------------------------------------------------------


@pytest.mark.django_db
def test_resume_only_extracts_skills_and_provenance(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(URL, {"resume": _resume_file()}, format="multipart")
    assert resp.status_code == 200
    interests = resp.data["interests"]
    assert "compilers" in interests["areas"]
    assert "COBOL" in interests["skills"]
    assert interests["sources"]["resume"] == "uploaded"
    assert resp.data["draft"]["display_name"] == "Grace Hopper"


# -- site + résumé merged -----------------------------------------------------


@pytest.mark.django_db
def test_site_and_resume_merge(client, user, monkeypatch) -> None:
    monkeypatch.setattr(views, "import_author", lambda i, s: _site_draft())
    client.force_authenticate(user)

    resp = client.post(
        URL,
        {"source": "openalex", "identifier": "A1", "resume": _resume_file()},
        format="multipart",
    )
    assert resp.status_code == 200
    areas = resp.data["interests"]["areas"]
    # Both sources contributed their areas into one merged draft.
    assert "computational mathematics" in areas  # from the site
    assert "compilers" in areas  # from the résumé
    assert "COBOL" in resp.data["interests"]["skills"]
    assert resp.data["interests"]["sources"]["resume"] == "uploaded"


@pytest.mark.django_db
def test_pdf_resume_is_parsed(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(URL, {"resume": _resume_pdf()}, format="multipart")
    assert resp.status_code == 200
    assert "robotics" in resp.data["interests"]["areas"]


@pytest.mark.django_db
def test_pdf_without_pypdf_returns_400_not_500(client, user, monkeypatch) -> None:
    import sys

    # An out-of-date backend (no pypdf) must surface a clean 400, never a 500.
    monkeypatch.setitem(sys.modules, "pypdf", None)
    client.force_authenticate(user)
    resp = client.post(URL, {"resume": _resume_pdf()}, format="multipart")
    assert resp.status_code == 400
    assert "resume" in resp.data


@pytest.mark.django_db
def test_llm_drives_fields_when_model_available(client, user, monkeypatch) -> None:
    import json as _json

    from apps.accounts.intake import extract as extract_module

    # Simulate a configured, reachable model returning a structured profile.
    llm_json = _json.dumps(
        {
            "statement": "I research post-quantum cryptography.",
            "areas": ["post-quantum cryptography"],
            "keywords": ["lattice-based cryptography"],
            "methods": ["cryptanalysis"],
            "skills": ["Rust"],
        }
    )
    monkeypatch.setattr(extract_module, "_settings_complete", lambda _prompt: llm_json)
    client.force_authenticate(user)

    resp = client.post(URL, {"resume": _resume_file()}, format="multipart")
    assert resp.status_code == 200
    interests = resp.data["interests"]
    # The model's fields win over the résumé heuristic's.
    assert interests["statement"] == "I research post-quantum cryptography."
    assert interests["areas"] == ["post-quantum cryptography"]
    assert interests["skills"] == ["Rust"]
    assert interests["sources"]["resume"] == "uploaded"


@pytest.mark.django_db
def test_requires_authentication(client) -> None:
    resp = client.post(URL, {"resume": _resume_file()}, format="multipart")
    assert resp.status_code in (401, 403)

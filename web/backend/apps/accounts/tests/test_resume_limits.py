"""Résumé and document uploads are bounded before they are parsed: the declared
size is checked before a byte is read, a lying size still stops one byte past
the limit, and a PDF is read only up to a page cap."""

from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.intake import resume
from apps.accounts.intake.errors import AuthorImportError


class _Upload:
    """An upload whose declared ``size`` and real bytes can disagree."""

    def __init__(self, data: bytes, size: int | None = None) -> None:
        self._data = io.BytesIO(data)
        self.size = len(data) if size is None else size
        self.content_type = "text/plain"
        self.name = "cv.txt"
        self.reads: list[int] = []

    def read(self, n: int = -1) -> bytes:
        self.reads.append(n)
        return self._data.read(n)


def _pdf(pages: list[str]) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_an_oversize_declared_upload_is_refused_before_it_is_read() -> None:
    upload = _Upload(b"x", size=resume.MAX_RESUME_BYTES + 1)
    with pytest.raises(AuthorImportError, match="too large"):
        resume.read_upload(upload)
    assert upload.reads == []


def test_an_upload_that_lies_about_its_size_stops_one_byte_past_the_limit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(resume, "MAX_RESUME_BYTES", 100)
    upload = _Upload(b"y" * 10_000, size=10)
    with pytest.raises(AuthorImportError, match="too large"):
        resume.read_upload(upload)
    assert upload.reads == [101]


def test_a_small_upload_reads_through() -> None:
    upload = _Upload(b"Research interests: coral reef acoustics and sonar.")
    assert "coral reef" in resume.extract_upload(upload)


def test_a_pdf_is_read_only_up_to_the_page_cap(monkeypatch) -> None:
    monkeypatch.setattr(resume, "MAX_RESUME_PAGES", 2)
    data = _pdf(
        ["Page one reef acoustics", "Page two sonar arrays", "Page three SECRET"]
    )
    text = resume.extract_text(data, filename="cv.pdf")
    assert "Page one" in text and "Page two" in text
    assert "SECRET" not in text


@pytest.mark.django_db
def test_the_project_state_upload_is_size_checked_before_reading(
    monkeypatch,
) -> None:
    from apps.research.models import Project

    monkeypatch.setattr(resume, "MAX_RESUME_BYTES", 1000)
    owner = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Synapse", scope_user=owner)
    client = APIClient()
    client.force_authenticate(owner)
    big = SimpleUploadedFile("big.txt", b"z" * 5000, content_type="text/plain")
    resp = client.post(
        f"/api/projects/{project.id}/state/extract/",
        {"file": big},
        format="multipart",
    )
    assert resp.status_code == 400
    assert "too large" in str(resp.data["file"])

"""The files tool: safety, visibility, extraction, deletion, and Mylo's use."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from tools.files import service, storage
from tools.files.models import StoredFile
from tools.files.storage import Refused

pytestmark = pytest.mark.django_db
BASE = "/api/tools/files"


@pytest.fixture(autouse=True)
def store_dir(tmp_path):
    with override_settings(FILES_DATA_DIR=str(tmp_path / "files")):
        yield tmp_path / "files"


def make_pdf(pages: list[str]) -> bytes:
    """A minimal real PDF with one text line per page (Helvetica)."""
    objects = ["<</Type/Catalog/Pages 2 0 R>>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<</Type/Pages/Kids[{kids}]/Count {len(pages)}>>")
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(
            f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents "
            f"{4 + 2 * i} 0 R/Resources<</Font<</F1 {font} 0 R>>>>>>"
        )
        objects.append(
            f"<</Length {len(content)}>>stream\n{content.decode()}\nendstream"
        )
    objects.append("<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        (
            f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF"
        ).encode()
    )
    return out.getvalue()


def blank_pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_docx(paragraphs: list[str], *, padding: int = 0) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", xml)
        if padding:
            z.writestr("pad.bin", b"\0" * padding)
    return buf.getvalue()


def make_user(username):
    from apps.billing.testing import paid_plan
    from django.contrib.auth.models import User

    user = User.objects.create_user(username=username, password="x")
    user.profile.is_verified = True
    user.profile.save(update_fields=["is_verified"])
    paid_plan(user)
    return user


def upload(user, data: bytes, name: str, kind="user", owner=None):
    owner_id = owner.pk if owner is not None else user.pk
    return service.store_upload(
        user, SimpleUploadedFile(name, data), owner_kind=kind, owner_id=owner_id
    )


@pytest.fixture
def world(db):
    from apps.accounts.models import Lab, LabMembership
    from apps.research.models import Project, ProjectMember

    class W:
        pass

    w = W()
    w.alice, w.bob, w.carol, w.admin = (
        make_user(n) for n in ("alice", "bob", "carol", "labadmin")
    )
    w.lab = Lab.objects.create(name="Lab", slug="lab")
    LabMembership.objects.create(user=w.alice, lab=w.lab, role="owner")
    LabMembership.objects.create(user=w.bob, lab=w.lab, role="member")
    LabMembership.objects.create(user=w.admin, lab=w.lab, role="admin")
    w.project = Project.objects.create(scope_lab=w.lab, name="P")
    ProjectMember.objects.create(project=w.project, user=w.bob)
    return w


# -- safety -------------------------------------------------------------------


def test_type_is_sniffed_from_the_bytes_not_the_name(world):
    assert storage.sniff(make_pdf(["x"]), "notes.txt") == "pdf"
    assert storage.sniff(b"a,b\n1,2\n", "data.csv") == "csv"
    assert storage.sniff(b"# Title\n", "readme.md") == "md"
    assert storage.sniff(b"plain words", "evil.pdf") == "txt"
    assert storage.sniff(make_docx(["hi"]), "x.bin") == "docx"
    with pytest.raises(Refused):
        storage.sniff(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff", "doc.pdf")
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("a.txt", "x")
    with pytest.raises(Refused):
        storage.sniff(zipped.getvalue(), "a.docx")


def test_size_cap(world, settings):
    settings.FILES_MAX_BYTES = 10
    with pytest.raises(Refused) as exc:
        upload(world.alice, b"x" * 11, "a.txt")
    assert exc.value.code == "too_large"


def test_zip_bomb_guard(world, monkeypatch):
    monkeypatch.setattr(storage, "DOCX_MAX_UNCOMPRESSED", 1000)
    with pytest.raises(Refused) as exc:
        upload(world.alice, make_docx(["hi"], padding=5000), "big.docx")
    assert exc.value.code == "too_large_unpacked"


def test_no_path_comes_from_a_filename(world, store_dir):
    row = upload(world.alice, b"secret notes", "../../../etc/passwd")
    assert row.filename == "passwd"
    files = list(Path(store_dir).rglob("original.*"))
    assert files == [
        store_dir / "user" / str(world.alice.pk) / str(row.pk) / "original.txt"
    ]
    with pytest.raises(ValueError):
        storage.folder("user", "../..", str(row.pk))


def test_downloads_are_attachments_never_inline(world):
    row = upload(world.alice, b"hello", "a.txt")
    c = APIClient()
    c.force_authenticate(world.alice)
    r = c.get(f"{BASE}/files/{row.pk}/download/")
    assert r.status_code == 200
    assert r["Content-Disposition"].startswith("attachment")
    assert r["X-Content-Type-Options"] == "nosniff"


# -- visibility -----------------------------------------------------------------


def test_visibility_per_owner_kind(world):
    from tools.files import access

    personal = upload(world.bob, b"mine", "mine.txt")
    lab_file = upload(world.bob, b"lab wide", "lab.txt", "lab", world.lab)
    proj_file = upload(world.alice, b"project", "p.txt", "project", world.project)
    assert access.can_see(world.bob, personal) and not access.can_see(
        world.alice, personal
    )
    assert access.can_see(world.alice, lab_file) and not access.can_see(
        world.carol, lab_file
    )
    assert access.can_see(world.bob, proj_file) and not access.can_see(
        world.carol, proj_file
    )
    c = APIClient()
    c.force_authenticate(world.carol)
    for row in (personal, lab_file, proj_file):
        assert c.get(f"{BASE}/files/{row.pk}/").status_code == 404


def test_the_file_list_is_filtered_in_sql_and_matches_can_see(
    world, django_assert_max_num_queries
):
    """Listing files never walks every file on the instance in Python: the
    visibility rule is one query, and it agrees with ``can_see`` row by row."""
    from apps.accounts.models import Department
    from apps.research.models import Project

    from tools.files import access

    dept = Department.objects.create(owner=world.alice, name="Dept")
    world.lab.department = dept
    world.lab.save(update_fields=["department"])
    other_lab_project = Project.objects.create(scope_user=world.carol, name="Mine")
    upload(world.bob, b"mine", "mine.txt")
    upload(world.bob, b"lab wide", "lab.txt", "lab", world.lab)
    upload(world.alice, b"project", "p.txt", "project", world.project)
    upload(world.alice, b"dept", "dept.txt", "department", dept)
    upload(world.carol, b"carol", "carol.txt")
    upload(world.carol, b"carol project", "cp.txt", "project", other_lab_project)
    every = list(StoredFile.objects.all())
    for user in (world.alice, world.bob, world.carol, world.admin):
        with django_assert_max_num_queries(3):  # fixed, whatever the file count
            got = access.visible_queryset(user)
        assert {f.pk for f in got} == {f.pk for f in every if access.can_see(user, f)}
    assert {f.filename for f in access.visible_queryset(world.carol)} == {
        "carol.txt",
        "cp.txt",
    }
    assert [f.filename for f in access.visible_queryset(world.bob, q="DEPT")] == [
        "dept.txt"
    ]


def test_who_may_add(world):
    with pytest.raises(Refused):
        upload(world.carol, b"x", "a.txt", "lab", world.lab)
    with pytest.raises(Refused):
        upload(world.bob, b"x", "a.txt", "project", world.project)  # bob can't edit it
    assert upload(world.alice, b"x", "a.txt", "project", world.project)


def test_the_same_bytes_are_stored_once_per_owner(world):
    a = upload(world.alice, b"same", "a.txt")
    b = upload(world.alice, b"same", "b.txt")
    assert a.pk == b.pk and StoredFile.objects.count() == 1


# -- extraction ----------------------------------------------------------------


def test_pdf_text_and_page_offsets(world):
    row = upload(
        world.alice, make_pdf(["First page words", "Second page words"]), "p.pdf"
    )
    assert row.status == "ready" and row.pages == 2
    text = service.text_of(row)
    assert "First page words" in text and "Second page words" in text
    assert service.pages_of(row)[0] == 1 and service.pages_of(row)[1] > 1


def test_scanned_pdf_has_no_text(world):
    row = upload(world.alice, blank_pdf(), "scan.pdf")
    assert row.status == "no_text" and "OCR" in row.extract_error


def test_docx_and_text_extraction(world):
    row = upload(world.alice, make_docx(["Alpha para", "Beta para"]), "d.docx")
    assert row.status == "ready" and "Beta para" in service.text_of(row)
    row = upload(world.alice, "naïve café".encode(), "u.txt")
    assert service.text_of(row) == "naïve café"


def test_text_route_is_line_numbered(world):
    row = upload(world.alice, b"one\ntwo\nthree", "a.txt")
    c = APIClient()
    c.force_authenticate(world.alice)
    body = c.get(f"{BASE}/files/{row.pk}/text/?offset=1&limit=1").json()
    assert body["lines"] == [{"n": 2, "text": "two"}] and body["total_lines"] == 3


# -- deletion --------------------------------------------------------------------


def test_delete_removes_the_bytes(world, store_dir):
    row = upload(world.alice, b"bye", "a.txt")
    folder = storage.folder("user", str(world.alice.pk), str(row.pk))
    assert folder.exists()
    c = APIClient()
    c.force_authenticate(world.alice)
    assert c.delete(f"{BASE}/files/{row.pk}/").status_code == 204
    assert not folder.exists()
    assert c.get(f"{BASE}/files/{row.pk}/").status_code == 404


def test_delayed_purge_sweeps_later(world, settings):
    from datetime import timedelta

    from django.utils import timezone

    settings.FILES_PURGE_AFTER_DAYS = 7
    row = upload(world.alice, b"later", "a.txt")
    service.delete(world.alice, row)
    folder = storage.folder("user", str(world.alice.pk), str(row.pk))
    assert folder.exists()
    assert service.purge_deleted() == 0
    assert service.purge_deleted(now=timezone.now() + timedelta(days=8)) == 1
    assert not folder.exists()


def test_who_may_delete(world):
    lab_file = upload(world.bob, b"x", "x.txt", "lab", world.lab)
    with pytest.raises(Refused):
        service.delete(world.carol, lab_file)
    service.delete(world.admin, lab_file)  # an admin of the owning lab


def test_files_check_reports_orphans(world, store_dir):
    row = upload(world.alice, b"x", "a.txt")
    orphan = (
        store_dir
        / "user"
        / str(world.alice.pk)
        / "00000000-0000-0000-0000-000000000000"
    )
    orphan.mkdir(parents=True)
    storage.remove(storage.folder("user", str(world.alice.pk), str(row.pk)))
    out = io.StringIO()
    call_command("files_check", stdout=out)
    assert "1 orphan folders, 1 rows without bytes" in out.getvalue()
    call_command("files_check", "--fix", stdout=io.StringIO())
    assert not orphan.exists()
    assert StoredFile.objects.get(pk=row.pk).status == "failed"

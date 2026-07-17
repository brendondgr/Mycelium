"""Lab logo upload / serve / clear endpoint (LabLogoView)."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership

# A minimal-but-valid PNG signature — the sniffer keys off the magic bytes only.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def _media_tmp(settings, tmp_path):
    """Keep uploaded logos out of the repo tree during tests."""
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="Reyes Lab", slug="reyes-lab")


@pytest.fixture
def lead(db, lab: Lab) -> User:
    user = User.objects.create_user(username="lena", password="p")
    LabMembership.objects.create(
        user=user, lab=lab, role=LabMembership.Role.OWNER, is_lead=True
    )
    return user


@pytest.fixture
def member(db, lab: Lab) -> User:
    user = User.objects.create_user(username="jordan", password="p")
    LabMembership.objects.create(user=user, lab=lab, role=LabMembership.Role.MEMBER)
    return user


def _png() -> SimpleUploadedFile:
    return SimpleUploadedFile("logo.png", PNG_BYTES, content_type="image/png")


@pytest.mark.django_db
def test_get_missing_logo_404(client: APIClient, lab: Lab, member: User) -> None:
    client.force_authenticate(member)
    assert client.get(f"/api/auth/labs/{lab.slug}/logo/").status_code == 404


@pytest.mark.django_db
def test_lead_uploads_then_member_serves(
    client: APIClient, lab: Lab, lead: User, member: User
) -> None:
    client.force_authenticate(lead)
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/logo/", {"file": _png()}, format="multipart"
    )
    assert resp.status_code == 200
    assert resp.data["has_logo"] is True
    assert isinstance(resp.data["logo_version"], int)

    client.force_authenticate(member)
    served = client.get(f"/api/auth/labs/{lab.slug}/logo/")
    assert served.status_code == 200
    assert served["Content-Type"] == "image/png"
    assert served["X-Content-Type-Options"] == "nosniff"
    assert b"".join(served.streaming_content) == PNG_BYTES


@pytest.mark.django_db
def test_plain_member_cannot_upload(
    client: APIClient, lab: Lab, member: User
) -> None:
    client.force_authenticate(member)
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/logo/", {"file": _png()}, format="multipart"
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_non_image_rejected(client: APIClient, lab: Lab, lead: User) -> None:
    client.force_authenticate(lead)
    bogus = SimpleUploadedFile(
        "notes.txt", b"just some text, not an image", content_type="text/plain"
    )
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/logo/", {"file": bogus}, format="multipart"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_lead_clears_logo(client: APIClient, lab: Lab, lead: User) -> None:
    client.force_authenticate(lead)
    client.post(
        f"/api/auth/labs/{lab.slug}/logo/", {"file": _png()}, format="multipart"
    )
    cleared = client.delete(f"/api/auth/labs/{lab.slug}/logo/")
    assert cleared.status_code == 200
    assert cleared.data["has_logo"] is False
    assert client.get(f"/api/auth/labs/{lab.slug}/logo/").status_code == 404


@pytest.mark.django_db
def test_mylabs_surfaces_logo_flags(
    client: APIClient, lab: Lab, lead: User
) -> None:
    client.force_authenticate(lead)
    before = client.get("/api/auth/labs/")
    assert before.status_code == 200
    assert before.data[0]["has_logo"] is False
    assert before.data[0]["logo_version"] is None

    client.post(
        f"/api/auth/labs/{lab.slug}/logo/", {"file": _png()}, format="multipart"
    )
    after = client.get("/api/auth/labs/")
    assert after.data[0]["has_logo"] is True
    assert isinstance(after.data[0]["logo_version"], int)

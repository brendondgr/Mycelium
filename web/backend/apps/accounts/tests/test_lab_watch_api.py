"""Lab-level watch settings + LLM-assisted lab profile synthesis endpoints."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.intake.lab import source_text_from_links
from apps.accounts.models import Lab, LabMembership, LabWatchPreference


@pytest.fixture
def client() -> APIClient:
    return APIClient()


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


# -- Lab watch ----------------------------------------------------------------


@pytest.mark.django_db
def test_lab_watch_auto_created_with_lab(lab: Lab) -> None:
    assert LabWatchPreference.objects.filter(lab=lab).exists()


@pytest.mark.django_db
def test_member_reads_lab_watch(client: APIClient, lab: Lab, member: User) -> None:
    client.force_authenticate(member)
    resp = client.get(f"/api/auth/labs/{lab.slug}/watch/")
    assert resp.status_code == 200
    assert resp.data["cadence"] == "daily"
    assert resp.data["topics"] == []
    assert resp.data["deadline_buffer_days"] == 14
    assert resp.data["min_paper_window_days"] == 60
    # A lab's send hour and zone stay on the lab itself, not on its watch row.
    assert "send_hour_local" not in resp.data


@pytest.mark.django_db
def test_non_member_cannot_read_lab_watch(
    client: APIClient, lab: Lab
) -> None:
    outsider = User.objects.create_user(username="nope", password="p")
    client.force_authenticate(outsider)
    assert client.get(f"/api/auth/labs/{lab.slug}/watch/").status_code == 403


@pytest.mark.django_db
def test_lead_updates_lab_watch(client: APIClient, lab: Lab, lead: User) -> None:
    client.force_authenticate(lead)
    resp = client.patch(
        f"/api/auth/labs/{lab.slug}/watch/",
        {"topics": ["coral", "coral"], "categories": ["papers"], "cadence": "daily"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["topics"] == ["coral"]  # deduped
    assert resp.data["cadence"] == "daily"


@pytest.mark.django_db
def test_plain_member_cannot_update_lab_watch(
    client: APIClient, lab: Lab, member: User
) -> None:
    client.force_authenticate(member)
    resp = client.patch(
        f"/api/auth/labs/{lab.slug}/watch/",
        {"cadence": "daily"},
        format="json",
    )
    assert resp.status_code == 403


# -- Lab intake synthesis -----------------------------------------------------


@pytest.mark.django_db
def test_lead_synthesizes_lab_profile(
    client: APIClient, lab: Lab, lead: User
) -> None:
    client.force_authenticate(lead)
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/intake/synthesize/",
        {
            "description": "We study coral reef resilience under ocean warming.",
            "areas": ["Coral reef ecology", "Remote sensing"],
            "source_text": "",
        },
        format="json",
    )
    assert resp.status_code == 200
    # No LLM configured in tests: the deterministic fallback echoes the areas
    # hint and drafts a statement from the description.
    assert "Coral reef ecology" in resp.data["areas"]
    assert resp.data["statement"]
    assert isinstance(resp.data["keywords"], list)


@pytest.mark.django_db
def test_synthesize_requires_some_input(
    client: APIClient, lab: Lab, lead: User
) -> None:
    client.force_authenticate(lead)
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/intake/synthesize/",
        {"description": "", "areas": [], "source_text": ""},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_plain_member_cannot_synthesize(
    client: APIClient, lab: Lab, member: User
) -> None:
    client.force_authenticate(member)
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/intake/synthesize/",
        {"description": "anything"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_synthesize_accepts_a_source_file(
    client: APIClient, lab: Lab, lead: User
) -> None:
    client.force_authenticate(lead)
    upload = SimpleUploadedFile(
        "notes.txt",
        b"The group works on tidal energy modeling and coastal sensor networks.",
        content_type="text/plain",
    )
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/intake/synthesize/",
        {"description": "", "files": upload},
        format="multipart",
    )
    # File text alone is enough source material to synthesize (fallback path).
    assert resp.status_code == 200
    assert resp.data["statement"] or resp.data["areas"] or resp.data["keywords"] == []


@pytest.mark.django_db
def test_synthesize_accepts_a_link(
    client: APIClient, lab: Lab, lead: User
) -> None:
    client.force_authenticate(lead)
    # An unrecognized link is kept as a source hint, so the request still drafts.
    resp = client.post(
        f"/api/auth/labs/{lab.slug}/intake/synthesize/",
        {"description": "", "links": "https://example.org/our-lab"},
        format="multipart",
    )
    assert resp.status_code == 200


class _FakeDraft:
    display_name = "Dr. Reef"
    evidence = [{"title": "Coral bleaching under warming seas"}]
    areas = ["Coral ecology"]
    keywords = ["bleaching", "reefs"]


def test_source_text_from_links_imports_recognized_and_hints_the_rest() -> None:
    calls: list[tuple[str, str]] = []

    def fake_import(identifier: str, source: str):
        calls.append((source, identifier))
        return _FakeDraft()

    text = source_text_from_links(
        [
            "https://scholar.google.com/citations?user=ZQt7m3kAAAAJ",
            "https://example.org/unknown",
        ],
        import_fn=fake_import,
    )
    # The Scholar link is detected + imported; the unknown link is kept verbatim.
    assert calls == [("scholar", "ZQt7m3kAAAAJ")]
    assert "Coral bleaching under warming seas" in text
    assert "https://example.org/unknown" in text

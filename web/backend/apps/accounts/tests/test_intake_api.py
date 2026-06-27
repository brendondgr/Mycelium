"""Phase G — author-import, intake session, and confirm-and-save endpoints."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.accounts import views
from apps.accounts.intake import AuthorProfileDraft
from apps.accounts.intake.resolve import ResolutionError


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(username="u", password="p")


def _draft() -> AuthorProfileDraft:
    return AuthorProfileDraft(
        display_name="Ada Lovelace",
        institution="Analytical Engine Institute",
        areas=["computational mathematics"],
        external_ids={"openalex": "A1"},
        evidence=[{"title": "Notes"}],
    )


@pytest.mark.django_db
def test_import_returns_draft_and_interests(client, user, monkeypatch) -> None:
    monkeypatch.setattr(views, "import_author", lambda i, s: _draft())
    client.force_authenticate(user)

    resp = client.post(
        "/api/auth/intake/import/",
        {"identifier": "A1", "source": "openalex"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["draft"]["display_name"] == "Ada Lovelace"
    assert resp.data["interests"]["areas"] == ["computational mathematics"]
    assert resp.data["interests"]["sources"]["openalex"] == "A1"


@pytest.mark.django_db
def test_import_requires_identifier_and_source(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(
        "/api/auth/intake/import/", {"source": "openalex"}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_import_reports_resolution_error(client, user, monkeypatch) -> None:
    def boom(identifier, source):
        raise ResolutionError("bad id")

    monkeypatch.setattr(views, "import_author", boom)
    client.force_authenticate(user)
    resp = client.post(
        "/api/auth/intake/import/",
        {"identifier": "???", "source": "openalex"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_intake_session_advances(client, user) -> None:
    client.force_authenticate(user)

    first = client.post(
        "/api/auth/intake/session/",
        {"interests": {}, "free_text": "I study genomes"},
        format="json",
    )
    assert first.status_code == 200
    assert first.data["question"] is not None
    assert first.data["done"] is False

    second = client.post(
        "/api/auth/intake/session/",
        {"interests": first.data["interests"], "answer": "genomics, machine learning"},
        format="json",
    )
    assert "genomics" in second.data["interests"]["areas"]
    assert "machine learning" in second.data["interests"]["areas"]


@pytest.mark.django_db
def test_confirm_saves_valid_interests(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(
        "/api/auth/intake/confirm/",
        {"interests": {"version": 1, "areas": ["genomics"]}},
        format="json",
    )
    assert resp.status_code == 200
    user.profile.refresh_from_db()
    assert user.profile.interests["areas"] == ["genomics"]


@pytest.mark.django_db
def test_confirm_rejects_unvalidated_contract(client, user) -> None:
    client.force_authenticate(user)
    resp = client.post(
        "/api/auth/intake/confirm/",
        {"interests": {"skills": ["python"]}},  # missing required areas
        format="json",
    )
    assert resp.status_code == 400

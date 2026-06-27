"""Phase F — the canonical-text + (re)embed hook."""

import pytest
from django.contrib.auth.models import User

from apps.accounts import embedding
from apps.accounts.embedding import apply_embedding, build_canonical_text
from apps.accounts.models import Department, Lab, Profile


@pytest.fixture
def reset_embedder():
    yield
    embedding.set_embedder(None)


def test_build_canonical_text_joins_sections() -> None:
    text = build_canonical_text(
        statement="I study cortical circuits.",
        areas=["neuroscience", "computation"],
        methods=["electrophysiology"],
        keywords=["cortex"],
    )
    assert "I study cortical circuits." in text
    assert "Areas: neuroscience, computation" in text
    assert "Methods: electrophysiology" in text
    assert "Keywords: cortex" in text


def test_build_canonical_text_skips_empty_sections() -> None:
    assert build_canonical_text(areas=["x"]) == "Areas: x"
    assert build_canonical_text() == ""


@pytest.mark.django_db
def test_save_builds_embedding_text() -> None:
    user = User.objects.create_user(username="emb", password="pass-123")
    profile = user.profile
    profile.interests = {
        "version": 1,
        "statement": "studying genomes",
        "areas": ["genomics"],
    }
    profile.save()

    profile.refresh_from_db()
    assert "studying genomes" in profile.embedding_text
    assert "Areas: genomics" in profile.embedding_text


@pytest.mark.django_db
def test_empty_profile_has_blank_embedding_text() -> None:
    user = User.objects.create_user(username="emb2", password="pass-123")
    assert user.profile.embedding_text == ""


@pytest.mark.django_db
def test_save_fires_reembed_trigger(reset_embedder) -> None:
    calls: list[str] = []

    def recording_embedder(text: str):
        calls.append(text)
        return None  # dimension still deferred

    embedding.set_embedder(recording_embedder)
    user = User.objects.create_user(username="emb3", password="pass-123")
    profile = user.profile
    profile.interests = {"version": 1, "areas": ["robotics"]}
    profile.save()

    assert any("Areas: robotics" in text for text in calls)


def test_apply_embedding_sets_vector_in_memory(reset_embedder) -> None:
    embedding.set_embedder(lambda text: [0.1, 0.2, 0.3])
    profile = Profile(interests={"version": 1, "areas": ["x"]})

    apply_embedding(profile)

    assert profile.embedding == [0.1, 0.2, 0.3]
    assert "Areas: x" in profile.embedding_text


@pytest.mark.django_db
def test_lab_surface_embeds_from_curated_columns() -> None:
    lab = Lab.objects.create(name="Reed Lab", slug="reed-lab")
    surface = lab.profile
    surface.statement = "modeling proteins"
    surface.areas = ["structural biology"]
    surface.save()

    surface.refresh_from_db()
    assert "modeling proteins" in surface.embedding_text
    assert "Areas: structural biology" in surface.embedding_text


@pytest.mark.django_db
def test_dept_surface_embeds(reset_embedder) -> None:
    owner = User.objects.create_user(username="o", password="pass-123")
    dept = Department.objects.create(owner=owner, name="Dept")
    surface = dept.profile
    surface.areas = ["climate science"]
    surface.save()

    surface.refresh_from_db()
    assert "Areas: climate science" in surface.embedding_text

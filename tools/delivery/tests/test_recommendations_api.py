"""Lab + project recommendation read feeds.

These read already-stored ``RelevanceScore`` rows, so they need no retrieval /
pgvector — the rows are created directly, mirroring what the matcher would persist.
"""

from datetime import timedelta

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project, ProjectMember
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _paper(title):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=title,
        metadata={"title": title, "abstract": title},
    )


def _grant(title):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="legacy",
        external_id=title,
        metadata={"title": title, "sponsor": "NSF", "deadline_date": "2026-12-01"},
    )


def _score(content, *, run_at="2026-07-05T00:00:00", rank=1, **target):
    return RelevanceScore.objects.create(
        content=content,
        score=0.9,
        signals={
            "run_at": run_at,
            "suggested": True,
            "rank": rank,
            "headline": "Fits",
            "reason": "Aligns with the group's work.",
            "verdict": "read",
            "source": "llm",
            "area": content.type,
        },
        **target,
    )


@pytest.mark.django_db
def test_lab_member_reads_lab_recommendations(client: APIClient) -> None:
    member = User.objects.create_user(username="m", password="p")
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    _score(_paper("Graph paper"), target_lab=lab)
    _score(_grant("Graph grant"), target_lab=lab)

    client.force_authenticate(member)
    resp = client.get("/api/labs/graph-lab/recommendations/")
    assert resp.status_code == 200
    assert resp.data["counts"] == {
        "papers": 1,
        "grants": 1,
        "conferences": 0,
        "fellowships": 0,
    }
    assert resp.data["papers"][0]["title"] == "Graph paper"
    assert resp.data["grants"][0]["title"] == "Graph grant"
    assert resp.data["generated_at"] == "2026-07-05T00:00:00"


@pytest.mark.django_db
def test_non_member_cannot_read_lab_recommendations(client: APIClient) -> None:
    Lab.objects.create(name="Graph Lab", slug="graph-lab")
    outsider = User.objects.create_user(username="out", password="p")
    client.force_authenticate(outsider)
    assert client.get("/api/labs/graph-lab/recommendations/").status_code == 403


@pytest.mark.django_db
def test_project_recommendations_are_scoped_to_the_project(client: APIClient) -> None:
    owner = User.objects.create_user(username="o", password="p")
    project = Project.objects.create(name="Cyber", scope_user=owner)
    ProjectMember.objects.create(project=project, user=owner)
    other = Project.objects.create(name="Other", scope_user=owner)
    _score(_paper("Cyber paper"), target_project=project)
    _score(_paper("Other paper"), target_project=other)

    client.force_authenticate(owner)
    resp = client.get(f"/api/projects/{project.id}/recommendations/")
    assert resp.status_code == 200
    assert resp.data["counts"]["papers"] == 1
    assert resp.data["papers"][0]["title"] == "Cyber paper"


@pytest.mark.django_db
def test_outsider_cannot_read_project_recommendations(client: APIClient) -> None:
    owner = User.objects.create_user(username="o", password="p")
    outsider = User.objects.create_user(username="out", password="p")
    project = Project.objects.create(name="Private", scope_user=owner)

    client.force_authenticate(outsider)
    assert (
        client.get(f"/api/projects/{project.id}/recommendations/").status_code == 403
    )


@pytest.mark.django_db
def test_recommendations_require_auth(client: APIClient) -> None:
    Lab.objects.create(name="Graph Lab", slug="graph-lab")
    assert client.get("/api/labs/graph-lab/recommendations/").status_code in (401, 403)


def _backdate(score: RelevanceScore, days: int) -> None:
    """Move a row's insert time back N days (``created_at`` is auto_now_add)."""
    RelevanceScore.objects.filter(pk=score.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )


@pytest.mark.django_db
def test_window_counts_bucket_matches_by_recency(client: APIClient) -> None:
    member = User.objects.create_user(username="m", password="p")
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)

    # Papers found at spread-out times: today / 3d / 20d / 100d / 400d ago.
    _backdate(_score(_paper("p-today"), target_lab=lab), 0)
    _backdate(_score(_paper("p-week"), target_lab=lab), 3)
    _backdate(_score(_paper("p-month"), target_lab=lab), 20)
    _backdate(_score(_paper("p-year"), target_lab=lab), 100)
    _backdate(_score(_paper("p-old"), target_lab=lab), 400)
    # A below-floor (not suggested) paper must never be counted.
    hidden = _score(_paper("p-hidden"), target_lab=lab)
    hidden.signals["suggested"] = False
    hidden.save()

    client.force_authenticate(member)
    resp = client.get("/api/labs/graph-lab/recommendations/")
    assert resp.status_code == 200
    papers = resp.data["window_counts"]["papers"]
    assert papers == {"today": 1, "week": 2, "month": 3, "year": 4}
    # No grants at all — the area is still reported as all-zero windows.
    assert resp.data["window_counts"]["grants"] == {
        "today": 0,
        "week": 0,
        "month": 0,
        "year": 0,
    }


@pytest.mark.django_db
def test_personal_window_counts_bucket_matches_by_recency(client: APIClient) -> None:
    user = User.objects.create_user(username="m", password="p")

    _backdate(_score(_paper("p-today"), target_user=user), 0)
    _backdate(_score(_paper("p-week"), target_user=user), 3)
    _backdate(_score(_grant("g-month"), target_user=user), 20)
    # A below-floor (not suggested) item must never be counted.
    hidden = _score(_paper("p-hidden"), target_user=user)
    hidden.signals["suggested"] = False
    hidden.save()

    client.force_authenticate(user)
    resp = client.get("/api/recommendations/window-counts/")
    assert resp.status_code == 200
    assert resp.data["window_counts"]["papers"] == {
        "today": 1,
        "week": 2,
        "month": 2,
        "year": 2,
    }
    assert resp.data["window_counts"]["grants"] == {
        "today": 0,
        "week": 0,
        "month": 1,
        "year": 1,
    }
    # No conferences/fellowships at all — still reported as all-zero windows.
    assert resp.data["window_counts"]["conferences"] == {
        "today": 0,
        "week": 0,
        "month": 0,
        "year": 0,
    }


@pytest.mark.django_db
def test_personal_window_counts_requires_auth(client: APIClient) -> None:
    assert client.get("/api/recommendations/window-counts/").status_code in (401, 403)


@pytest.mark.django_db
def test_interested_members_surface_strong_personal_matches(client: APIClient):
    """A lab item lists members whose own match for it clears the threshold."""
    keen = User.objects.create_user(username="keen", password="p")
    meh = User.objects.create_user(username="meh", password="p")
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    for u in (keen, meh):
        LabMembership.objects.create(user=u, lab=lab, role=LabMembership.Role.MEMBER)

    paper = _paper("Graph paper")
    _score(paper, target_lab=lab)
    # A strong personal match for keen, a weak one for meh.
    keen_score = _score(paper, target_user=keen)
    keen_score.signals["verdict"] = "read"
    keen_score.save()
    meh_score = _score(paper, target_user=meh)
    meh_score.signals["verdict"] = "file"
    meh_score.save()

    client.force_authenticate(keen)
    resp = client.get("/api/labs/graph-lab/recommendations/")
    assert resp.status_code == 200
    interested = resp.data["interested"][str(paper.id)]
    usernames = {m["username"] for m in interested}
    assert usernames == {"keen"}  # meh's 40% is below the threshold

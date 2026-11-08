"""Project collaboration surface: share feed, external ingest, seen ledger, events.

Exercises the endpoints in ``apps.research.views`` that back the Projects page:
share-to-feed (A), paste-a-link ingest (E, resolver mocked), the seen/dedup ledger
(B), weighted engagement events (D), and the backfill command.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APIClient
from tools.delivery.models import ProjectItemSeen, ProjectShare
from tools.recommendation.models import RelevanceEvent, RelevanceScore
from tools.retrieval.models import ContentItem
from tools.retrieval.resolver import ResolveError, ResolveResult

from apps.accounts.models import Lab, LabMembership
from apps.research.models import Project, ProjectMember


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="Reyes Lab", slug="reyes-lab")


@pytest.fixture
def pi(db, lab: Lab) -> User:
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


@pytest.fixture
def project(db, lab: Lab, member: User) -> Project:
    project = Project.objects.create(name="Reef Mapping", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=member)
    return project


def _paper(title: str = "Coral bleaching dynamics") -> ContentItem:
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=title,
        metadata={
            "title": title,
            "abstract": title,
            "authors": ["A. Reyes"],
            "venue": "Nature",
            "year": 2026,
        },
    )


def _project_score(project: Project, content: ContentItem) -> RelevanceScore:
    return RelevanceScore.objects.create(
        content=content,
        score=0.8,
        target_project=project,
        signals={"run_at": "2026-07-05T00:00:00", "suggested": True, "rank": 1},
    )


# --- Feature A: share to project + feed ------------------------------------ #


@pytest.mark.django_db
def test_member_shares_paper_into_feed(client, project, member):
    paper = _paper()
    client.force_authenticate(member)
    resp = client.post(
        f"/api/projects/{project.id}/shares/",
        {"content_item": str(paper.id), "note": "Great method"},
    )
    assert resp.status_code == 201
    assert (
        ProjectShare.objects.filter(
            project=project, content=paper, shared_by=member
        ).count()
        == 1
    )
    # seen ledger row via share; one weighted share event; no RelevanceScore touched.
    seen = ProjectItemSeen.objects.get(project=project, content=paper)
    assert seen.first_seen_via == ProjectItemSeen.Via.SHARE
    assert seen.seen_by.count() == 0  # a share is not an in-app view
    assert (
        RelevanceEvent.objects.filter(
            content=paper, action="share", weight=0.7
        ).count()
        == 1
    )
    assert RelevanceScore.objects.count() == 0

    feed = client.get(f"/api/projects/{project.id}/feed/")
    assert feed.status_code == 200
    assert feed.data["count"] == 1
    item = feed.data["items"][0]
    assert item["content_id"] == str(paper.id)
    assert item["note"] == "Great method"
    assert item["shared_by"]["username"] == "jordan"
    assert item["seen"]["seen_by_count"] == 0


@pytest.mark.django_db
def test_lab_member_not_on_project_cannot_share(client, lab, project):
    kai = User.objects.create_user(username="kai", password="p")
    LabMembership.objects.create(user=kai, lab=lab, role=LabMembership.Role.MEMBER)
    paper = _paper()
    client.force_authenticate(kai)
    resp = client.post(
        f"/api/projects/{project.id}/shares/", {"content_item": str(paper.id)}
    )
    assert resp.status_code == 403
    assert ProjectShare.objects.count() == 0


@pytest.mark.django_db
def test_non_visible_outsider_blocked_from_share_and_feed(client, project):
    outsider = User.objects.create_user(username="nope", password="p")
    paper = _paper()
    client.force_authenticate(outsider)
    assert (
        client.post(
            f"/api/projects/{project.id}/shares/", {"content_item": str(paper.id)}
        ).status_code
        == 403
    )
    assert client.get(f"/api/projects/{project.id}/feed/").status_code == 403


@pytest.mark.django_db
def test_pi_can_share_into_lab_project(client, project, pi):
    # A lab owner/admin is a participant even without an explicit ProjectMember row.
    paper = _paper()
    client.force_authenticate(pi)
    assert (
        client.post(
            f"/api/projects/{project.id}/shares/", {"content_item": str(paper.id)}
        ).status_code
        == 201
    )


@pytest.mark.django_db
def test_reshare_collapses_and_credits_cosharers(client, project, member, pi):
    paper = _paper()
    client.force_authenticate(member)
    client.post(
        f"/api/projects/{project.id}/shares/",
        {"content_item": str(paper.id), "note": "first"},
    )
    client.force_authenticate(pi)  # most recent share wins the row
    client.post(
        f"/api/projects/{project.id}/shares/",
        {"content_item": str(paper.id), "note": "second"},
    )
    assert ProjectShare.objects.filter(content=paper).count() == 2
    assert (
        ProjectItemSeen.objects.filter(project=project, content=paper).count() == 1
    )
    feed = client.get(f"/api/projects/{project.id}/feed/")
    assert feed.data["count"] == 1  # collapsed by content
    item = feed.data["items"][0]
    assert item["shared_by"]["username"] == "lena"
    assert item["note"] == "second"
    assert item["share_count"] == 2
    assert {c["username"] for c in item["co_sharers"]} == {"jordan"}


# --- Feature E: external paste-a-link ingest (resolver mocked) -------------- #


@pytest.mark.django_db
def test_paste_link_creates_external_share(client, project, member):
    paper = _paper("Ingested via DOI")
    client.force_authenticate(member)
    with patch(
        "tools.retrieval.resolver.resolve_external",
        return_value=ResolveResult(content_item=paper, created=True, embed_status="ok"),
    ) as mocked:
        resp = client.post(
            f"/api/projects/{project.id}/ingest-link/", {"raw_input": "10.1234/abcd"}
        )
    assert resp.status_code == 201
    mocked.assert_called_once_with("10.1234/abcd")
    assert resp.data["embed_status"] == "ok"
    share = ProjectShare.objects.get(project=project, content=paper)
    assert share.source == ProjectShare.Source.EXTERNAL_LINK
    seen = ProjectItemSeen.objects.get(project=project, content=paper)
    assert seen.first_seen_via == ProjectItemSeen.Via.EXTERNAL_LINK


@pytest.mark.django_db
def test_same_doi_dedups_content_but_adds_a_share(client, project, member):
    paper = _paper("One paper")
    client.force_authenticate(member)
    with patch("tools.retrieval.resolver.resolve_external") as mocked:
        mocked.side_effect = [
            ResolveResult(content_item=paper, created=True, embed_status="ok"),
            ResolveResult(content_item=paper, created=False, embed_status="ok"),
        ]
        client.post(f"/api/projects/{project.id}/ingest-link/", {"raw_input": "10.1/x"})
        client.post(
            f"/api/projects/{project.id}/ingest-link/",
            {"raw_input": "https://doi.org/10.1/x"},
        )
    assert ContentItem.objects.filter(id=paper.id).count() == 1  # one item
    assert ProjectShare.objects.filter(content=paper).count() == 2  # two shares
    feed = client.get(f"/api/projects/{project.id}/feed/")
    assert feed.data["count"] == 1
    assert feed.data["items"][0]["share_count"] == 2


@pytest.mark.django_db
def test_garbage_link_returns_422_and_creates_nothing(client, project, member):
    client.force_authenticate(member)
    with patch(
        "tools.retrieval.resolver.resolve_external",
        side_effect=ResolveError("Couldn't find a DOI or arXiv id."),
    ):
        resp = client.post(
            f"/api/projects/{project.id}/ingest-link/", {"raw_input": "hello world"}
        )
    assert resp.status_code == 422
    assert ProjectShare.objects.count() == 0
    assert ProjectItemSeen.objects.count() == 0


@pytest.mark.django_db
def test_empty_raw_input_is_400(client, project, member):
    client.force_authenticate(member)
    assert (
        client.post(
            f"/api/projects/{project.id}/ingest-link/", {"raw_input": "   "}
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_non_participant_cannot_ingest(client, project):
    outsider = User.objects.create_user(username="nope", password="p")
    client.force_authenticate(outsider)
    assert (
        client.post(
            f"/api/projects/{project.id}/ingest-link/", {"raw_input": "10.1/x"}
        ).status_code
        == 403
    )


# --- Feature B / D: seen ledger + weighted events -------------------------- #


@pytest.mark.django_db
def test_mark_seen_increments_only_on_actual_view(client, project, member, pi):
    paper = _paper()
    client.force_authenticate(pi)
    client.post(f"/api/projects/{project.id}/shares/", {"content_item": str(paper.id)})
    seen = ProjectItemSeen.objects.get(project=project, content=paper)
    assert seen.seen_by.count() == 0  # delivery/share does not count as a view

    client.force_authenticate(member)
    resp = client.post(f"/api/projects/{project.id}/items/{paper.id}/seen/")
    assert resp.status_code == 200
    assert resp.data["seen_by_count"] == 1
    assert resp.data["first_seen_via"] == ProjectItemSeen.Via.SHARE  # unchanged
    seen.refresh_from_db()
    assert list(seen.seen_by.values_list("username", flat=True)) == ["jordan"]
    assert RelevanceEvent.objects.filter(content=paper, action="view").count() == 1


@pytest.mark.django_db
def test_event_records_weighted_engagement(client, project, member):
    paper = _paper()
    client.force_authenticate(member)
    resp = client.post(
        f"/api/projects/{project.id}/events/",
        {"content_item": str(paper.id), "action": "thumbs_up"},
    )
    assert resp.status_code == 201
    assert resp.data["weight"] == 1.0
    event = RelevanceEvent.objects.get(content=paper, action="thumbs_up")
    assert event.weight == 1.0
    assert event.project_id == project.id


@pytest.mark.django_db
def test_unknown_event_action_is_400(client, project, member):
    paper = _paper()
    client.force_authenticate(member)
    resp = client.post(
        f"/api/projects/{project.id}/events/",
        {"content_item": str(paper.id), "action": "yeet"},
    )
    assert resp.status_code == 400
    assert RelevanceEvent.objects.count() == 0


# --- Backfill + digest-first dedup regression ------------------------------ #


@pytest.mark.django_db
def test_backfill_seeds_ledger_from_project_scores(project):
    paper = _paper()
    _project_score(project, paper)
    call_command("backfill_project_seen")
    seen = ProjectItemSeen.objects.get(project=project, content=paper)
    assert seen.first_seen_via == ProjectItemSeen.Via.DIGEST
    assert seen.seen_by.count() == 0
    before = ProjectItemSeen.objects.count()
    call_command("backfill_project_seen")  # idempotent
    assert ProjectItemSeen.objects.count() == before


@pytest.mark.django_db
def test_sharing_a_digest_item_keeps_first_seen_via_digest(client, project, member):
    paper = _paper()
    _project_score(project, paper)
    call_command("backfill_project_seen")  # first_seen_via = digest
    client.force_authenticate(member)
    client.post(f"/api/projects/{project.id}/shares/", {"content_item": str(paper.id)})
    # get() asserts exactly one ledger row; first-wins keeps it 'digest'.
    seen = ProjectItemSeen.objects.get(project=project, content=paper)
    assert seen.first_seen_via == ProjectItemSeen.Via.DIGEST

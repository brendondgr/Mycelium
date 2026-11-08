"""Manual ignore: the endpoints, the feed filtering, and the reader boundary.

Like the saves API tests these read ``RelevanceScore`` / ``IgnoredItem`` rows
directly (no pgvector), so they run on SQLite.
"""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from tools.recommendation.models import RelevanceEvent, RelevanceScore
from tools.retrieval.models import ContentItem, IgnoredItem, SavedOpportunity

from apps.accounts.models import Lab, LabMembership


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _paper(pid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="openalex",
        external_id=pid,
        source_url=f"https://openalex.org/{pid}",
        metadata={
            "title": title,
            "abstract": f"Abstract for {title}.",
            "venue": "NeurIPS",
            "year": 2026,
            "authors": ["A. Researcher"],
        },
    )


def _grant(gid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="pivot",
        external_id=gid,
        source_url=f"https://pivot.proquest.com/funding_opps/{gid}",
        metadata={
            "title": title,
            "sponsor": "NSF",
            "amount": "$100,000",
            "website": "https://nsf.gov/x",
            "deadline_date": "2099-12-01",
            "next_kind": "application",
        },
    )


def _conference(cid, name):
    return ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="collect",
        external_id=cid,
        source_url=f"https://example.org/{cid}",
        metadata={
            "name": name,
            "location": "Vienna",
            "country": "Austria",
            "deadline_date": "2099-05-01",
            "next_kind": "abstract",
            # A conference with no date at all is hidden by `liveness.is_live`
            # regardless of the ignore state, so date it.
            "prune_after": "2099-06-01",
        },
    )


def _fellowship(fid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.FELLOWSHIP,
        source="illinois",
        external_id=fid,
        source_url=f"https://example.edu/fellowships/{fid}",
        metadata={
            "title": title,
            "award_class": "fellowship",
            "description": "Supports early-stage graph researchers.",
            "facets": {"field": ["Computer Science"], "stage": ["phd"]},
        },
    )


def _score(item, *, rank=1, match=85, **target):
    return RelevanceScore.objects.create(
        content=item,
        score=1.0 / rank,
        signals={
            "area": item.type,
            "run_at": "2026-07-05T00:00:00+00:00",
            "rank": rank,
            "suggested": True,
            "headline": f"Headline {rank}",
            "reason": f"Reason {rank}",
            "match_percent": match,
            "source": "llm",
        },
        **target,
    )


@pytest.mark.django_db
def test_ignore_requires_auth(client: APIClient):
    assert client.post("/api/opportunities/ignore/", {}).status_code in (401, 403)
    assert client.get("/api/opportunities/ignored/").status_code in (401, 403)


@pytest.mark.django_db
def test_ignore_creates_row_and_is_idempotent(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    paper = _paper("p1", "Graph Learning Advances")
    _score(paper, target_user=user)

    first = client.post(
        "/api/opportunities/ignore/", {"content_id": str(paper.id)}, format="json"
    )
    assert first.status_code == 201
    assert first.data == {"content_id": str(paper.id), "ignored": True}
    row = IgnoredItem.objects.get(user=user, content=paper)
    assert row.area == "paper"

    # A repeat call is a no-op, not a duplicate row and not a second event.
    again = client.post(
        "/api/opportunities/ignore/", {"content_id": str(paper.id)}, format="json"
    )
    assert again.status_code == 200
    assert IgnoredItem.objects.filter(user=user, content=paper).count() == 1
    assert (
        RelevanceEvent.objects.filter(
            user=user, content=paper, action=RelevanceEvent.Action.DISMISS
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_ignore_rejects_missing_and_unknown_items(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    assert (
        client.post("/api/opportunities/ignore/", {}, format="json").status_code == 400
    )
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        client.post(
            "/api/opportunities/ignore/", {"content_id": missing}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_unignore_restores_the_item(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    paper = _paper("p1", "Graph Learning Advances")
    _score(paper, target_user=user)
    client.post(
        "/api/opportunities/ignore/", {"content_id": str(paper.id)}, format="json"
    )
    assert client.get("/api/daily-report/").data["suggestions"] == []

    resp = client.delete(f"/api/opportunities/ignore/{paper.id}/")
    assert resp.status_code == 204
    assert not IgnoredItem.objects.filter(user=user).exists()
    titles = [s["title"] for s in client.get("/api/daily-report/").data["suggestions"]]
    assert titles == ["Graph Learning Advances"]

    # Nothing left to un-ignore.
    assert client.delete(f"/api/opportunities/ignore/{paper.id}/").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("make", "path", "key"),
    [
        (lambda: _grant("g1", "Ignored Grant"), "/api/opportunities/grants/", "items"),
        (
            lambda: _conference("c1", "Ignored Conference"),
            "/api/opportunities/conferences/",
            "items",
        ),
        (
            lambda: _fellowship("f1", "Ignored Fellowship"),
            "/api/opportunities/fellowships/",
            "items",
        ),
    ],
)
def test_ignored_items_leave_every_opportunity_feed(client, make, path, key):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    item = make()
    _score(item, target_user=user)
    assert len(client.get(path).data[key]) == 1

    client.post(
        "/api/opportunities/ignore/", {"content_id": str(item.id)}, format="json"
    )
    assert client.get(path).data[key] == []


@pytest.mark.django_db
def test_ignore_follows_the_reader_into_a_lab_feed(client: APIClient):
    """An ignore is a fact about the reader, so it hides on shared feeds too —
    and only for the reader who set it."""
    reader = User.objects.create_user("reader", password="x")
    colleague = User.objects.create_user("colleague", password="x")
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    for user, role in ((reader, LabMembership.Role.MEMBER), (colleague, "owner")):
        LabMembership.objects.create(lab=lab, user=user, role=role)
    grant = _grant("g1", "Shared Grant")
    _score(grant, target_lab=lab)

    client.force_authenticate(reader)
    client.post(
        "/api/opportunities/ignore/", {"content_id": str(grant.id)}, format="json"
    )
    reader_feed = client.get(f"/api/labs/{lab.slug}/recommendations/").data
    assert reader_feed["grants"] == []
    assert reader_feed["counts"]["grants"] == 0

    client.force_authenticate(colleague)
    colleague_feed = client.get(f"/api/labs/{lab.slug}/recommendations/").data
    assert [g["title"] for g in colleague_feed["grants"]] == ["Shared Grant"]
    assert colleague_feed["counts"]["grants"] == 1


@pytest.mark.django_db
def test_ignoring_drops_a_personal_save_but_not_a_lab_save(client: APIClient):
    user = User.objects.create_user("u", password="x")
    lab = Lab.objects.create(name="Graph Lab", slug="graph-lab")
    LabMembership.objects.create(lab=lab, user=user, role=LabMembership.Role.OWNER)
    client.force_authenticate(user)
    grant = _grant("g1", "Contested Grant")
    _score(grant, target_user=user)
    client.post(
        "/api/opportunities/save/", {"content_id": str(grant.id)}, format="json"
    )
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": lab.slug},
        format="json",
    )

    client.post(
        "/api/opportunities/ignore/", {"content_id": str(grant.id)}, format="json"
    )
    assert not SavedOpportunity.objects.filter(
        user=user, target_lab__isnull=True, content=grant
    ).exists()
    assert SavedOpportunity.objects.filter(target_lab=lab, content=grant).exists()


@pytest.mark.django_db
def test_saving_clears_an_ignore(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    paper = _paper("p1", "Reconsidered Paper")
    _score(paper, target_user=user)
    client.post(
        "/api/opportunities/ignore/", {"content_id": str(paper.id)}, format="json"
    )
    client.post(
        "/api/opportunities/save/", {"content_id": str(paper.id)}, format="json"
    )

    assert not IgnoredItem.objects.filter(user=user, content=paper).exists()
    titles = [s["title"] for s in client.get("/api/daily-report/").data["suggestions"]]
    assert titles == ["Reconsidered Paper"]


@pytest.mark.django_db
def test_ignored_view_carries_feed_parity_cards(client: APIClient):
    user = User.objects.create_user("u", password="x")
    client.force_authenticate(user)
    paper = _paper("p1", "Ignored Paper")
    grant = _grant("g1", "Ignored Grant")
    for item in (paper, grant):
        _score(item, target_user=user)
        client.post(
            "/api/opportunities/ignore/", {"content_id": str(item.id)}, format="json"
        )

    items = client.get("/api/opportunities/ignored/").data["items"]
    by_area = {i["area"]: i for i in items}
    assert set(by_area) == {"paper", "grant"}
    assert by_area["paper"]["card"]["title"] == "Ignored Paper"
    assert by_area["paper"]["card"]["venue"] == "NeurIPS"
    assert by_area["grant"]["card"]["sponsor"] == "NSF"
    assert by_area["grant"]["ignored_at"]


@pytest.mark.django_db
def test_one_reader_cannot_see_or_clear_another_readers_ignores(client: APIClient):
    mine = User.objects.create_user("mine", password="x")
    theirs = User.objects.create_user("theirs", password="x")
    paper = _paper("p1", "Shared Paper")
    _score(paper, target_user=mine)
    _score(paper, target_user=theirs)

    client.force_authenticate(mine)
    client.post(
        "/api/opportunities/ignore/", {"content_id": str(paper.id)}, format="json"
    )

    client.force_authenticate(theirs)
    assert client.get("/api/opportunities/ignored/").data["items"] == []
    assert len(client.get("/api/daily-report/").data["suggestions"]) == 1
    # Deleting is scoped to the caller, so this must not clear anyone else's row.
    assert client.delete(f"/api/opportunities/ignore/{paper.id}/").status_code == 404
    assert IgnoredItem.objects.filter(user=mine, content=paper).exists()


@pytest.mark.django_db
def test_a_personal_briefing_leaves_out_what_the_reader_ignored():
    """The report is where "no longer surfaced" is most easily broken: an item
    dismissed today must not be written up and re-delivered tomorrow morning."""
    from apps.accounts.models import WatchPreference
    from apps.content.briefing import generate_briefing_for_user

    user = User.objects.create_user("u", password="x")
    WatchPreference.objects.create(user=user, categories=["papers"])
    kept = _paper("p1", "Kept Paper")
    dropped = _paper("p2", "Dropped Paper")
    today = timezone.now().date().isoformat()
    for rank, item in enumerate((kept, dropped), start=1):
        RelevanceScore.objects.create(
            content=item,
            target_user=user,
            score=1.0 / rank,
            signals={
                "suggested": True,
                "run_at": "2026-07-05T00:00:00+00:00",
                "rank": rank,
                "match_percent": 90,
                "headline": f"Headline {rank}",
                "reason": f"Reason {rank}",
                "top_rank": rank,
                "entered_top_on": today,
                "is_new_top": True,
            },
        )
    IgnoredItem.objects.create(user=user, content=dropped, area="paper")

    briefing = generate_briefing_for_user(user, complete=lambda system, prompt: "")
    titles = [i["title"] for i in briefing.showcase.get("papers", [])]
    assert titles == ["Kept Paper"]
    assert briefing.counts["papers"] == 1
    assert "Dropped Paper" not in briefing.body

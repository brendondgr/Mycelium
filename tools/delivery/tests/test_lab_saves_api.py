"""Lab-scoped saves: the save-to-lab dropdown + the lab Saves area.

A lab save belongs to the lab (unique per ``(target_lab, content)``); only a lab
manager (owner/admin) may create or remove one, while any lab member may read the
lab's shared saves. Feeds expose ``saved_labs`` so the dropdown knows where an item
is already saved. Runs on SQLite — no pgvector needed (direct row reads).
"""

import pytest
from apps.accounts.models import Lab, LabMembership
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from tools.delivery.models import SavedOpportunity
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _lab(slug="lab", name="Lab") -> Lab:
    return Lab.objects.create(name=name, slug=slug)


def _member(lab, username, *, role=LabMembership.Role.MEMBER) -> User:
    user = User.objects.create_user(username, password="x")
    LabMembership.objects.create(user=user, lab=lab, role=role)
    return user


def _grant(gid, title):
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="legacy",
        external_id=gid,
        source_url=f"https://example.org/funding_opps/{gid}",
        metadata={
            "title": title,
            "sponsor": "NSF",
            "amount": "$100,000",
            "website": "https://nsf.gov/x",
            "deadline_date": "2026-12-01",
            "next_kind": "application",
            "matched_topics": title,
        },
    )


def _score(target, item, *, lab=None, rank=1, match=85):
    kwargs = {"target_lab": lab} if lab is not None else {"target_user": target}
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
            "verdict": "read" if match >= 75 else "skim",
            "source": "llm",
        },
        **kwargs,
    )


@pytest.mark.django_db
def test_manager_can_save_to_lab(client: APIClient):
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    client.force_authenticate(owner)
    grant = _grant("g1", "Lab Grant")

    resp = client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )
    assert resp.status_code == 201
    save = SavedOpportunity.objects.get(target_lab=lab, content=grant)
    assert save.user == owner  # actor recorded
    assert save.title == "Lab Grant"
    # No personal save was created for the owner.
    assert not SavedOpportunity.objects.filter(
        user=owner, target_lab__isnull=True, content=grant
    ).exists()


@pytest.mark.django_db
def test_member_cannot_save_to_lab(client: APIClient):
    lab = _lab()
    member = _member(lab, "member", role=LabMembership.Role.MEMBER)
    client.force_authenticate(member)
    grant = _grant("g1", "Lab Grant")

    resp = client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )
    assert resp.status_code == 403
    assert not SavedOpportunity.objects.filter(target_lab=lab).exists()


@pytest.mark.django_db
def test_personal_and_lab_save_coexist(client: APIClient):
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    client.force_authenticate(owner)
    grant = _grant("g1", "Both Grant")

    client.post(
        "/api/opportunities/save/", {"content_id": str(grant.id)}, format="json"
    )
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )
    assert SavedOpportunity.objects.filter(content=grant).count() == 2
    assert SavedOpportunity.objects.filter(
        content=grant, target_lab__isnull=True
    ).exists()
    assert SavedOpportunity.objects.filter(content=grant, target_lab=lab).exists()


@pytest.mark.django_db
def test_lab_save_is_idempotent_across_managers(client: APIClient):
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    admin = _member(lab, "admin", role=LabMembership.Role.ADMIN)
    grant = _grant("g1", "Shared Grant")

    client.force_authenticate(owner)
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )
    client.force_authenticate(admin)
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )
    # Still one lab save; the actor follows the latest saver.
    save = SavedOpportunity.objects.get(target_lab=lab, content=grant)
    assert save.user == admin


@pytest.mark.django_db
def test_manager_can_unsave_lab_save(client: APIClient):
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    client.force_authenticate(owner)
    grant = _grant("g1", "Lab Grant")
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )

    resp = client.delete(f"/api/opportunities/save/{grant.id}/?lab=lab")
    assert resp.status_code == 204
    assert not SavedOpportunity.objects.filter(target_lab=lab).exists()


@pytest.mark.django_db
def test_member_cannot_unsave_lab_save(client: APIClient):
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    member = _member(lab, "member", role=LabMembership.Role.MEMBER)
    grant = _grant("g1", "Lab Grant")
    client.force_authenticate(owner)
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )

    client.force_authenticate(member)
    resp = client.delete(f"/api/opportunities/save/{grant.id}/?lab=lab")
    assert resp.status_code == 403
    assert SavedOpportunity.objects.filter(target_lab=lab).exists()


@pytest.mark.django_db
def test_lab_saves_list_visible_to_members(client: APIClient):
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    member = _member(lab, "member", role=LabMembership.Role.MEMBER)
    grant = _grant("g1", "Lab Grant")
    _score(lab, grant, lab=lab)  # lab-scored → feed-parity card
    client.force_authenticate(owner)
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )

    # A plain member can read the shared list but is not a manager.
    client.force_authenticate(member)
    body = client.get("/api/labs/lab/saves/").data
    assert body["can_manage"] is False
    assert len(body["items"]) == 1
    assert body["items"][0]["card"]["sponsor"] == "NSF"

    # The owner sees can_manage true.
    client.force_authenticate(owner)
    assert client.get("/api/labs/lab/saves/").data["can_manage"] is True


@pytest.mark.django_db
def test_lab_save_of_unscored_live_grant_renders_full_card(client: APIClient):
    """Saving a still-active grant to a lab must show the real card, not the
    "Original listing has closed" fallback.

    A grant saved to a lab is usually not lab-scored (the daily match may never
    have surfaced it for the lab), so there is no ``target_lab`` RelevanceScore.
    The card must still be built from the live item — a null card is reserved for
    a pruned listing (``content`` SET_NULL), which is what the UI reads as closed.
    """
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    client.force_authenticate(owner)
    grant = _grant("g1", "Active Lab Grant")  # live item, no lab score
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )

    body = client.get("/api/labs/lab/saves/").data
    assert len(body["items"]) == 1
    card = body["items"][0]["card"]
    assert card is not None  # not the pruned "listing closed" fallback
    assert card["title"] == "Active Lab Grant"
    assert card["sponsor"] == "NSF"
    assert card["verdict"] is None  # unscored for the lab, but still shown


@pytest.mark.django_db
def test_pruned_lab_save_still_renders_null_card(client: APIClient):
    """When the source item is pruned (``content`` SET_NULL) the card is null so
    the client falls back to the save snapshot ("listing closed")."""
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    client.force_authenticate(owner)
    grant = _grant("g1", "Doomed Grant")
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )
    grant.delete()  # prune → SavedOpportunity.content SET_NULL, snapshot survives

    body = client.get("/api/labs/lab/saves/").data
    assert len(body["items"]) == 1
    assert body["items"][0]["card"] is None
    assert body["items"][0]["title"] == "Doomed Grant"  # snapshot fallback


@pytest.mark.django_db
def test_lab_saves_list_denies_non_members(client: APIClient):
    lab = _lab()
    _member(lab, "owner", role=LabMembership.Role.OWNER)
    outsider = User.objects.create_user("outsider", password="x")
    client.force_authenticate(outsider)
    assert client.get("/api/labs/lab/saves/").status_code == 403


@pytest.mark.django_db
def test_feed_reports_saved_labs(client: APIClient):
    lab = _lab()
    owner = _member(lab, "owner", role=LabMembership.Role.OWNER)
    client.force_authenticate(owner)
    grant = _grant("g1", "Grant")
    _score(owner, grant)  # personal score → shows on the owner's grants feed
    client.post(
        "/api/opportunities/save/",
        {"content_id": str(grant.id), "lab_slug": "lab"},
        format="json",
    )

    items = client.get("/api/opportunities/grants/").data["items"]
    assert items[0]["saved"] is False  # not personally saved
    assert items[0]["saved_labs"] == ["lab"]  # saved to the managed lab

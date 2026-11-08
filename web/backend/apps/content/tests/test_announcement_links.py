"""Search links into existing threads (plan D15, Phase 5).

Announced items, and only those, link to their thread — in the server the search
ran in; another server, a DM, or a server without announcements shows none. An
updated thread keeps its link; a thread deleted by hand loses it without an error.
A manager can announce an unannounced result once. The web card carries the same
links for the reader's own labs.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from tools.retrieval.models import (
    Announcement,
    AnnouncementPost,
    AnnouncementSettings,
    ContentItem,
    RelevanceScore,
)

from apps.accounts.models import Lab, LabMembership
from apps.content import (
    announce,
    announce_updates,
    announcement_links,
    discord_announcements,
    discord_commands,
)
from apps.integrations.models import DiscordIdentity
from apps.integrations.testing import add_route, bind

TODAY = timezone.localdate()


def _world(*, guilds=("g1",)):
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    row = AnnouncementSettings.objects.create(
        target_lab=lab, enabled=True, seeded_at=timezone.now()
    )
    for guild in guilds:
        add_route(bind(lab=lab, guild_id=guild), "grants", f"forum-{guild}")
    member = User.objects.create_user("ana")
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.OWNER)
    DiscordIdentity.objects.create(
        user=member,
        discord_user_id="101",
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        dm_ok=True,
    )
    return announce.Target("lab", lab, row), member


def _grant(title, days=60):
    iso = (TODAY + timedelta(days=days)).isoformat()
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="open-collector",
        external_id=title,
        metadata={
            "title": title,
            "status": "open",
            "deadline_date": iso,
            "prune_after": iso,
        },
    )


def _announced(target, item):
    RelevanceScore.objects.create(
        content=item,
        target_lab=target.obj,
        score=0.9,
        signals={
            "suggested": True,
            "cluster_slates": {
                "c1": {
                    "label": "Ocean",
                    "rank": 1,
                    "of": 10,
                    "entered_on": TODAY.isoformat(),
                    "is_new": True,
                }
            },
        },
    )
    target.settings.refresh_from_db()
    announce.run_target(
        target, TODAY, dry_run=False, complete=None, poster=discord_announcements.post
    )
    return Announcement.objects.get(content=item)


def _search(items, guild_id):
    context = SimpleNamespace(
        items=items,
        saved_ids=set(),
        result=SimpleNamespace(count=len(items), confidence="high"),
    )
    with mock.patch(
        "apps.content.search_service.search_for_user", return_value=context
    ):
        return discord_commands.search("101", "ocean", guild_id)


@pytest.mark.django_db
def test_only_announced_items_link_and_only_in_the_announcing_server(fake) -> None:
    target, _ = _world(guilds=("g1",))
    announced, other = _grant("Announced"), _grant("Not announced")
    ann = _announced(target, announced)
    thread = ann.posts.get().thread_id

    status, payload = _search([announced, other], "g1")
    rows = {r["title"]: r for r in payload["results"]}
    assert status == "ok"
    assert (
        rows["Announced"]["thread_url"] == f"https://discord.com/channels/g1/{thread}"
    )
    assert rows["Not announced"]["thread_url"] == ""

    _status, elsewhere = _search([announced], "g-other")
    assert elsewhere["results"][0]["thread_url"] == ""
    _status, dm = _search([announced], "")
    assert dm["results"][0]["thread_url"] == "" and dm["results"][0]["announce"] == []


@pytest.mark.django_db
def test_an_updated_thread_keeps_the_same_link(fake) -> None:
    target, _ = _world()
    item = _grant("Moving", days=40)
    ann = _announced(target, item)
    before = _search([item], "g1")[1]["results"][0]["thread_url"]
    moved = (TODAY + timedelta(days=80)).isoformat()
    item.metadata = {**item.metadata, "deadline_date": moved, "prune_after": moved}
    item.save()
    discord_announcements.apply_updates(announce_updates.plan(target, TODAY), TODAY)

    after = _search([item], "g1")[1]["results"][0]["thread_url"]

    assert after == before and ann.posts.get().update_log


@pytest.mark.django_db
def test_a_thread_deleted_by_hand_loses_its_link_without_an_error(fake) -> None:
    target, _ = _world()
    item = _grant("Deleted")
    ann = _announced(target, item)
    discord_announcements.mark_thread_deleted(ann.posts.get().thread_id)

    status, payload = _search([item], "g1")

    assert status == "ok" and payload["results"][0]["thread_url"] == ""


@pytest.mark.django_db
def test_a_send_that_finds_the_thread_gone_marks_it_deleted(fake, monkeypatch) -> None:
    from apps.integrations.services import discord_api
    from apps.integrations.services.discord_api import RawResponse

    target, _ = _world()
    item = _grant("Gone", days=40)
    ann = _announced(target, item)
    post = ann.posts.get()

    def gone(method, path, **kw):
        if path.startswith(f"/channels/{post.thread_id}"):
            return RawResponse(404, {"code": 10003, "message": "Unknown Channel"})
        return fake(method, path, **kw)

    monkeypatch.setattr(discord_api, "_request", gone)
    moved = (TODAY + timedelta(days=80)).isoformat()
    item.metadata = {**item.metadata, "deadline_date": moved, "prune_after": moved}
    item.save()
    discord_announcements.apply_updates(announce_updates.plan(target, TODAY), TODAY)

    post.refresh_from_db()
    assert post.deleted_at is not None


@pytest.mark.django_db
def test_a_manager_can_announce_a_result_once(fake, settings) -> None:
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    target, _ = _world()
    item = _grant("By hand")

    _status, payload = _search([item], "g1")
    options = payload["results"][0]["announce"]
    assert [o["purpose"] for o in options] == ["grants"]

    status, posted = announcement_links.manual_announce(
        "101", "g1", options[0]["binding_id"], str(item.id)
    )
    assert status == "ok", posted
    ann = Announcement.objects.get(content=item)
    assert ann.origin == Announcement.Origin.MANUAL and ann.posts.count() == 1

    _status, again = _search([item], "g1")
    assert again["results"][0]["announce"] == []
    assert again["results"][0]["thread_url"] == posted["thread_url"]
    status, _ = announcement_links.manual_announce(
        "101", "g1", options[0]["binding_id"], str(item.id)
    )
    assert status == "exists" and AnnouncementPost.objects.count() == 1


@pytest.mark.django_db
def test_a_member_who_is_not_a_manager_gets_no_announce_option(fake) -> None:
    target, manager = _world()
    LabMembership.objects.filter(user=manager).update(role=LabMembership.Role.MEMBER)

    _status, payload = _search([_grant("Plain")], "g1")

    assert payload["results"][0]["announce"] == []


@pytest.mark.django_db
def test_the_web_search_card_carries_the_same_links(fake) -> None:
    target, member = _world(guilds=("g1", "g2"))
    item = _grant("Web")
    _announced(target, item)
    stranger = User.objects.create_user("stranger")

    mine = announcement_links.discussed_for_user(member, [item.id])[str(item.id)]
    assert [link["guild_id"] for link in mine] == ["g1", "g2"]
    assert announcement_links.discussed_for_user(stranger, [item.id]) == {}

    from apps.content.serializers import SearchResultSerializer

    data = SearchResultSerializer(
        [item], many=True, context={"discord_links": {str(item.id): mine}}
    ).data[0]
    assert data["discord_thread_url"] == mine[0]["thread_url"]


@pytest.mark.django_db
def test_the_nightly_check_catches_a_deletion_the_gateway_missed(
    fake, monkeypatch
) -> None:
    from apps.integrations.services import discord_api
    from apps.integrations.services.discord_api import RawResponse

    target, _ = _world()
    item = _grant("Missed")
    ann = _announced(target, item)
    thread = ann.posts.get().thread_id

    def lookup(method, path, **kw):
        if method == "GET" and path == f"/channels/{thread}":
            return RawResponse(404, {"code": 10003})
        return fake(method, path, **kw)

    monkeypatch.setattr(discord_api, "_request", lookup)

    assert discord_announcements.verify_threads(target) == 1
    assert _search([item], "g1")[1]["results"][0]["thread_url"] == ""


@pytest.mark.django_db
def test_a_deleted_thread_can_be_announced_again(fake, settings) -> None:
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    target, _ = _world()
    item = _grant("Again")
    ann = _announced(target, item)
    post = ann.posts.get()
    old_thread = post.thread_id
    discord_announcements.mark_thread_deleted(old_thread)

    status, payload = announcement_links.manual_announce(
        "101", "g1", post.binding_id, str(item.id)
    )

    post.refresh_from_db()
    assert status == "ok", payload
    assert post.thread_id and post.thread_id != old_thread and post.deleted_at is None

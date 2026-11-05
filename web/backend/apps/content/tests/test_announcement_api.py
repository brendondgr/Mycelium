"""The announcements API the web reads (plan Phase 6).

Members read; managers write. The list carries Discord links (server, channel
name, thread URL) for the logo links, what was held back with its reason, and the
closing-soon list. Switching on for the first time queues the activation seed.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership
from apps.content import announce, discord_announcements
from apps.content.models import AnnouncementSettings, ContentItem, RelevanceScore
from apps.integrations.testing import add_route, bind

TODAY = timezone.localdate()


@pytest.fixture
def world(db, fake):
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    binding = bind(lab=lab, guild_id="g1", guild_name="Reef Server")
    add_route(binding, "grants", "forum-g1", channel_name="grants")
    owner = User.objects.create_user("owner")
    member = User.objects.create_user("member")
    LabMembership.objects.create(user=owner, lab=lab, role=LabMembership.Role.OWNER)
    LabMembership.objects.create(user=member, lab=lab, role=LabMembership.Role.MEMBER)
    return lab, binding, owner, member


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _grant(title, days):
    iso = (TODAY + timedelta(days=days)).isoformat()
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="open-collector",
        external_id=title,
        source_url="https://example.org/" + title,
        metadata={
            "title": title,
            "status": "open",
            "funder": "NSF",
            "deadline_date": iso,
            "prune_after": iso,
        },
    )


def _post_some(lab):
    row = AnnouncementSettings.objects.create(
        target_lab=lab, enabled=True, seeded_at=timezone.now()
    )
    for rank, (title, days) in enumerate((("Open call", 60), ("Too soon", 5)), 1):
        RelevanceScore.objects.create(
            content=_grant(title, days),
            target_lab=lab,
            score=1 / rank,
            signals={
                "suggested": True,
                "cluster_slates": {
                    "c1": {
                        "label": "Ocean",
                        "rank": rank,
                        "of": 10,
                        "entered_on": TODAY.isoformat(),
                        "is_new": True,
                    }
                },
            },
        )
    announce.run_target(
        announce.Target("lab", lab, row),
        TODAY,
        dry_run=False,
        complete=None,
        poster=discord_announcements.post,
    )


@pytest.mark.django_db
def test_members_read_the_list_with_discord_links_held_back_and_closing_soon(world):
    lab, _binding, _owner, member = world
    _post_some(lab)

    resp = _client(member).get(f"/api/announcements/?lab={lab.slug}")

    assert resp.status_code == 200
    data = resp.data
    assert data["can_manage"] is False
    (row,) = data["announced"]
    assert row["title"] == "Open call"
    link = row["discord"][0]
    assert link["channel_name"] == "grants" and link["guild_name"] == "Reef Server"
    assert link["thread_url"].startswith("https://discord.com/channels/g1/")
    assert [h["title"] for h in data["held"]] == ["Too soon"]
    assert "buffer" in data["held"][0]["reason"]
    assert [c["title"] for c in data["closing_soon"]] == ["Too soon"]
    assert (
        data["servers"][0]["announcement_routes"]["grants"]["channel_name"] == "grants"
    )


@pytest.mark.django_db
def test_outsiders_cannot_read_and_members_cannot_write(world):
    lab, _binding, _owner, member = world
    outsider = User.objects.create_user("outsider")

    assert (
        _client(outsider).get(f"/api/announcements/?lab={lab.slug}").status_code == 403
    )
    put = _client(member).put(
        f"/api/announcements/settings/?lab={lab.slug}", {"enabled": True}, format="json"
    )
    assert put.status_code == 403
    assert _client(member).get("/api/announcements/").status_code == 400


@pytest.mark.django_db
def test_managers_write_settings_and_bad_values_are_refused(world):
    lab, _binding, owner, _member = world
    client = _client(owner)
    url = f"/api/announcements/settings/?lab={lab.slug}"

    bad = client.put(url, {"daily_cap": -5, "default_nudge": "4w"}, format="json")
    assert bad.status_code == 400 and set(bad.data) == {"daily_cap", "default_nudge"}

    ok = client.put(
        url,
        {
            "daily_cap": 3,
            "default_nudge": "1w",
            "strong_match_tagging": True,
            "min_award": "50000",
        },
        format="json",
    )
    assert ok.status_code == 200, ok.data
    row = AnnouncementSettings.objects.get(target_lab=lab)
    assert (row.daily_cap, row.default_nudge, row.strong_match_tagging) == (
        3,
        "1w",
        True,
    )
    assert float(row.min_award) == 50000.0


@pytest.mark.django_db
def test_switching_on_the_first_time_queues_the_seed(world, settings):
    settings.OPPORTUNITY_ANNOUNCEMENTS_ENABLED = True
    lab, _binding, owner, _member = world
    url = f"/api/announcements/settings/?lab={lab.slug}"

    with mock.patch("apps.content.tasks.activate_announcements.delay") as delay:
        first = _client(owner).put(url, {"enabled": True}, format="json")
        again = _client(owner).put(url, {"enabled": True}, format="json")

    assert first.data["activating"] is True and again.data["activating"] is False
    delay.assert_called_once_with("lab", str(lab.pk))
    assert AnnouncementSettings.objects.get(target_lab=lab).activated_at is not None


@pytest.mark.django_db
def test_a_test_post_goes_to_each_forum(world, fake):
    lab, _binding, owner, _member = world

    resp = _client(owner).post(f"/api/announcements/test/?lab={lab.slug}")

    assert resp.status_code == 200
    assert resp.data["results"] == [
        {
            "guild_name": "Reef Server",
            "purpose": "grants",
            "channel_id": "forum-g1",
            "channel_name": "grants",
            "ok": True,
        }
    ]
    assert any(b["name"].startswith("[Test]") for b in fake.threads.values())


@pytest.mark.django_db
def test_create_channels_is_for_the_bindings_managers(world, fake):
    lab, binding, owner, member = world
    url = f"/api/announcements/create-channels/?binding={binding.id}"

    assert _client(member).post(url).status_code == 404
    resp = _client(owner).post(url)

    assert resp.status_code == 200, resp.data
    assert set(resp.data["routes"]) == {"grants", "fellowships", "conferences"}


@pytest.mark.django_db
def test_the_lab_report_keeps_papers_and_one_line_per_kind(world, settings):
    from apps.content import briefing

    settings.OPPORTUNITY_ANNOUNCEMENTS_ENABLED = True
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    lab, binding, _owner, _member = world
    _post_some(lab)

    assert announce.announcements_live(lab)
    line = announce.report_line(lab, TODAY)
    assert line.startswith("## Opportunities")
    assert (
        "**1 grant** announced → [#grants](https://discord.com/channels/g1/forum-g1)"
        in line
    )

    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return mock.Mock(body="Report.", save=lambda **_k: None)

    with (
        mock.patch.object(briefing, "_write_briefing", side_effect=capture),
        mock.patch.object(
            briefing, "record_run_stats", side_effect=lambda b: b, create=True
        ),
    ):
        report = briefing.generate_briefing_for_lab(lab, complete=lambda _p: None)

    assert seen["allow"] == ("papers",)
    assert report.body.endswith(line + "\n") and "## Grants" not in report.body


@pytest.mark.django_db
def test_without_announcements_the_report_is_unchanged(world, settings):
    settings.OPPORTUNITY_ANNOUNCEMENTS_ENABLED = True
    lab, *_ = world
    assert not announce.announcements_live(lab)


@pytest.mark.django_db
def test_lab_feed_cards_carry_where_they_were_announced(world):
    lab, _binding, _owner, member = world
    _post_some(lab)

    data = _client(member).get(f"/api/labs/{lab.slug}/recommendations/").data
    cards = {g["title"]: g for g in data["grants"]}

    announced = cards["Open call"]["announcement"]
    assert announced["discord"][0]["channel_name"] == "grants"
    assert cards["Too soon"]["announcement"] is None
    assert cards["Too soon"]["usability"]["verdict"] == "block"


def test_a_carried_forward_body_loses_its_opportunity_sections():
    body = (
        "Intro.\n\n## Papers\n\n[P](u) why\n\n## Grants\n\n[G](u) why\n\n"
        "## Conferences\n\n[C](u) why\n\n## Opportunities\n\nold line\n"
    )
    out = announce.report_body(body, "## Opportunities\n\n**1 grant** announced")
    assert "## Grants" not in out and "## Conferences" not in out
    assert "old line" not in out
    assert out.startswith("Intro.\n\n## Papers") and out.endswith("announced\n")

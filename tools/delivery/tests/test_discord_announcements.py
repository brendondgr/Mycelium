"""Announcements in Discord, against a fake Discord (plan Phase 4).

One thread per live binding that routes the kind; a changed call updates the same
thread in place (renamed, retagged, opening post edited, a reply tagging exactly
the followers) at most once a night; finished calls are archived and tagged; the
closing-soon list replaces yesterday's; nudges fire at the chosen time and follow a
moved date; the buttons go through the gate.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from apps.accounts.models import Lab, LabMembership
from apps.integrations.models import DiscordIdentity, DiscordOutboxMessage
from apps.integrations.testing import add_route, bind
from django.contrib.auth.models import User
from django.utils import timezone

from tools.delivery import (
    announce,
    announce_updates,
    announcement_actions,
    announcement_setup,
    discord_announcements,
)
from tools.delivery.models import (
    Announcement,
    AnnouncementNudge,
    AnnouncementPost,
    AnnouncementReaction,
    AnnouncementSettings,
    ClosingSoonPost,
    ReminderSubscription,
)
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

TODAY = timezone.localdate()


def _setup(*, guilds=("g1",), followers=0):
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    row = AnnouncementSettings.objects.create(
        target_lab=lab, enabled=True, seeded_at=timezone.now()
    )
    bindings = []
    for guild in guilds:
        b = bind(lab=lab, guild_id=guild)
        add_route(
            b,
            "grants",
            f"forum-{guild}",
            forum_tag_ids={
                "New call": "t-new",
                "Newly relevant": "t-rel",
                "Already open": "t-open",
                "Updated": "t-upd",
                "Daily list": "t-daily",
                "Closed": "t-closed",
            },
        )
        bindings.append(b)
    return announce.Target("lab", lab, row), bindings


def _member(lab, username, snowflake, role=LabMembership.Role.MEMBER):
    user = User.objects.create_user(username)
    LabMembership.objects.create(user=user, lab=lab, role=role)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
        dm_ok=True,
    )
    return user


def _grant(deadline: date, title="Ocean Technology"):
    iso = deadline.isoformat()
    return ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="open-collector",
        external_id=f"g-{title}-{iso}",
        source_url="https://example.org/call",
        metadata={
            "title": title,
            "status": "open",
            "funder": "NSF",
            "deadline_date": iso,
            "prune_after": iso,
        },
    )


def _announce(target, item):
    RelevanceScore.objects.create(
        content=item,
        target_lab=target.obj,
        score=0.9,
        signals={
            "suggested": True,
            "cluster_slates": {
                "c1": {
                    "label": "Ocean forecasting",
                    "rank": 1,
                    "of": 10,
                    "entered_on": TODAY.isoformat(),
                    "is_new": True,
                }
            },
        },
    )
    target.settings.refresh_from_db()
    outcome = announce.run_target(
        target,
        TODAY,
        dry_run=False,
        complete=None,
        poster=lambda ann: discord_announcements.post(ann),
    )
    return Announcement.objects.get(content=item), outcome


# --------------------------------------------------------------------------- #
# Posting
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_one_thread_per_binding_with_buttons_and_tags(fake) -> None:
    target, bindings = _setup(guilds=("g1", "g2"))
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=60)))

    posts = list(AnnouncementPost.objects.filter(announcement=ann))
    assert len(posts) == 2 and all(p.thread_id for p in posts)
    thread_posts = [
        b for m, p, b in fake.calls if m == "POST" and p.endswith("/threads")
    ]
    assert {p.split("/")[2] for p in fake.paths("POST") if p.endswith("/threads")} == {
        "forum-g1",
        "forum-g2",
    }
    body = thread_posts[0]
    assert body["name"] == "Ocean Technology"
    assert body["applied_tags"] == ["t-rel"]
    ids = [
        c["custom_id"]
        for c in body["message"]["components"][0]["components"]
        if "custom_id" in c
    ]
    assert ids[0].startswith("ann:") and ids[0].endswith(":interested")
    assert body["message"]["allowed_mentions"] == {"parse": []}
    fields = [f["name"] for f in body["message"]["embeds"][0]["fields"]]
    assert fields[:2] == ["Why it matters", "Can we use this?"]


@pytest.mark.django_db
def test_a_binding_without_the_route_gets_nothing(fake) -> None:
    target, (binding,) = _setup()
    other = bind(lab=target.obj, guild_id="g9")  # bound, but no grants forum
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=60)))

    assert list(ann.posts.values_list("binding_id", flat=True)) == [binding.id]
    assert not AnnouncementPost.objects.filter(binding=other).exists()


@pytest.mark.django_db
def test_strong_match_tagging_is_off_by_default_and_names_only_strong_fits(
    fake,
) -> None:
    target, _ = _setup()
    ana = _member(target.obj, "ana", "111")
    item = _grant(TODAY + timedelta(days=60))
    RelevanceScore.objects.create(
        content=item,
        target_lab=target.obj,
        score=0.9,
        signals={
            "suggested": True,
            "member_fit": [
                {
                    "username": "ana",
                    "reason": "assimilation",
                    "fit": 0.8,
                    "source": "llm",
                }
            ],
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
    announce.run_target(
        target, TODAY, dry_run=False, complete=None, poster=discord_announcements.post
    )
    first = [b for m, p, b in fake.calls if p.endswith("/threads")][0]
    assert "content" not in first["message"]  # off: nobody tagged

    target.settings.strong_match_tagging = True
    target.settings.save()
    ann = Announcement.objects.get(content=item)
    AnnouncementPost.objects.filter(announcement=ann).delete()
    DiscordOutboxMessage.objects.all().delete()
    discord_announcements.post(ann)
    second = [b for m, p, b in fake.calls if p.endswith("/threads")][-1]
    assert second["message"]["content"] == "🎯 Strong match for <@111>"
    assert second["message"]["allowed_mentions"] == {"parse": [], "users": ["111"]}
    assert ana.id  # the tag names exactly Ana


# --------------------------------------------------------------------------- #
# Updates in place
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_changed_call_updates_the_same_thread_and_tags_only_followers(fake) -> None:
    target, _ = _setup()
    item = _grant(TODAY + timedelta(days=40))
    ann, _ = _announce(target, item)
    post = ann.posts.get()
    fan = _member(target.obj, "fan", "222")
    _member(target.obj, "bystander", "333")
    AnnouncementReaction.objects.create(
        announcement=ann, user=fan, kind=AnnouncementReaction.Kind.INTERESTED
    )

    moved = (TODAY + timedelta(days=70)).isoformat()
    item.metadata = {**item.metadata, "deadline_date": moved, "prune_after": moved}
    item.save()
    plan = announce_updates.plan(target, TODAY)
    done = discord_announcements.apply_updates(plan, TODAY)

    assert done["updated"] == 1
    patches = [
        b
        for m, p, b in fake.calls
        if m == "PATCH" and p == f"/channels/{post.thread_id}"
    ]
    assert patches[-1]["archived"] is False
    assert patches[-1]["name"].startswith("[🚨 Update ")
    assert patches[-1]["applied_tags"] == ["t-rel", "t-upd"]
    edit = [
        b
        for m, p, b in fake.calls
        if m == "PATCH" and p == f"/channels/{post.thread_id}/messages/{post.thread_id}"
    ][-1]
    assert edit["embeds"][0]["fields"][0]["name"] == "What changed"
    reply = [
        b
        for m, p, b in fake.calls
        if m == "POST" and p == f"/channels/{post.thread_id}/messages"
    ][-1]
    assert reply["content"].startswith("🚨 **Update ")
    assert reply["content"].endswith("<@222>")
    assert reply["allowed_mentions"] == {"parse": [], "users": ["222"]}
    post.refresh_from_db()
    assert len(post.update_log) == 1
    assert announce_updates.plan(target, TODAY).changed == []  # recorded


@pytest.mark.django_db
def test_a_second_change_the_same_night_waits(fake) -> None:
    target, _ = _setup()
    item = _grant(TODAY + timedelta(days=40))
    _announce(target, item)
    for days in (70, 90):
        moved = (TODAY + timedelta(days=days)).isoformat()
        item.metadata = {**item.metadata, "deadline_date": moved, "prune_after": moved}
        item.save()
        done = discord_announcements.apply_updates(
            announce_updates.plan(target, TODAY), TODAY
        )
    assert done == {"updated": 0, "deferred": 1, "closed": 0, "closing_soon": 0}


@pytest.mark.django_db
def test_a_finished_call_is_tagged_closed_then_archived(fake) -> None:
    target, _ = _setup()
    item = _grant(TODAY + timedelta(days=20))
    ann, _ = _announce(target, item)
    thread = ann.posts.get().thread_id
    later = TODAY + timedelta(days=21)

    discord_announcements.apply_updates(announce_updates.plan(target, later), later)

    patches = [
        b for m, p, b in fake.calls if m == "PATCH" and p == f"/channels/{thread}"
    ]
    assert patches[-2]["applied_tags"] == ["t-rel", "t-closed"]
    assert patches[-1] == {"archived": True}
    ann.refresh_from_db()
    assert ann.state == Announcement.State.CLOSED


@pytest.mark.django_db
def test_the_closing_soon_list_replaces_yesterdays(fake) -> None:
    target, (binding,) = _setup()
    _announce(target, _grant(TODAY + timedelta(days=5), title="Soon"))
    discord_announcements.apply_updates(announce_updates.plan(target, TODAY), TODAY)
    first = ClosingSoonPost.objects.get(on_date=TODAY)
    assert first.thread_id

    tomorrow = TODAY + timedelta(days=1)
    discord_announcements.apply_updates(
        announce_updates.plan(target, tomorrow), tomorrow
    )

    assert f"/channels/{first.thread_id}" in fake.paths("DELETE")
    first.refresh_from_db()
    assert first.replaced_at is not None
    names = [b["name"] for b in fake.threads.values() if b["name"].startswith("⏳")]
    assert len(names) == 2


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_interested_reacts_saves_nudges_and_dms(fake) -> None:
    target, _ = _setup()
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=40)))
    post = ann.posts.get()
    ana = _member(target.obj, "ana", "444")

    status, payload = announcement_actions.interested("444", post.id, "g1")

    assert status == "ok", payload
    assert "DM" in payload["message"] and "tag you in the thread" in payload["message"]
    assert AnnouncementNudge.objects.get(user=ana).offset == "2w"
    assert (
        ana.saved_opportunities.filter(content=ann.content).exists()
        or ann.content.saves.filter(user=ana).exists()
    )
    dm = DiscordOutboxMessage.objects.get(kind="announcement_details")
    assert dm.status == DiscordOutboxMessage.Status.SENT
    ids = [c.get("custom_id") for c in dm.components[0]["components"]]
    assert f"ann:{post.id}:unfollow" in ids
    names = [f["name"] for f in dm.embed["fields"]]
    assert "Your reminder" in names


@pytest.mark.django_db
def test_someone_outside_the_lab_cannot_use_the_buttons(fake) -> None:
    target, _ = _setup()
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=40)))
    stranger = User.objects.create_user("stranger")
    DiscordIdentity.objects.create(
        user=stranger,
        discord_user_id="555",
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
    )
    status, _ = announcement_actions.interested("555", ann.posts.get().id, "g1")
    assert status == "forbidden"
    assert not AnnouncementReaction.objects.exists()


@pytest.mark.django_db
def test_remind_me_offers_only_future_choices_and_sets_them(fake) -> None:
    target, _ = _setup()
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=40)))
    post = ann.posts.get()
    ana = _member(target.obj, "ana", "666")

    status, payload = announcement_actions.remind_options("666", post.id, "g1")
    values = [o["value"] for o in payload["options"]]
    assert status == "ok" and values == ["2d", "1w", "2w", "3w", "1m"]  # 2m is past
    assert [o["value"] for o in payload["options"] if o["default"]] == ["2w"]

    status, payload = announcement_actions.remind_set(
        "666", post.id, ["2d", "1w"], "thread"
    )
    assert status == "ok"
    assert set(
        AnnouncementNudge.objects.filter(user=ana).values_list("offset", flat=True)
    ) == {"2d", "1w"}
    assert ana in discord_announcements.followers(ann)  # counts as Interested
    # Recorded for measurement, without disturbing who follows it.
    remind = AnnouncementReaction.objects.get(
        announcement=ann, kind=AnnouncementReaction.Kind.REMIND
    )
    assert remind.user == ana and remind.reason == "thread:2d,1w"


@pytest.mark.django_db
def test_remind_me_by_dm_is_an_ordinary_reminder(fake) -> None:
    from apps.billing.testing import paid_plan

    target, _ = _setup()
    item = _grant(TODAY + timedelta(days=40))
    from tools.retrieval.deadlines_projection import rebuild_deadlines_for

    rebuild_deadlines_for(item, TODAY.isoformat())
    ann, _ = _announce(target, item)
    ana = _member(target.obj, "ana", "777")
    paid_plan(ana)

    status, payload = announcement_actions.remind_set(
        "777", ann.posts.get().id, ["1w"], "dm"
    )

    assert status == "ok", payload
    sub = ReminderSubscription.objects.get(target_user=ana, content=item)
    assert [(o.amount, o.unit) for o in sub.offsets.all()] == [(1, "week")]


@pytest.mark.django_db
def test_not_for_us_is_for_managers_and_keeps_the_reason(fake) -> None:
    target, _ = _setup()
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=40)))
    post = ann.posts.get()
    _member(target.obj, "member", "888")
    _member(target.obj, "boss", "999", role=LabMembership.Role.OWNER)

    assert (
        announcement_actions.not_for_us("888", post.id, "meh", "g1")[0] == "forbidden"
    )
    status, _ = announcement_actions.not_for_us(
        "999", post.id, "We don't do hardware", "g1"
    )
    assert status == "ok"
    row = AnnouncementReaction.objects.get(kind=AnnouncementReaction.Kind.NOT_FOR_US)
    assert row.reason == "We don't do hardware"


@pytest.mark.django_db
def test_nudges_fire_on_time_follow_a_moved_date_and_never_twice(fake) -> None:
    target, _ = _setup()
    item = _grant(TODAY + timedelta(days=30))
    ann, _ = _announce(target, item)
    ana = _member(target.obj, "ana", "1212")
    announcement_actions.interested("1212", ann.posts.get().id, "g1")

    assert discord_announcements.send_due_nudges(TODAY) == 0  # 30 days out, 2w nudge
    day = TODAY + timedelta(days=16)
    assert discord_announcements.send_due_nudges(day) == 1
    assert discord_announcements.send_due_nudges(day) == 0  # not twice

    moved = (TODAY + timedelta(days=60)).isoformat()
    item.metadata = {**item.metadata, "deadline_date": moved, "prune_after": moved}
    item.save()
    assert discord_announcements.send_due_nudges(day) == 0  # new date: not due yet
    assert discord_announcements.send_due_nudges(TODAY + timedelta(days=46)) == 1
    nudge = AnnouncementNudge.objects.get(user=ana)
    assert len(nudge.fired_for) == 2


@pytest.mark.django_db
def test_unfollow_stops_tags_and_nudges(fake) -> None:
    target, _ = _setup()
    ann, _ = _announce(target, _grant(TODAY + timedelta(days=40)))
    ana = _member(target.obj, "ana", "1313")
    post = ann.posts.get()
    announcement_actions.interested("1313", post.id, "g1")

    announcement_actions.unfollow("1313", post.id)

    assert ana not in discord_announcements.followers(ann)
    assert not AnnouncementNudge.objects.filter(user=ana, active=True).exists()


# --------------------------------------------------------------------------- #
# The /setup step
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_create_them_for_me_makes_three_sorted_tagged_forums(fake) -> None:
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    binding = bind(lab=lab, guild_id="g1")

    ok, message = announcement_setup.create_forums(binding)

    assert ok, message
    forums = [
        b for m, p, b in fake.calls if p == "/guilds/g1/channels" and b["type"] == 15
    ]
    assert [f["name"] for f in forums] == ["grants", "fellowships", "conferences"]
    assert all(f["default_sort_order"] == 0 for f in forums)
    state = announcement_setup.state(binding)
    assert set(state["routes"]) == {"grants", "fellowships", "conferences"}


@pytest.mark.django_db
def test_managers_only_closes_new_posts_but_keeps_replies_open(fake) -> None:
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    binding = bind(lab=lab, guild_id="g1")
    add_route(binding, "grants", "forum-1")

    ok, _ = announcement_setup.set_poster_policy(
        binding, "managers", manager_discord_ids=["42"], bot_user_id="7"
    )

    assert ok
    puts = {p: b for m, p, b in fake.calls if m == "PUT"}
    everyone = puts["/channels/forum-1/permissions/g1"]
    assert everyone["deny"] == str(announcement_setup.SEND_MESSAGES)
    assert everyone["allow"] == str(announcement_setup.SEND_IN_THREADS)
    assert "/channels/forum-1/permissions/42" in puts


@pytest.mark.django_db
def test_switching_on_runs_the_activation_seed_once(fake, settings) -> None:
    settings.BILLING_ENFORCE_ENTITLEMENTS = False
    lab = Lab.objects.create(name="Reef Lab", slug="reef")
    binding = bind(lab=lab, guild_id="g1")
    add_route(binding, "grants", "forum-g1")
    for n in range(8):
        item = _grant(TODAY + timedelta(days=40 + n), title=f"Call {n}")
        RelevanceScore.objects.create(
            content=item,
            target_lab=lab,
            score=1 / (n + 1),
            signals={
                "suggested": True,
                "cluster_slates": {
                    "c1": {
                        "label": "Ocean",
                        "rank": n + 1,
                        "of": 10,
                        "entered_on": TODAY.isoformat(),
                        "is_new": True,
                    }
                },
            },
        )

    _row, first = announcement_setup.switch(binding, on=True)
    result = announcement_setup.activate_now(binding, complete=None)

    assert first and result["posted"] == 6
    assert AnnouncementPost.objects.exclude(thread_id="").count() == 6
    assert announcement_setup.activate_now(binding, complete=None)["posted"] == 0


@pytest.mark.django_db
def test_one_tag_a_night_and_no_instant_tag_for_a_nudge_already_past(fake) -> None:
    target, _ = _setup()
    target.settings.default_nudge = "3w"
    target.settings.save()
    item = _grant(TODAY + timedelta(days=20))  # three weeks before is already past
    ann, _ = _announce(target, item)
    post = ann.posts.get()
    ana = _member(target.obj, "ana", "1414")

    announcement_actions.interested("1414", post.id, "g1")
    assert discord_announcements.send_due_nudges(TODAY) == 0  # 3w was already past

    announcement_actions.remind_set("1414", post.id, ["2d", "1w"], "thread")
    later = TODAY + timedelta(days=19)  # both 1w and 2d are due tonight
    assert discord_announcements.send_due_nudges(later) == 1
    replies = [
        b
        for m, p, b in fake.calls
        if m == "POST" and p == f"/channels/{post.thread_id}/messages"
    ]
    assert len([r for r in replies if "left." in (r.get("content") or "")]) == 1
    assert ana.id


@pytest.mark.django_db
def test_a_day_with_nothing_closing_takes_yesterdays_list_down(fake) -> None:
    target, _ = _setup()
    # Held back from its own thread (inside the buffer), but on the list.
    _announce(target, _grant(TODAY + timedelta(days=10), title="Soon"))
    discord_announcements.apply_updates(announce_updates.plan(target, TODAY), TODAY)
    first = ClosingSoonPost.objects.get()
    assert first.thread_id

    after = TODAY + timedelta(days=11)  # past its deadline: nothing closes now
    discord_announcements.apply_updates(announce_updates.plan(target, after), after)

    assert f"/channels/{first.thread_id}" in fake.paths("DELETE")
    assert ClosingSoonPost.objects.count() == 1


# --------------------------------------------------------------------------- #
# Where a conference is held: full location and the continent tag
# --------------------------------------------------------------------------- #
def _conference(place_text="Ann Arbor, MI", **meta):
    deadline = (TODAY + timedelta(days=60)).isoformat()
    return ContentItem.objects.create(
        type=ContentItem.Type.CONFERENCE,
        source="open-collector",
        external_id=f"c-{place_text}",
        source_url="https://example.org/conf",
        metadata={
            "name": "Ocean Systems Conference",
            "place_text": place_text,
            "prune_after": deadline,
            "deadlines_structured": [
                {
                    "kind": "submission",
                    "instant": f"{deadline}T11:59:59Z",
                    "round_label": "Papers",
                    "is_estimated": False,
                }
            ],
            **meta,
        },
    )


def _conference_setup():
    target, (binding,) = _setup()
    target.settings.conferences = True
    target.settings.save()
    tags = {
        name: f"t-{name}"
        for name, _e in discord_announcements.FORUM_TAGS["conferences"]
    }
    add_route(binding, "conferences", "forum-conf", forum_tag_ids=tags)
    return target, binding


@pytest.mark.django_db
def test_a_conference_post_shows_the_full_location_and_its_continent_tag(fake):
    target, _binding = _conference_setup()
    ann, _ = _announce(target, _conference("Ann Arbor, MI"))

    body = next(
        b
        for m, p, b in fake.calls
        if m == "POST" and p == "/channels/forum-conf/threads"
    )
    assert body["applied_tags"] == ["t-Dates published", "t-North America"]
    description = body["message"]["embeds"][0]["description"]
    assert description.startswith("**Ann Arbor, Michigan, United States** · 🌎 North")
    assert ann.snapshot["continent"] == "North America"


@pytest.mark.django_db
def test_a_conference_with_no_known_place_gets_no_continent_tag(fake):
    target, _binding = _conference_setup()
    _announce(target, _conference("Pittsburgh"))

    body = next(
        b
        for m, p, b in fake.calls
        if m == "POST" and p == "/channels/forum-conf/threads"
    )
    assert body["applied_tags"] == ["t-Dates published"]


def test_the_status_tag_survives_the_five_tag_cap() -> None:
    ann = Announcement(
        category=ContentItem.Type.CONFERENCE,
        target_department_id=1,
        snapshot={"continent": "Europe"},
        alignment={"dept_reasons": [{"label": f"Reason {n}"} for n in range(3)]},
    )
    names = discord_announcements._post_tags(ann, "Closed")
    assert names[:3] == ["Conference", "Closed", "Europe"]

    class _Route:
        forum_tag_ids = {n: f"id-{n}" for n in names}

    assert discord_announcements._tags(_Route, names) == [
        "id-Conference",
        "id-Closed",
        "id-Europe",
        "id-Reason 0",
        "id-Reason 1",
    ]


def test_grants_never_carry_a_continent() -> None:
    ann = Announcement(category=ContentItem.Type.GRANT, snapshot={"continent": "Asia"})
    assert discord_announcements.continent_of(ann) == ""


@pytest.mark.django_db
def test_retagging_adds_the_continent_to_old_threads_without_a_reply(fake):
    target, _binding = _conference_setup()
    ann, _ = _announce(target, _conference("Brescia (Italy)"))
    ann.snapshot = {k: v for k, v in ann.snapshot.items() if k != "continent"}
    ann.save()
    fake.calls.clear()

    assert (
        discord_announcements.retag_conference_threads(dry_run=True)[0]["continent"]
        == "Europe"
    )
    assert fake.calls == []  # a dry run touches nothing

    rows = discord_announcements.retag_conference_threads()
    post = ann.posts.get()
    patches = [
        b
        for m, p, b in fake.calls
        if m == "PATCH" and p == f"/channels/{post.thread_id}"
    ]
    assert rows and patches == [{"applied_tags": ["t-Dates published", "t-Europe"]}]
    assert not [p for m, p, _b in fake.calls if m == "POST"]  # no reply, no thread
    ann.refresh_from_db()
    assert ann.snapshot["continent"] == "Europe"

    # Re-running queues nothing new for a thread already done.
    fake.calls.clear()
    discord_announcements.retag_conference_threads()
    assert not [p for m, p, _b in fake.calls if m == "PATCH"]

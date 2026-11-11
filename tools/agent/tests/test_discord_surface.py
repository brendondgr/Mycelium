"""Plan D, phase D2: places, links, anchors and the Discord adapter.

No Discord: the adapter is called with the ids a gateway event would carry,
turns run with the scripted model, and the bot's part is phase D3.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from apps.integrations.models import DiscordIdentity
from apps.integrations.services import resolve
from apps.integrations.testing import add_route, bind
from apps.integrations.tests.base import (
    clear_discord_cache,
    discord_test_settings,
    grant_bot_server,
)
from django.utils import timezone

from tools.agent import loop, service
from tools.agent.models import AgentOrgPolicy, AgentThread, AgentThreadLink
from tools.agent.surfaces import discord as surface

pytestmark = pytest.mark.django_db

GUILD = "900"
_n = iter(range(5000, 9000))


@pytest.fixture(autouse=True)
def _discord():
    with discord_test_settings:
        clear_discord_cache()
        yield
        clear_discord_cache()


def link(user, snowflake):
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        state=DiscordIdentity.State.ACTIVE,
        link_method=DiscordIdentity.LinkMethod.OAUTH,
    )
    return snowflake


@pytest.fixture
def server(world):
    grant_bot_server(world.lab)
    world.binding = bind(lab=world.lab, guild_id=GUILD, guild_name="Imaging HQ")
    add_route(world.binding, "grants", "forum-1")
    world.member_id = link(world.member, "100")
    world.admin_id = link(world.admin, "101")
    world.lab_project.share_in_lab_reports = True
    world.lab_project.save(update_fields=["share_in_lab_reports"])
    return world


def announcement(world, thread_id="th-1"):
    from tools.delivery.models import Announcement, AnnouncementPost

    ann = Announcement.objects.create(
        target_lab=world.lab,
        category="grant",
        state=Announcement.State.POSTED,
        snapshot={"title": "Ocean Imaging Call", "funder": "NSF"},
        write_up={"why_it_matters": "It funds exactly your segmentation work."},
        facts={"deadline": "2027-01-15"},
    )
    AnnouncementPost.objects.create(
        announcement=ann,
        binding=world.binding,
        channel_id="forum-1",
        thread_id=thread_id,
        thread_name="Ocean Imaging Call",
        posted_at=timezone.now(),
    )
    return ann


def ask(
    snowflake,
    *,
    name="Visitor",
    guild=GUILD,
    channel="chan-1",
    thread="",
    parent="",
    text="What is this about?",
):
    return surface.ask(
        discord_user_id=snowflake,
        name=name,
        guild_id=guild,
        channel_id=thread or channel,
        thread_id=thread,
        parent_id=parent or (channel if thread else ""),
        message_id=str(next(_n)),
        text=text,
        start=lambda t: None,
    )


# --------------------------------------------------------------------------- #
# Places
# --------------------------------------------------------------------------- #


def test_each_place_resolves_as_the_plan_says(server):
    from tools.delivery.models import ClosingSoonPost

    ann = announcement(server)
    ClosingSoonPost.objects.create(
        binding=server.binding,
        category="grant",
        on_date=timezone.localdate(),
        outbox_key="k",
        thread_id="th-soon",
    )
    dm = resolve.place_for("", "dm-1")
    assert (dm.kind, dm.binding) == ("dm", None)

    p = resolve.place_for(GUILD, "th-1", "th-1", "forum-1")
    assert p.kind == "announcement" and p.shared and p.binding == server.binding
    assert p.anchor == {"kind": "announcement", "key": str(ann.pk)}

    p = resolve.place_for(GUILD, "th-soon", "th-soon", "forum-1")
    assert p.kind == "closing_soon" and p.shared and p.lab == server.lab

    p = resolve.place_for(GUILD, "th-x", "th-x", "general")
    assert p.kind == "thread" and p.shared and p.lab == server.lab

    p = resolve.place_for(GUILD, "general")
    assert p.kind == "channel" and not p.shared and p.lab == server.lab

    assert resolve.place_for("777", "c").kind == "unbound"


def test_several_bindings_route_or_fall_back_to_public(server):
    grant_bot_server(server.other_lab)
    other = bind(lab=server.other_lab, guild_id=GUILD)
    add_route(other, "updates", "other-news")
    assert resolve.place_for(GUILD, "other-news").lab == server.other_lab
    assert resolve.place_for(GUILD, "forum-1").lab == server.lab
    p = resolve.place_for(GUILD, "general")
    assert p.kind == "ambiguous" and p.binding is None

    h = ask(server.member_id, channel="general")
    thread = AgentThread.objects.get(pk=h.thread_id)
    assert thread.scope_kind == "personal" and thread.shared
    event = thread.events.filter(type="user").last()
    assert event.payload["turn"]["audience_width"] == "instance"


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_a_dm_needs_an_activated_account(server):
    r = ask("555", guild="", channel="dm-555")
    assert not r and r.code == "not_linked" and "Connect Discord" in r.message
    profile = server.viewer.profile
    profile.is_verified = False
    profile.save(update_fields=["is_verified"])
    link(server.viewer, "556")
    r = ask("556", guild="", channel="dm-556")
    assert not r and r.code == "not_verified" and "Connect Discord" in r.message
    assert ask(server.member_id, guild="", channel="dm-100")


def test_every_denial_has_a_sentence(server, settings, monkeypatch):
    assert ask("1", guild="777").message == surface.UNBOUND
    assert ask(server.member_id, text="  ").message == surface.EMPTY

    AgentOrgPolicy.objects.create(lab=server.lab, discord_channels_off=["quiet"])
    r = ask(server.member_id, channel="quiet")
    assert r.code == "channel_off" and "Ask in a DM instead" in r.message

    service.set_preferences(server.member, discord_allowed=False)
    r = ask(server.member_id, channel="general")
    assert r.code == "discord_off"
    service.set_preferences(server.member, discord_allowed=True)

    AgentOrgPolicy.objects.filter(lab=server.lab).update(discord_guests="off")
    r = ask("4242", channel="general")
    assert r.code == "guests_off"
    AgentOrgPolicy.objects.filter(lab=server.lab).update(discord_guests="full")

    settings.AGENT_DISCORD_ACCESS = "linked"
    assert ask("4243", channel="general").code == "not_linked"
    settings.AGENT_DISCORD_ACCESS = "public"

    monkeypatch.setattr(service, "status", lambda: {"model": None})
    assert ask(server.member_id, channel="general").message == surface.NO_MODEL
    monkeypatch.undo()

    settings.DISCORD_COMMAND_RATE_LIMITS = {"chat": (1, 60)}
    assert ask(server.admin_id, channel="general")
    r = ask(server.admin_id, channel="general")
    assert r.code == "rate_limited" and r.message


def test_a_server_without_the_addon_is_refused(world):
    bind(lab=world.lab, guild_id="901")
    link(world.member, "100")
    r = ask("100", guild="901")
    assert r.code == "not_entitled" and "add-on" in r.message


def test_both_guest_limits_hold(server, settings):
    settings.AGENT_DISCORD_GUEST_DAILY_TURNS = 1
    assert ask("4242", channel="general")
    assert ask("4242", channel="general").code == "guest_limit"
    settings.AGENT_DISCORD_GUEST_DAILY_TURNS = 0
    settings.AGENT_DISCORD_PLACE_DAILY_TURNS = 2
    assert ask("4243", channel="general")
    assert ask("4244", channel="general").code == "place_limit"
    assert ask(server.member_id, channel="general")  # members are not counted


# --------------------------------------------------------------------------- #
# Anchors, links and rollover
# --------------------------------------------------------------------------- #


def _system_prompt(handle, scripted):
    model = scripted("It funds segmentation work (#1).")
    loop.run_turn(handle.thread_id, port=model)
    return model.requests[0]["messages"][0]["content"]


def test_a_forum_question_holds_the_announcement_as_number_one(server, scripted):
    announcement(server)
    for who in (server.member_id, "4242"):
        h = ask(who, thread="th-1", parent="forum-1")
        prompt = _system_prompt(h, scripted)
        assert "This conversation is about #1." in prompt
        assert "Ocean Imaging Call" in prompt
        assert "funds exactly your segmentation work" in prompt
    # one shared conversation for the thread
    assert AgentThreadLink.objects.filter(place_id="th-1").count() == 1
    out = surface.result(h)
    assert out["state"] == "answered"
    assert [s["n"] for s in out["sources"]] == [1]


def test_a_public_level_guest_gets_the_card_and_the_corpus_only(server, scripted):
    from tools.agent import permissions

    announcement(server)
    AgentOrgPolicy.objects.create(lab=server.lab, discord_guests="public")
    h = ask("4242", thread="th-1", parent="forum-1")
    prompt = _system_prompt(h, scripted)
    assert "This conversation is about #1." in prompt
    from tools.agent.caller import for_turn

    thread = AgentThread.objects.get(pk=h.thread_id)
    names = {fn.name for fn in permissions.allowed_functions(for_turn(thread))}
    assert names == {
        "corpus_item",
        "corpus_search",
        "find_functions",
        "fulltext_availability",
        "fulltext_read_paper",
        "fulltext_search_paper",
        "load_functions",
        "read_skill",
    }


def test_a_second_question_reuses_the_thread_and_a_quiet_channel_rolls_over(
    server, settings
):
    first = ask(server.member_id, thread="th-9", parent="general")
    second = ask(server.admin_id, thread="th-9", parent="general")
    assert first.thread_id == second.thread_id  # one shared thread

    a = ask(server.member_id, channel="general")
    b = ask(server.admin_id, channel="general")
    assert a.thread_id != b.thread_id  # a channel: one each
    assert ask(server.member_id, channel="general").thread_id == a.thread_id

    settings.AGENT_DISCORD_CHANNEL_SESSION_HOURS = 24
    AgentThread.objects.filter(pk=a.thread_id).update(
        last_activity_at=timezone.now() - timedelta(hours=25)
    )
    rolled = ask(server.member_id, channel="general")
    assert rolled.thread_id != a.thread_id
    assert AgentThreadLink.objects.get(thread_id=a.thread_id).closed_at is not None


def test_a_dm_is_the_persons_own_thread(server):
    h = ask(server.member_id, guild="", channel="dm-100")
    thread = AgentThread.objects.get(pk=h.thread_id)
    assert thread.user == server.member and not thread.shared
    assert thread.scope_kind == "personal"
    assert thread in service.list_threads(server.member)


def test_a_guest_in_a_channel_is_answered_and_stored_as_a_guest(server):
    h = ask("4242", name="<@1> Sam", channel="general")
    assert h and h.guest
    thread = AgentThread.objects.get(pk=h.thread_id)
    speaker = thread.events.get(type="user").payload["speaker"]
    assert speaker == {
        "kind": "guest",
        "user_id": None,
        "discord_user_id": "4242",
        "name": "1 Sam",
    }


def test_forget_blanks_only_the_callers_own_questions(server):
    a = ask(server.member_id, thread="th-9", parent="general", text="mine")
    ask(server.admin_id, thread="th-9", parent="general", text="theirs")
    assert (
        surface.forget(
            discord_user_id=server.member_id, guild_id=GUILD, place_id="th-9"
        )
        == 1
    )
    texts = [
        e.payload["text"]
        for e in AgentThread.objects.get(pk=a.thread_id).events.filter(type="user")
    ]
    assert texts == ["", "theirs"]


# --------------------------------------------------------------------------- #
# Following a turn, recovery, deletion (what the bot calls)
# --------------------------------------------------------------------------- #


def test_follow_shows_activity_and_the_answer_never_thinking(server, scripted):
    from tools.agent import store

    h = ask(server.member_id, channel="general")
    model = scripted(
        {"text": "", "calls": [("corpus_search", {"query": "cells"})]}, "Found it."
    )
    loop.run_turn(h.thread_id, port=model)
    thread = AgentThread.objects.get(pk=h.thread_id)
    store.append(thread, "thinking", {"text": "secret thoughts"})
    shown = list(surface.follow(h, poll=0.01))
    kinds = [m["type"] for m in shown]
    assert "activity" in kinds and kinds[-1] in ("assistant", "state")
    assert any(m["type"] == "assistant" and m["payload"].get("final") for m in shown)
    assert "secret" not in str(shown)
    assert all("args" not in (m.get("payload") or {}) for m in shown)


def test_follow_falls_back_to_the_log_when_the_bus_is_down(
    server, scripted, monkeypatch
):
    from tools.agent import stream

    h = ask(server.member_id, channel="general")
    loop.run_turn(h.thread_id, port=scripted("Answer."))

    def broken(*a, **k):
        raise ConnectionError("redis down")
        yield  # pragma: no cover

    monkeypatch.setattr(stream, "follow", broken)
    shown = list(surface.follow(h, poll=0.01))
    assert shown[-1]["type"] == "assistant" and shown[-1]["payload"]["final"]


def test_a_queued_question_is_followed_once_its_turn_starts(server, scripted):
    first = ask(server.member_id, thread="th-9", parent="general", text="one")
    AgentThread.objects.filter(pk=first.thread_id).update(state="running")
    second = ask(server.admin_id, thread="th-9", parent="general", text="two")
    assert second.queued and not second.user_event_seq
    AgentThread.objects.filter(pk=first.thread_id).update(state="idle")
    loop.run_turn(first.thread_id, port=scripted("first answer", "second answer"))
    assert surface.result(first)["text"] == "first answer"
    assert surface.result(second)["text"] == "second answer"
    shown = list(surface.follow(second, poll=0.01))
    finals = [m for m in shown if m["type"] == "assistant"]
    assert finals[-1]["payload"]["text"] == "second answer"


def test_recovery_lists_pending_turns_until_finished(server, scripted):
    h = ask(server.member_id, channel="general")
    assert [x.turn_id for x in surface.reconcile()] == [h.turn_id]
    loop.run_turn(h.thread_id, port=scripted("Done."))
    assert surface.result(h)["state"] == "answered"
    surface.finish(h, "answered")
    assert surface.reconcile() == []


def test_a_deleted_question_leaves_the_queue_and_is_blanked(server):
    first = ask(server.member_id, thread="th-9", parent="general", text="keep")
    AgentThread.objects.filter(pk=first.thread_id).update(state="running")
    queued = ask(server.admin_id, thread="th-9", parent="general", text="drop")
    assert surface.question_deleted(queued.trigger_message_id)
    from tools.agent.models import AgentQueuedMessage

    assert not AgentQueuedMessage.objects.filter(thread_id=first.thread_id).exists()
    assert surface.question_deleted(first.trigger_message_id)
    event = AgentThread.objects.get(pk=first.thread_id).events.get(type="user")
    assert event.payload["text"] == "" and event.payload["forgotten"]


def test_stop_is_for_the_asker_or_a_manager(server):
    h = ask(server.member_id, thread="th-9", parent="general")
    link(server.viewer, "102")
    refused = surface.stop(h, discord_user_id="102")
    assert refused is not None and refused.code == "forbidden"
    assert surface.stop(h, discord_user_id=server.admin_id) is None
    assert surface.result(h)["state"] == "cancelled"


def test_a_deleted_discord_thread_deletes_its_conversation(server):
    h = ask(server.member_id, thread="th-9", parent="general")
    assert surface.place_deleted("th-9") == 1
    assert not AgentThread.objects.filter(pk=h.thread_id).exists()


# --------------------------------------------------------------------------- #
# D4: commands and switches
# --------------------------------------------------------------------------- #


def _audited(action, outcome):
    from apps.accounts.models import AuditEvent

    return AuditEvent.objects.filter(
        action=f"discord.command.{action}", metadata__outcome=outcome
    ).count()


def test_switch_commands_are_refused_by_the_gate_for_the_wrong_person(server):
    ids = {"guild_id": GUILD, "channel_id": "general"}
    # a member is not a manager
    line = surface.set_channel(discord_user_id=server.member_id, on=False, **ids)
    assert line == "You don't have access to that."
    assert _audited("chat_manage", "forbidden") == 1
    line = surface.set_guests(discord_user_id=server.member_id, level="off", **ids)
    assert line == "You don't have access to that."
    # nobody linked: the personal switch and forget need an account
    assert "Connect Discord" in surface.set_chat(discord_user_id="5555", on=False)
    assert _audited("chat_self", "not_linked") == 1
    assert "Connect Discord" in surface.forget_command(
        discord_user_id="5555", guild_id="", place_id="dm-5555"
    )
    assert _audited("chat_forget", "not_linked") == 1
    # a manager is allowed, and that is audited too
    assert "off" in surface.set_channel(
        discord_user_id=server.admin_id, on=False, **ids
    )
    assert _audited("chat_manage", "allowed") == 1


def test_a_channel_turned_off_refuses_with_the_dm_line(server):
    surface.set_channel(
        discord_user_id=server.admin_id, guild_id=GUILD, channel_id="general", on=False
    )
    r = ask(server.member_id, channel="general")
    assert r.code == "channel_off" and "Ask in a DM instead." in r.message
    assert ask(server.member_id, guild="", channel="dm-100")  # a DM still works
    surface.set_channel(
        discord_user_id=server.admin_id, guild_id=GUILD, channel_id="general", on=True
    )
    assert ask(server.member_id, channel="general")


def test_a_channel_switch_in_a_thread_turns_off_its_parent(server):
    surface.set_channel(
        discord_user_id=server.admin_id,
        guild_id=GUILD,
        channel_id="th-3",
        thread_id="th-3",
        parent_id="forum-1",
        on=False,
    )
    assert AgentOrgPolicy.objects.get(lab=server.lab).discord_channels_off == [
        "forum-1"
    ]
    assert ask(server.member_id, thread="th-4", parent="forum-1").code == "channel_off"


def test_chat_off_is_respected_on_the_next_question(server):
    assert ask(server.member_id, channel="general")
    assert "off" in surface.set_chat(discord_user_id=server.member_id, on=False)
    assert ask(server.member_id, channel="general").code == "discord_off"
    surface.set_chat(discord_user_id=server.member_id, on=True)
    assert ask(server.member_id, channel="general")


def test_the_guest_level_command_states_the_level_in_force(server, settings):
    settings.AGENT_DISCORD_GUEST_LEVEL = "no_people"
    line = surface.set_guests(
        discord_user_id=server.admin_id,
        guild_id=GUILD,
        channel_id="general",
        level="full",
    )
    assert "at most **no-people**" in line
    assert AgentOrgPolicy.objects.get(lab=server.lab).discord_guests == "full"
    surface.set_guests(
        discord_user_id=server.admin_id,
        guild_id=GUILD,
        channel_id="general",
        level="off",
    )
    assert ask("4242", channel="general").code == "guests_off"


def test_forget_in_a_dm_deletes_the_conversation(server):
    h = ask(server.member_id, guild="", channel="dm-100")
    line = surface.forget_command(
        discord_user_id=server.member_id, guild_id="", place_id="dm-100"
    )
    assert "deleted" in line
    assert not AgentThread.objects.filter(pk=h.thread_id).exists()


def test_a_guest_may_forget_their_own_questions(server):
    ask("4242", thread="th-9", parent="general", text="guest question")
    line = surface.forget_command(
        discord_user_id="4242", guild_id=GUILD, place_id="th-9"
    )
    assert "blanked 1" in line


# --------------------------------------------------------------------------- #
# D5: learning, retention, removal
# --------------------------------------------------------------------------- #


def _quiet(handles):
    AgentThread.objects.filter(pk__in=[h.thread_id for h in handles]).update(
        last_activity_at=timezone.now() - timedelta(hours=2)
    )


def test_learning_reads_a_dm_and_never_a_shared_place(server, monkeypatch):
    from tools._framework import events as bus
    from tools.agent import learning

    handed = []
    monkeypatch.setattr(bus, "publish", lambda name, **kw: handed.append(kw))
    dm = ask(server.member_id, guild="", channel="dm-100", text="I study tides")
    member = ask(server.member_id, thread="th-9", parent="general", text="in thread")
    guest = ask("4242", channel="general", text="guest words")
    _quiet([dm, member, guest])
    assert learning.run_pass() == 1
    assert [m["text"] for m in handed[0]["messages"]] == ["I study tides"]
    assert handed[0]["thread_id"] == dm.thread_id


def test_a_closed_announcements_conversation_is_swept_after_the_set_days(
    server, settings
):
    from tools.agent import tasks
    from tools.delivery.models import AnnouncementPost

    announcement(server)
    h = ask(server.member_id, thread="th-1", parent="forum-1")
    settings.AGENT_DISCORD_CLOSED_THREAD_DAYS = 30
    AnnouncementPost.objects.filter(thread_id="th-1").update(
        closed_at=timezone.now() - timedelta(days=10)
    )
    assert tasks.retention_sweep() == 0
    AnnouncementPost.objects.filter(thread_id="th-1").update(
        closed_at=timezone.now() - timedelta(days=31)
    )
    assert tasks.retention_sweep() == 1
    assert not AgentThread.objects.filter(pk=h.thread_id).exists()


def test_a_removed_binding_or_a_left_server_closes_its_links(server):
    h = ask(server.member_id, thread="th-9", parent="general")
    resolve.remove_binding(server.binding)
    assert AgentThreadLink.objects.get(thread_id=h.thread_id).closed_at is not None
    assert ask(server.member_id, thread="th-9", parent="general").code == "unbound"
    server.binding.state = "active"
    server.binding.save()
    h2 = ask(server.member_id, thread="th-9", parent="general")
    assert h2.thread_id != h.thread_id  # a fresh conversation after re-activation
    resolve.mark_guild_kicked(GUILD)
    assert AgentThreadLink.objects.filter(closed_at=None).count() == 0


def test_an_item_without_a_source_page_falls_back_to_the_app(settings):
    settings.DISCORD_APP_BASE_URL = "https://app.example.org/"
    url = surface._item_url("ab-12", guest=False, title="[grant] Ocean call")
    assert url == "https://app.example.org/app/grants?item=ab-12"
    paper = surface._item_url("ab-12", guest=False, title="Untyped title")
    assert paper == "https://app.example.org/app/research-papers?item=ab-12"
    assert surface._item_url("ab-12", guest=True, title="[grant] x") == ""
    settings.DISCORD_APP_BASE_URL = ""
    assert surface._item_url("ab-12", guest=False, title="[grant] x") == ""


def test_every_link_goes_to_the_items_own_page(settings):
    from tools.retrieval.models import ContentItem

    settings.DISCORD_APP_BASE_URL = "https://app.example.org/"
    grant = ContentItem.objects.create(
        type="grant",
        source="grants.gov",
        source_url="https://grants.example.gov/ocean",
    )
    conf = ContentItem.objects.create(
        type="conference",
        source="wikicfp",
        metadata={"website": "https://sigx.example.org"},
    )
    for guest in (False, True):
        url = surface._item_url(str(grant.pk), guest=guest, title="[grant] Ocean")
        assert url == "https://grants.example.gov/ocean"
        url = surface._item_url(str(conf.pk), guest=guest, title="[conference] X")
        assert url == "https://sigx.example.org"


def test_discord_is_told_to_answer_not_to_list(server, scripted):
    prompt = _system_prompt(ask(server.member_id), scripted)
    assert "A list of titles is not an answer" in prompt
    assert "[[links]]" in prompt
    assert "Keep it short" not in prompt

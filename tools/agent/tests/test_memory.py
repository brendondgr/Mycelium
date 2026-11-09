"""Phase 7: learning from quiet threads (D-2, D-3), recall boundaries."""

from __future__ import annotations

from datetime import timedelta

import pytest
from apps.ambient import buffer
from apps.ambient.models import ListeningConsent, Observation, RawMessageRef, Source
from django.core.cache import caches
from django.utils import timezone

from tools._framework import events as bus
from tools.agent import learning, loop, recall, service, store
from tools.agent.caller import Audience, Caller, Scope, for_thread
from tools.agent.models import AgentThread

from .conftest import make_user, thread_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _ambient_buffer(settings):
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "agent-memory-tests",
        },
    }
    settings.AGENT_LEARNING = True
    settings.AMBIENT_ENABLED = False  # Mylo chat has its own switch
    caches["ambient"].clear()
    yield
    try:  # housekeeping only; another module may have swapped the backend
        caches["ambient"].clear()
    except Exception:
        pass


def _chat(user, scripted, *texts, reply="Noted."):
    thread = thread_for(user)
    for text in texts:
        service.send(for_thread(thread), thread, text, start=lambda t: None)
        loop.run_turn(thread.pk, port=scripted(reply, '{"title": "t", "purpose": "p"}'))
    AgentThread.objects.filter(pk=thread.pk).update(
        last_activity_at=timezone.now() - timedelta(hours=1)
    )
    return thread


def _bodies(user):
    refs = RawMessageRef.objects.filter(speaker=user)
    return [
        buffer.get(ref.source_id, ref.external_id) if hasattr(buffer, "get") else None
        for ref in refs
    ], refs


def test_learning_is_on_by_default_and_records_only_the_persons_words(db, scripted):
    user = make_user("ada")
    thread = _chat(
        user,
        scripted,
        "I'm moving to clinical work next year",
        reply="SECRET-AGENT-TEXT about clinical work",
    )
    assert learning.run_pass() == 1
    refs = RawMessageRef.objects.filter(speaker=user)
    assert refs.count() == 1
    source = refs.first().source
    assert source.kind == Source.Kind.AGENT_CHAT and source.lab_id is None
    assert refs.first().explicit is True
    # nothing Mylo said entered the ledger
    for key in caches["ambient"]._cache.keys():
        assert b"SECRET-AGENT-TEXT" not in caches["ambient"]._cache[key]
    thread.refresh_from_db()
    assert thread.learned_seq == store.last_seq(thread)
    # a second pass with nothing new hands nothing over
    assert learning.run_pass() == 0


def test_opting_out_stops_recording_at_the_next_message(db, scripted):
    user = make_user("ada")
    _chat(user, scripted, "first thing")
    learning.run_pass()
    assert RawMessageRef.objects.filter(speaker=user).count() == 1
    service.set_preferences(user, learning=False)
    assert (
        ListeningConsent.objects.get(user=user, platform="agent_chat").enabled is False
    )
    thread = _chat(user, scripted, "second thing")
    # even a direct hand-off is refused by eligibility on arrival
    bus.publish(
        "agent.thread_quiet",
        raise_errors=True,
        **learning.payload(
            thread, [{"seq": 99, "ts": timezone.now().isoformat(), "text": "sneaked"}]
        ),
    )
    learning.run_pass()
    assert RawMessageRef.objects.filter(speaker=user).count() == 1


def test_turning_learning_back_on_marks_old_chats_read(db, scripted):
    user = make_user("ada")
    service.set_preferences(user, learning=False)
    thread = _chat(user, scripted, "old chat")
    service.set_preferences(user, learning=True)
    thread.refresh_from_db()
    assert thread.learned_seq == store.last_seq(thread)
    assert learning.run_pass() == 0


def test_the_instance_switch_turns_learning_off(db, scripted, settings):
    user = make_user("ada")
    _chat(user, scripted, "hello")
    settings.AGENT_LEARNING = False
    assert learning.run_pass() == 0
    assert not RawMessageRef.objects.filter(speaker=user).exists()


def test_a_failed_hand_off_backs_off(db, scripted, monkeypatch):
    user = make_user("ada")
    thread = _chat(user, scripted, "hello")

    def boom(**_):
        raise RuntimeError("ledger down")

    bus.subscribe("agent.thread_quiet", boom)
    try:
        assert learning.run_pass() == 0
    finally:
        bus.unsubscribe("agent.thread_quiet", boom)
    thread.refresh_from_db()
    assert thread.learn_failures == 1 and thread.learn_after > timezone.now()
    assert thread.learned_seq == 0
    assert learning.run_pass() == 0  # still backing off


def test_deleting_a_thread_leaves_the_ledger_and_forget_removes_it(db, scripted):
    from apps.ambient.review import delete_everything

    user = make_user("ada")
    thread = _chat(user, scripted, "I work on conformal prediction")
    learning.run_pass()
    service.delete_thread(user, thread.pk)
    assert RawMessageRef.objects.filter(speaker=user).count() == 1
    delete_everything(user)
    assert not RawMessageRef.objects.filter(speaker=user).exists()
    assert not Observation.objects.filter(speaker=user).exists()


def test_mylo_and_you_shows_the_chat_switch(db):
    from apps.ambient.review import settings_for, update_settings

    user = make_user("ada")
    assert settings_for(user)["listening"]["mylo_chat"] is True
    update_settings(user, {"listening_mylo_chat": False})
    assert service.learning_enabled(user) is False


def test_recall_never_crosses_people(world, scripted):
    """CIMemories-style: what one member told Mylo never reaches another."""
    secret = thread_for(world.member)
    service.send(
        for_thread(secret),
        secret,
        "my grant deadline is in March",
        start=lambda t: None,
    )
    loop.run_turn(
        secret.pk,
        port=scripted(
            "Noted.", '{"title": "Grant deadline", "purpose": "march grant deadline"}'
        ),
    )
    other = thread_for(world.admin)
    facts = recall.search(
        Caller(user=world.admin, surface="web", thread_id=other.pk),
        other,
        "what is the grant deadline in March?",
    )
    assert not any("deadline" in f.lower() for f in facts)
    mine = thread_for(world.member)
    facts = recall.search(
        Caller(user=world.member, surface="web", thread_id=mine.pk),
        mine,
        "what is the grant deadline in March?",
    )
    assert any("deadline" in f.lower() for f in facts)


def test_recall_in_a_shared_channel_holds_nothing_personal(world, scripted):
    from apps.ambient.models import ProjectDevelopment

    first = thread_for(world.member)
    service.send(
        for_thread(first),
        first,
        "Segmentation is blocked on labels",
        start=lambda t: None,
    )
    loop.run_turn(
        first.pk,
        port=scripted(
            "Noted.", '{"title": "Segmentation blockers", "purpose": "labels"}'
        ),
    )
    ProjectDevelopment.objects.create(
        project=world.lab_project,
        speaker=world.member,
        change="experiment_failed",
        occurred_on=timezone.localdate(),
        topic="private worry",
        text="x",
        visibility="personal",
        status=ProjectDevelopment.Status.CONFIRMED,
        origin=ProjectDevelopment.Origin.TOLD,
    )
    channel = thread_for(world.member, "lab", world.lab)
    c = Caller(
        user=world.member,
        surface="discord",
        scope=Scope("lab", world.lab),
        audience=Audience("lab"),
        thread_id=channel.pk,
    )
    facts = recall.search(c, channel, "how is Segmentation going?")
    assert not any("Earlier conversation" in f or "private worry" in f for f in facts)

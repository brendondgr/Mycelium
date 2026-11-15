"""The personal-information opt-out (Q-071).

With the switch on, a planted health or visa statement is not recorded while a
research statement in the same conversation is; with it off, both are, as
before. Turning it on deletes what is already marked personal, and the hourly
sweep marks — and deletes — what was written before the extractor was asked.
"""

from __future__ import annotations

import json

import pytest

from apps.accounts.models import Lab
from apps.ambient import personal, reading, service
from apps.ambient.models import (
    ExtractionRun,
    ListeningConsent,
    Observation,
    Origin,
    Platform,
    Retraction,
    Visibility,
)
from apps.ambient.tests.test_reasoning import (  # noqa: F401 - autouse fixtures
    GUILD,
    FakeModel,
    _ambient_on,
    _obs,
    _person,
    _say,
    fake_embedder,
)
from apps.billing.models import Tier
from apps.knowledge.tests.conftest import embedder  # noqa: F401 - the fake embedder


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="PULSE", slug="pulse")


@pytest.fixture
def ada(db):
    return _person("ada", "111")


@pytest.fixture
def bo(db):
    return _person("bo", "222")


@pytest.fixture
def source(lab):
    service.set_guild_listening(GUILD, on=True, lab=lab)
    return service.guild_source(GUILD)


HEALTH = "My doctor says the chronic migraines will slow me down this term"
VISA = "Honestly my visa renewal is stuck and I may have to leave in March"
RESEARCH = "I would like to try conformal prediction on the imaging scans"


def _window(author="111"):
    _say(HEALTH, mid="1", author=author)
    _say(VISA, mid="2", author=author)
    _say(RESEARCH, mid="3", author=author)


def _model(*, personal_answer=True):
    """Health and visa marked personal, the research line marked work."""

    def mark(entry, value):
        if value is not None:
            entry["personal"] = value
        return entry

    return FakeModel(
        mark(
            _obs(
                HEALTH,
                kind="capability",
                force="fact",
                facet="setting",
                topic="chronic migraines",
                account="Told the lab a medical problem is slowing their term.",
            ),
            personal_answer,
        ),
        mark(
            _obs(
                VISA,
                kind="career_direction",
                force="possibility",
                facet="setting",
                topic="visa renewal",
                account="Mentioned trouble with an immigration document.",
            ),
            personal_answer,
        ),
        mark(_obs(RESEARCH), False),
    )


def _opt_out(user):
    personal.set_withheld(user, on=True)


def _note(user, *, topic, text, flag, kind="current_curiosity"):
    from django.utils import timezone

    return Observation.objects.create(
        source=service.guild_source(GUILD),
        observed_at=timezone.now(),
        speaker=user,
        text=text,
        subject="self",
        understanding_kind=kind,
        force="fact",
        visibility=Visibility.PERSONAL,
        origin=Origin.MODEL,
        topic=topic,
        place_kind="channel",
        personal_life=flag,
    )


# -- at extraction -------------------------------------------------------------


def test_on_drops_health_and_visa_and_keeps_research_from_one_window(source, ada):
    _opt_out(ada)
    _window()
    result = reading.read_ready(complete=_model())
    assert result.observations == 1 and result.withheld == 2
    kept = Observation.objects.get()
    assert kept.topic == "conformal prediction" and kept.personal_life is False
    run = ExtractionRun.objects.get()
    assert run.withheld == 2 and run.observations_kept == 1
    assert run.outcome == ExtractionRun.Outcome.READ


def test_off_records_them_as_before_and_remembers_the_answer(source, ada):
    _window()
    result = reading.read_ready(complete=_model())
    assert result.observations == 3 and result.withheld == 0
    flags = dict(Observation.objects.values_list("topic", "personal_life"))
    assert flags == {
        "chronic migraines": True,
        "visa renewal": True,
        "conformal prediction": False,
    }
    assert set(Observation.objects.values_list("visibility", flat=True)) == {
        Visibility.PERSONAL
    }


def test_an_unmarked_observation_is_dropped_only_for_who_opted_out(source, ada, bo):
    _opt_out(ada)
    _window(author="111")
    reading.read_ready(complete=_model(personal_answer=None))
    assert list(Observation.objects.values_list("topic", flat=True)) == [
        "conformal prediction"
    ]
    Observation.objects.all().delete()
    ExtractionRun.objects.all().delete()
    for mid, text in (("11", HEALTH), ("12", VISA), ("13", RESEARCH)):
        _say(text, mid=mid, author="222", place="chan-2")
    reading.read_ready(complete=_model(personal_answer=None))
    # Bo did not opt out: unmarked is recorded, as before, and left for a sweep.
    assert Observation.objects.filter(speaker=bo).count() == 3
    assert Observation.objects.filter(personal_life__isnull=True).count() == 2


# -- turning it on ---------------------------------------------------------------


def test_turning_it_on_deletes_what_is_marked_personal_and_says_so(source, ada):
    health = _note(
        ada, topic="health condition", text="Said a medical issue.", flag=True
    )
    work = _note(ada, topic="kriging", text="Said they ran kriging again.", flag=False)
    older = _note(
        ada, topic="advisor", text="Said they argued with someone.", flag=None
    )
    assert personal.set_withheld(ada, on=True) == 1
    assert set(Observation.objects.values_list("pk", flat=True)) == {work.pk, older.pk}
    retraction = Retraction.objects.get()
    assert retraction.user == ada and retraction.observation_ids == [health.pk]
    # Off again brings nothing back and deletes nothing more.
    assert personal.set_withheld(ada, on=False) == 0
    assert Observation.objects.count() == 2


def test_the_switch_is_in_the_settings_and_open_to_a_free_plan(db, client):
    fay = _person("fay", "444", tier=Tier.FREE)
    client.force_login(fay)
    assert client.get("/api/ambient/settings/").json()["personal_withheld"] is False
    body = client.put(
        "/api/ambient/settings/",
        {"personal_withheld": True},
        content_type="application/json",
    ).json()
    assert body["personal_withheld"] is True and body["personal_removed"] == 0
    assert (
        ListeningConsent.objects.get(
            user=fay, platform=Platform.DISCORD
        ).personal_withheld_at
        is not None
    )
    body = client.put(
        "/api/ambient/settings/",
        {"personal_withheld": False},
        content_type="application/json",
    ).json()
    assert body["personal_withheld"] is False


# -- the sweep of older rows ----------------------------------------------------


class Sorter:
    """Marks the notes whose topic is in ``personal_topics``."""

    def __init__(self, *personal_topics, raise_error=False):
        self.topics = personal_topics
        self.raise_error = raise_error
        self.calls = 0

    def __call__(self, system, prompt):
        self.calls += 1
        if self.raise_error:
            raise ConnectionError("model down")
        marked = []
        for line in prompt.splitlines():
            if line.startswith("[") and any(f"({t})" in line for t in self.topics):
                marked.append(int(line[1 : line.index("]")]))
        return json.dumps({"personal": marked})


def test_the_sweep_marks_older_rows_and_deletes_the_personal_ones(source, ada, bo):
    _opt_out(ada)
    health = _note(
        ada, topic="health condition", text="Said a medical issue.", flag=None
    )
    work = _note(ada, topic="kriging", text="Said they ran kriging again.", flag=None)
    theirs = _note(
        bo, topic="health condition", text="Said a medical issue.", flag=None
    )
    sorter = Sorter("health condition")
    counts = personal.sweep(complete=sorter)
    assert counts == {"marked": 2, "deleted": 1, "unavailable": 0}
    assert not Observation.objects.filter(pk=health.pk).exists()
    assert Observation.objects.get(pk=work.pk).personal_life is False
    # Bo did not opt out: never sent, never touched.
    assert Observation.objects.get(pk=theirs.pk).personal_life is None
    # Nothing left to ask about.
    assert personal.sweep(complete=sorter) == {
        "marked": 0,
        "deleted": 0,
        "unavailable": 0,
    }
    assert sorter.calls == 1


@pytest.mark.parametrize("reply", ["no json", '{"personal": [9]}'])
def test_an_unusable_answer_changes_nothing(source, ada, reply):
    _opt_out(ada)
    note = _note(ada, topic="health condition", text="Said a medical issue.", flag=None)
    counts = personal.sweep(complete=lambda s, p: reply)
    assert counts["unavailable"] == 1 and counts["deleted"] == 0
    assert Observation.objects.get(pk=note.pk).personal_life is None


def test_an_unreachable_model_leaves_older_rows_for_the_next_hour(source, ada):
    _opt_out(ada)
    note = _note(ada, topic="health condition", text="Said a medical issue.", flag=None)
    counts = personal.sweep(complete=Sorter(raise_error=True))
    assert counts["unavailable"] == 1
    assert Observation.objects.get(pk=note.pk).personal_life is None

"""Plan 04 — the reasoning agent: windows, extraction, deliberation, explanation.

Fixture conversations for each force; a rejection retiring a possibility; a
colleague's idea not moving a profile; the budget refusing a seventh cluster;
and the plan's acceptance criteria, each as a test.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone

from apps.accounts.models import Lab
from apps.ambient import deliberate, explain, extract, reading, service, windows
from apps.ambient.models import (
    ExtractionRun,
    Finding,
    ListeningConsent,
    Observation,
    Platform,
    RawMessageRef,
    Source,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import DiscordIdentity
from apps.knowledge.models import Concept, Edge, EdgeStatus, Facet, Relation, Scope
from apps.knowledge.tests.conftest import embedder  # noqa: F401 - the fake embedder
from apps.knowledge.tests.fakes import FakeEmbedder
from apps.research.models import Project, ProjectMember

GUILD = "700"


@pytest.fixture(autouse=True)
def _ambient_on(settings):
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_DELIBERATE_ENABLED = True
    settings.AMBIENT_MIN_MESSAGE_CHARS = 1
    settings.AMBIENT_RAW_TTL_HOURS = 6
    settings.AMBIENT_WINDOW_QUIET_MINUTES = 60
    settings.AMBIENT_WINDOW_HOURS = 4
    settings.AMBIENT_WINDOW_MAX_MESSAGES = 40
    settings.AMBIENT_EXTRACT_CONCURRENCY = 1
    settings.AMBIENT_EXTRACT_DAILY_CAP_PER_LAB = 200
    settings.AMBIENT_CONSISTENT_DAYS = 2
    settings.AMBIENT_CONSISTENT_SPAN_DAYS = 5
    settings.AMBIENT_CONSISTENT_CONVERSATIONS = 2
    settings.AMBIENT_COVERED_SIMILARITY = 0.85
    settings.AMBIENT_DECLINE_REST_DAYS = 30
    settings.CACHES = {
        **settings.CACHES,
        "ambient": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ambient-reasoning",
        },
    }
    caches["ambient"].clear()
    yield
    caches["ambient"].clear()


@pytest.fixture(autouse=True)
def fake_embedder(embedder):  # noqa: F811
    return embedder


def _person(name: str, snowflake: str, *, tier=Tier.SPORE) -> User:
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    Subscription.objects.create(tier=tier, scope_user=user)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id=snowflake,
        link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
        state=DiscordIdentity.State.ACTIVE,
    )
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    return user


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
def imaging(lab, ada, bo):
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    for person in (ada, bo):
        ProjectMember.objects.create(project=project, user=person)
    return project


@pytest.fixture
def source(lab):
    service.set_guild_listening(GUILD, on=True, lab=lab)
    return service.guild_source(GUILD)


def _say(
    text,
    *,
    author="111",
    mid,
    minutes_ago=90,
    place="chan-1",
    label="methods",
    mentions=None,
    reply_to="",
    from_mylo=False,
):
    return service.heard(
        guild_id=GUILD,
        message_id=mid,
        text=text,
        sent_at=timezone.now() - timedelta(minutes=minutes_ago),
        author_id=author,
        place_id=place,
        place_label=label,
        mention_ids=mentions,
        reply_to_id=reply_to,
        from_mylo=from_mylo,
        explicit=False,
    )


# -- a fake model --------------------------------------------------------------


def _line(prompt: str, phrase: str) -> int:
    for match in re.finditer(r"^\[(\d+)\] Speaker .*?\): (.*)$", prompt, re.M):
        if phrase.lower() in match.group(2).lower():
            return int(match.group(1))
    return -1


class FakeModel:
    """Answers with observations for the phrases it is told to look for."""

    def __init__(self, *wanted, raise_error=False):
        self.wanted = wanted
        self.raise_error = raise_error
        self.calls = 0

    def __call__(self, system, prompt):
        self.calls += 1
        if self.raise_error:
            raise ConnectionError("model down")
        out = []
        for want in self.wanted:
            number = _line(prompt, want["sentence"])
            if number < 0 and not want.get("line_anyway"):
                continue
            out.append({"line": number if number > 0 else 1, **want})
        return "Here you go:\n```json\n" + json.dumps({"observations": out}) + "\n```"


def _obs(
    sentence,
    *,
    kind="current_curiosity",
    force="preference",
    subject="self",
    facet="method",
    topic="conformal prediction",
    account="Said they would like to try this method on their data.",
):
    return {
        "sentence": sentence,
        "kind": kind,
        "force": force,
        "subject": subject,
        "facet": facet,
        "topic": topic,
        "account": account,
        "confidence": 0.9,
    }


# -- windows -------------------------------------------------------------------


def test_a_conversation_is_ready_only_once_its_place_goes_quiet(source, ada):
    _say("thinking about conformal prediction", mid="1", minutes_ago=200)
    _say("for the imaging intervals", mid="2", minutes_ago=190)
    _say("a new thing entirely", mid="3", minutes_ago=10)
    specs = windows.ready()
    assert len(specs) == 1
    assert len(specs[0].ref_ids) == 2


def test_a_body_about_to_expire_is_read_even_while_the_place_is_busy(source, ada):
    _say("still talking about intervals", mid="1", minutes_ago=5)
    RawMessageRef.objects.update(buffered_until=timezone.now() + timedelta(minutes=30))
    assert len(windows.ready()) == 1


def test_a_window_is_capped_by_messages(source, ada, settings):
    settings.AMBIENT_WINDOW_MAX_MESSAGES = 3
    for i in range(7):
        _say(f"message number {i} about intervals", mid=str(i), minutes_ago=300 - i)
    specs = windows.ready()
    assert [len(s.ref_ids) for s in specs] == [3, 3, 1]


# -- extraction ----------------------------------------------------------------


def _conversation(source):
    spec = windows.ready()[0]
    return windows.assemble(spec)


def test_a_window_with_nothing_groundable_yields_nothing_and_no_error(source, ada):
    """Acceptance: zero observations and no error."""
    _say("morning all, coffee in five", mid="1")
    model = FakeModel(_obs("I want to try conformal prediction"))
    result = reading.read_ready(complete=model)
    assert result.read == 1 and result.observations == 0
    assert Observation.objects.count() == 0
    assert ExtractionRun.objects.get().outcome in ("empty", "refused")


def test_an_ungrounded_sentence_is_refused(source, ada):
    _say("I would like to try conformal prediction on the scans", mid="1")
    model = FakeModel(
        {
            **_obs("I adore Bayesian optimisation", topic="conformal prediction"),
            "line_anyway": True,
        }
    )
    outcome = extract.extract(_conversation(source), complete=model)
    assert outcome.observations == []
    assert "not_grounded" in outcome.refused
    assert model.calls == 2  # one repair, then refusal


def test_the_speaker_is_the_message_author_never_the_model(source, ada, bo):
    _say("the loader is flaky again today", mid="1", author="111", minutes_ago=95)
    _say("I would like to try conformal prediction on the scans", mid="2", author="222")
    sentence = "I would like to try conformal prediction on the scans"
    # The model cites line 1 (ada's); the sentence it copied is bo's.
    outcome = extract.extract(
        _conversation(source),
        complete=lambda s, p: json.dumps(
            {"observations": [{**_obs(sentence), "line": 1}]}
        ),
    )
    assert len(outcome.observations) == 1
    assert outcome.observations[0].line.speaker_id == bo.pk


def test_an_account_that_quotes_the_speaker_is_refused(source, ada):
    _say(
        "I would really like to try conformal prediction on the imaging scans", mid="1"
    )
    quoting = _obs(
        "I would really like to try conformal prediction on the imaging scans",
        account=(
            "They said: really like to try conformal prediction on the imaging scans."
        ),
    )
    outcome = extract.extract(_conversation(source), complete=FakeModel(quoting))
    assert outcome.observations == []
    assert "quote_in_account" in outcome.refused


def test_mylo_and_replies_to_mylo_are_context_never_evidence(source, ada):
    """Acceptance: Mylo's own recommendation, replied to, yields no interest
    observation."""
    _say(
        "Here is a paper on conformal prediction you may like",
        mid="m1",
        author="999",
        from_mylo=True,
        minutes_ago=120,
    )
    _say(
        "I love conformal prediction, more like this please",
        mid="2",
        reply_to="m1",
        minutes_ago=110,
    )
    conversation = _conversation(source)
    assert conversation.evidence == []
    prompt, numbered = extract.prompt_for(conversation)
    assert numbered == {}
    assert "(context) Mylo" in prompt
    model = FakeModel(_obs("I love conformal prediction", force="preference"))
    result = reading.read_ready(complete=model)
    assert model.calls == 0
    assert Observation.objects.count() == 0
    assert ExtractionRun.objects.get().engagement == 1
    assert result.read == 1


def test_speakers_are_letters_not_names(source, ada):
    _say("I would like to try conformal prediction", mid="1")
    prompt, _ = extract.prompt_for(_conversation(source))
    assert "Speaker A" in prompt and "ada" not in prompt


# -- the hourly read -----------------------------------------------------------


def test_reading_writes_observations_links_topics_and_deletes_the_text(
    source, ada, imaging
):
    _say("I would like to try conformal prediction on the imaging scans", mid="1")
    model = FakeModel(
        _obs("I would like to try conformal prediction on the imaging scans")
    )
    result = reading.read_ready(complete=model)
    assert result.observations == 1 and result.linked == 1
    observation = Observation.objects.get()
    assert observation.speaker == ada
    assert observation.topic == "conformal prediction"
    assert observation.concept is not None
    assert observation.concept.scope == Scope.PERSONAL  # born private
    assert observation.visibility == Visibility.PERSONAL
    assert "conformal prediction on the imaging scans" not in observation.text
    ref = RawMessageRef.objects.get()
    assert ref.read_at is not None and ref.buffered_until is None
    assert caches["ambient"].get(f"raw:{source.pk}:1") is None


def test_an_unchanged_window_is_never_read_twice(source, ada):
    _say("I would like to try conformal prediction", mid="1")
    reading.read_ready(
        complete=FakeModel(_obs("I would like to try conformal prediction"))
    )
    # The same window arrives again (a replay): same ids, same bodies.
    RawMessageRef.objects.update(read_at=None)
    caches["ambient"].set(
        f"raw:{source.pk}:1", "I would like to try conformal prediction"
    )
    model = FakeModel(_obs("I would like to try conformal prediction"))
    result = reading.read_ready(complete=model)
    assert model.calls == 0 and result.duplicate == 1


def test_an_unreachable_model_leaves_the_window_for_the_next_hour(source, ada):
    _say("I would like to try conformal prediction", mid="1")
    result = reading.read_ready(complete=FakeModel(raise_error=True))
    assert result.unavailable == 1
    ref = RawMessageRef.objects.get()
    assert ref.read_at is None
    assert caches["ambient"].get(f"raw:{source.pk}:1") is not None
    assert not ExtractionRun.objects.exists()
    # Nothing rule-based stood in.
    assert not Observation.objects.exists()


def test_a_window_whose_text_expired_is_closed_without_a_call(source, ada):
    _say("I would like to try conformal prediction", mid="1")
    caches["ambient"].clear()
    model = FakeModel(_obs("I would like to try conformal prediction"))
    result = reading.read_ready(complete=model)
    assert model.calls == 0 and result.expired == 1
    assert ExtractionRun.objects.get().outcome == "expired"


def test_the_daily_cap_holds_per_lab(source, ada, settings):
    settings.AMBIENT_EXTRACT_DAILY_CAP_PER_LAB = 1
    _say("I would like to try conformal prediction", mid="1", place="a")
    _say("I would like to try kriging", mid="2", place="b")
    model = FakeModel()
    result = reading.read_ready(complete=model)
    assert model.calls == 1 and result.capped == 1


def test_nothing_is_read_while_ambient_is_off(source, ada, settings):
    _say("I would like to try conformal prediction", mid="1")
    settings.AMBIENT_ENABLED = False
    model = FakeModel()
    assert reading.read_ready(complete=model).ready == 0
    assert model.calls == 0


def test_a_lab_project_development_is_lab_visible_and_born_in_the_lab(
    source, ada, imaging, monkeypatch
):
    _say("The imaging pipeline dataset arrived from the scanner team", mid="1")
    RawMessageRef.objects.update(project=imaging)
    monkeypatch.setattr(reading, "_attribute", lambda conversation: conversation)
    reading.read_ready(
        complete=FakeModel(
            _obs(
                "The imaging pipeline dataset arrived from the scanner team",
                kind="project_development",
                force="fact",
                subject="project",
                facet="setting",
                topic="scanner dataset",
                account="Reported that new scanner data has come in for the project.",
            )
        )
    )
    observation = Observation.objects.get()
    assert observation.project == imaging
    assert observation.visibility == Visibility.LAB
    assert observation.concept.scope == Scope.LAB


# -- deliberation --------------------------------------------------------------


def _concept(label, facet=Facet.METHOD, scope=Scope.GLOBAL, owner=None):
    kwargs = {"scope": scope}
    if scope == Scope.PERSONAL:
        kwargs["scope_user"] = owner
    vector = FakeEmbedder().vector(label)
    return Concept.objects.create(label=label, facet=facet, embedding=vector, **kwargs)


def _noted(
    person,
    concept,
    *,
    days_ago,
    force="preference",
    kind="current_curiosity",
    subject="self",
    conversation=None,
    explicit=False,
    project=None,
    visibility=Visibility.PERSONAL,
    source=None,
):
    return Observation.objects.create(
        source=source
        or Source.objects.get_or_create(
            kind=Source.Kind.DISCORD_DM,
            external_id=f"dm-{person.pk}",
            defaults={"consent_state": Source.Consent.ACTIVE},
        )[0],
        external_message_ids=["x"],
        observed_at=timezone.now() - timedelta(days=days_ago),
        speaker=person,
        text="Said they want to look into this topic further.",
        subject=subject,
        understanding_kind=kind,
        force=force,
        place_kind="channel",
        visibility=visibility,
        facet=concept.facet,
        topic=concept.label,
        concept=concept,
        explicit=explicit,
        project=project,
        conversation_key=conversation or f"c-{days_ago}-{force}",
    )


def _finding(person, concept, kind="current_curiosity"):
    return Finding.objects.get(user=person, concept=concept, understanding_kind=kind)


def test_two_mentions_on_one_day_do_not_reach_the_floor(ada):
    """Acceptance, first half."""
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=3, conversation="a")
    _noted(ada, cp, days_ago=3, conversation="b")
    deliberate.deliberate()
    finding = _finding(ada, cp)
    assert finding.outcome == Finding.Outcome.IGNORE
    assert finding.reason == "below_floor"


def test_the_same_two_across_two_weeks_do(ada):
    """Acceptance, second half."""
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    deliberate.deliberate()
    finding = _finding(ada, cp)
    assert finding.outcome == Finding.Outcome.SUGGEST
    assert finding.facts["days"] == 2 and finding.facts["conversations"] == 2
    assert finding.explained == Finding.Explained.PENDING
    assert finding.budget["room_for_cluster"] is True


def test_only_questions_and_possibilities_never_suggest(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, force="question")
    _noted(ada, cp, days_ago=1, force="possibility")
    deliberate.deliberate()
    assert _finding(ada, cp).outcome == Finding.Outcome.IGNORE


def test_one_long_session_counts_once(ada):
    cp = _concept("conformal prediction")
    for days in (9, 8, 1):
        _noted(ada, cp, days_ago=days, conversation="one-long-debugging-session")
    deliberate.deliberate()
    finding = _finding(ada, cp)
    assert finding.facts["conversations"] == 1
    assert finding.outcome == Finding.Outcome.IGNORE


def test_a_later_rejection_retires_earlier_possibilities(ada):
    cp = _concept("conformal prediction")
    early = _noted(ada, cp, days_ago=15, force="possibility")
    _noted(ada, cp, days_ago=10, force="preference", conversation="p")
    no = _noted(ada, cp, days_ago=2, force="rejection", conversation="r")
    run = deliberate.deliberate()
    early.refresh_from_db()
    no.refresh_from_db()
    assert early.status == Observation.Status.SUPERSEDED
    assert no.supersedes_id is not None
    assert run.superseded >= 2
    assert _finding(ada, cp).outcome == Finding.Outcome.IGNORE


def test_a_colleagues_idea_does_not_move_a_profile(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, subject="colleague", conversation="a")
    _noted(ada, cp, days_ago=1, subject="colleague", conversation="b")
    deliberate.deliberate()
    finding = _finding(ada, cp)
    assert finding.outcome == Finding.Outcome.IGNORE and finding.reason == "not_self"


def test_self_or_colleague_unclear_is_asked(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, subject="unknown", conversation="a")
    _noted(ada, cp, days_ago=1, subject="unknown", conversation="b")
    deliberate.deliberate()
    assert _finding(ada, cp).outcome == Finding.Outcome.ASK


def test_a_declared_topic_is_covered_and_silent(ada):
    cp = _concept("conformal prediction")
    Edge.objects.create(
        user=ada, concept=cp, relation=Relation.INTERESTED_IN, tier="declared"
    )
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    deliberate.deliberate()
    finding = _finding(ada, cp)
    assert finding.outcome == Finding.Outcome.IGNORE and finding.reason == "covered"
    assert finding.explained == Finding.Explained.NOT_NEEDED


def test_a_near_synonym_of_a_declared_topic_is_covered(ada, fake_embedder):
    fake_embedder.near("conformal prediction", "conformal methods", spread=0.05)
    declared = Concept.objects.create(
        label="conformal prediction",
        facet=Facet.METHOD,
        embedding=fake_embedder.vector("conformal prediction"),
    )
    said = Concept.objects.create(
        label="conformal methods",
        facet=Facet.METHOD,
        scope=Scope.PERSONAL,
        scope_user=ada,
        embedding=fake_embedder.vector("conformal methods"),
    )
    Edge.objects.create(
        user=ada, concept=declared, relation=Relation.INTERESTED_IN, tier="declared"
    )
    _noted(ada, said, days_ago=15, conversation="a")
    _noted(ada, said, days_ago=1, conversation="b")
    deliberate.deliberate()
    assert _finding(ada, said).reason == "covered"


def test_a_declined_topic_rests_then_needs_fresh_consistency(ada, settings):
    settings.AMBIENT_LOOKBACK_DAYS = 60
    cp = _concept("conformal prediction")
    edge = Edge.objects.create(
        user=ada,
        concept=cp,
        relation=Relation.INTERESTED_IN,
        tier="conversational",
        status=EdgeStatus.REJECTED,
    )
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")

    def said_no(days_ago):
        Edge.objects.filter(pk=edge.pk).update(
            updated_at=timezone.now() - timedelta(days=days_ago)
        )
        deliberate.deliberate()
        return _finding(ada, cp).reason

    assert said_no(0) == "declined_resting"
    # Said no 35 days ago, and both mentions came after it: askable again.
    assert said_no(35) == "consistent"
    # Now one mention predates the no: the one since is not consistency afresh.
    Observation.objects.filter(conversation_key="a").update(
        observed_at=timezone.now() - timedelta(days=40)
    )
    assert said_no(35) == "declined_not_returned"


def test_a_capability_is_a_skill_never_an_area(ada):
    kriging = _concept("kriging")
    _noted(ada, kriging, days_ago=15, kind="capability", force="fact", conversation="a")
    _noted(ada, kriging, days_ago=1, kind="capability", force="fact", conversation="b")
    deliberate.deliberate()
    finding = _finding(ada, kriging, "capability")
    assert finding.outcome == Finding.Outcome.CAPABILITY
    assert finding.relation == "can_do"


def test_a_learning_goal_is_not_covered_by_an_interest(ada):
    ci = _concept("causal inference")
    Edge.objects.create(
        user=ada, concept=ci, relation=Relation.INTERESTED_IN, tier="declared"
    )
    _noted(ada, ci, days_ago=15, kind="learning_goal", conversation="a")
    _noted(ada, ci, days_ago=1, kind="learning_goal", conversation="b")
    deliberate.deliberate()
    finding = _finding(ada, ci, "learning_goal")
    assert finding.outcome == Finding.Outcome.SUGGEST
    assert finding.relation == "wants_to_learn"


def test_a_fact_told_to_mylo_is_recorded(ada, imaging, source):
    data = _concept("scanner dataset", Facet.SETTING)
    _noted(
        ada,
        data,
        days_ago=1,
        kind="project_development",
        force="fact",
        subject="project",
        explicit=True,
        project=imaging,
        visibility=Visibility.LAB,
        source=source,
    )
    deliberate.deliberate()
    finding = Finding.objects.get(project=imaging, user__isnull=True)
    assert finding.outcome == Finding.Outcome.RECORD
    assert finding.visibility == Visibility.LAB


def test_an_unresolved_project_fact_is_asked_about(ada):
    data = _concept("scanner dataset", Facet.SETTING)
    _noted(
        ada,
        data,
        days_ago=1,
        kind="project_development",
        force="fact",
        subject="project",
        explicit=True,
    )
    deliberate.deliberate()
    finding = Finding.objects.get(user=ada, project__isnull=True)
    assert finding.outcome == Finding.Outcome.ASK
    assert finding.reason == "attribution_unresolved"


def test_a_dm_about_a_lab_project_stays_with_the_person(ada, imaging):
    data = _concept("scanner dataset", Facet.SETTING)
    _noted(
        ada,
        data,
        days_ago=1,
        kind="project_development",
        force="fact",
        subject="project",
        explicit=True,
        project=imaging,
    )
    deliberate.deliberate()
    finding = Finding.objects.get(project=imaging)
    assert finding.user == ada and finding.visibility == Visibility.PERSONAL
    assert not Finding.objects.filter(project=imaging, user__isnull=True).exists()


def test_a_full_profile_gets_a_swap_candidate_never_an_edit(ada, settings):
    """Acceptance: a finding past the cluster cap becomes a swap, never an edit."""
    from apps.accounts.models import Profile

    areas = [f"area {i}" for i in range(6)]
    clusters = [
        {"id": f"c{i}", "label": f"Theme {i}", "areas": [areas[i]]} for i in range(6)
    ]
    profile, _ = Profile.objects.get_or_create(user=ada)
    profile.interests = {"version": 2, "areas": areas, "clusters": clusters}
    profile.save()
    old = timezone.now() - timedelta(days=200)
    for area in areas:
        edge = Edge.objects.create(
            user=ada,
            concept=_concept(area, Facet.AREA),
            relation=Relation.INTERESTED_IN,
            tier="declared",
            surface=area,
        )
        Edge.objects.filter(pk=edge.pk).update(first_seen=old)
    before = dict(Profile.objects.get(user=ada).interests)
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    from apps.billing import entitlements

    cap = entitlements.cluster_cap(ada)
    deliberate.deliberate()
    finding = _finding(ada, cp)
    assert finding.outcome == Finding.Outcome.SUGGEST
    if cap <= 6:
        assert finding.budget["room_for_cluster"] is False
        assert finding.budget["swap_candidate"]["label"].startswith("Theme")
    assert Profile.objects.get(user=ada).interests == before


def test_a_lapsed_person_is_paused_not_decided(ada):
    Subscription.objects.filter(scope_user=ada).delete()
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    run = deliberate.deliberate()
    assert run.paused == 1
    assert not Finding.objects.exists()
    assert Observation.objects.count() == 2  # kept, untouched


def test_deliberation_is_rerunnable(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    deliberate.deliberate()
    deliberate.deliberate()
    assert Finding.objects.count() == 1


def test_unlinked_observations_are_linked_at_night(ada):
    observation = Observation.objects.create(
        source=Source.objects.create(
            kind=Source.Kind.DISCORD_DM,
            external_id="dm",
            consent_state=Source.Consent.ACTIVE,
        ),
        observed_at=timezone.now(),
        speaker=ada,
        text="Said they want to look into this.",
        subject="self",
        understanding_kind="current_curiosity",
        force="preference",
        place_kind="dm",
        visibility=Visibility.PERSONAL,
        facet="method",
        topic="gaussian processes",
    )
    run = deliberate.deliberate()
    observation.refresh_from_db()
    assert run.linked == 1 and observation.concept is not None


# -- explanation ---------------------------------------------------------------


def test_the_explanation_is_written_from_mylos_notes(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    deliberate.deliberate()
    prompts = []

    def model(system, prompt):
        prompts.append(prompt)
        return json.dumps(
            {
                "explanation": (
                    "You brought up conformal prediction on two days over the last two "
                    "weeks, in direct messages to me, and said you would like to "
                    "look into it."
                )
            }
        )

    run = explain.explain_pending(complete=model)
    finding = _finding(ada, cp)
    assert run.written == 1
    assert finding.explained == Finding.Explained.WRITTEN
    assert "Said they want to look into this topic further." in prompts[0]
    assert "you" in prompts[0]


def test_an_explanation_that_claims_a_change_is_refused(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    deliberate.deliberate()
    run = explain.explain_pending(
        complete=lambda s, p: json.dumps(
            {
                "explanation": (
                    "I updated your profile to include conformal prediction for you."
                )
            }
        )
    )
    assert run.refused == 1
    assert _finding(ada, cp).explained == Finding.Explained.PENDING


def test_without_the_model_the_explanation_waits(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    deliberate.deliberate()

    def down(system, prompt):
        raise ConnectionError("down")

    run = explain.explain_pending(complete=down)
    assert run.unavailable == 1
    assert _finding(ada, cp).explanation == ""


def test_new_evidence_makes_a_written_explanation_stale(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, conversation="a")
    _noted(ada, cp, days_ago=1, conversation="b")
    deliberate.deliberate()
    explain.explain_pending(
        complete=lambda s, p: json.dumps(
            {
                "explanation": (
                    "You brought up conformal prediction on two days in the last "
                    "two weeks."
                )
            }
        )
    )
    _noted(ada, cp, days_ago=0, conversation="c")
    deliberate.deliberate()
    assert _finding(ada, cp).explained == Finding.Explained.PENDING


def test_no_table_here_holds_a_persons_words():
    forbidden = {"quote", "body", "raw_text", "sentence", "verbatim", "message"}
    for model in (ExtractionRun, Finding):
        names = {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}
        assert not names & forbidden, model


# -- found by the sandbox smoke run (EXP-2026-09-013 ISSUES) ----------------------


def test_one_topic_said_as_interest_and_learning_goal_is_one_finding(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, kind="current_curiosity", conversation="a")
    _noted(ada, cp, days_ago=8, kind="learning_goal", conversation="b")
    _noted(ada, cp, days_ago=1, kind="current_curiosity", conversation="c")
    deliberate.deliberate()
    findings = Finding.objects.filter(user=ada, concept=cp)
    assert findings.count() == 1
    finding = findings.get()
    assert finding.understanding_kind == "current_curiosity"
    assert finding.outcome == Finding.Outcome.SUGGEST
    assert finding.facts["kinds"] == {"current_curiosity": 2, "learning_goal": 1}


def test_the_family_kind_follows_the_majority_without_duplicating(ada):
    cp = _concept("conformal prediction")
    _noted(ada, cp, days_ago=15, kind="learning_goal", conversation="a")
    deliberate.deliberate()
    assert (
        Finding.objects.get(user=ada, concept=cp).understanding_kind == "learning_goal"
    )
    _noted(ada, cp, days_ago=3, kind="current_curiosity", conversation="b")
    _noted(ada, cp, days_ago=1, kind="current_curiosity", conversation="c")
    deliberate.deliberate()
    assert Finding.objects.filter(user=ada, concept=cp).count() == 1
    assert (
        Finding.objects.get(user=ada, concept=cp).understanding_kind
        == "current_curiosity"
    )


def test_a_capability_is_never_folded_into_an_interest(ada):
    kriging = _concept("kriging")
    _noted(ada, kriging, days_ago=15, kind="capability", force="fact", conversation="a")
    _noted(ada, kriging, days_ago=1, kind="current_curiosity", conversation="b")
    deliberate.deliberate()
    assert Finding.objects.filter(user=ada, concept=kriging).count() == 2


def test_unresolved_project_chatter_is_not_asked_about(ada):
    data = _concept("centrifuge booking", Facet.SETTING)
    _noted(
        ada,
        data,
        days_ago=15,
        kind="project_development",
        force="possibility",
        subject="project",
        conversation="a",
    )
    _noted(
        ada,
        data,
        days_ago=1,
        kind="project_development",
        force="question",
        subject="project",
        conversation="b",
    )
    deliberate.deliberate()
    finding = Finding.objects.get(user=ada, concept=data)
    assert finding.outcome == Finding.Outcome.IGNORE


def test_a_topic_name_repeated_is_not_a_quote():
    from apps.ambient.extract import quoted_runs

    message = "just a heads up that the Baltic tide dataset for the project arrived"
    naming = "You told me that the Baltic tide dataset for Project A1 is in."
    assert quoted_runs(naming, [message], allowed="Baltic tide dataset") == []
    quoting = "You said just a heads up that the Baltic tide news came."
    assert quoted_runs(quoting, [message], allowed="Baltic tide dataset")


# -- found by EXP-2026-09-013 run 3 (post hoc) ------------------------------------


def test_an_unattributed_self_intent_is_the_persons_interest(ada):
    cp = _concept("contrastive learning")
    _noted(ada, cp, days_ago=15, kind="project_intent", conversation="a")
    _noted(ada, cp, days_ago=8, kind="learning_goal", conversation="b")
    _noted(ada, cp, days_ago=1, kind="project_intent", conversation="c")
    deliberate.deliberate()
    finding = Finding.objects.get(user=ada, concept=cp)
    assert finding.outcome == Finding.Outcome.SUGGEST
    assert finding.understanding_kind == "current_curiosity"
    assert finding.facts["kinds"] == {"project_intent": 2, "learning_goal": 1}


def test_a_project_intent_about_a_project_stays_the_projects(ada, imaging):
    cp = _concept("contrastive learning")
    _noted(
        ada,
        cp,
        days_ago=15,
        kind="project_intent",
        conversation="a",
        project=imaging,
        visibility=Visibility.LAB,
    )
    _noted(
        ada,
        cp,
        days_ago=1,
        kind="project_intent",
        conversation="b",
        project=imaging,
        visibility=Visibility.LAB,
    )
    deliberate.deliberate()
    assert not Finding.objects.filter(user=ada, project__isnull=True).exists()
    assert Finding.objects.get(project=imaging).outcome == Finding.Outcome.PROPOSE


def test_a_colleagues_intent_is_not_folded_into_an_interest(ada):
    cp = _concept("contrastive learning")
    _noted(
        ada,
        cp,
        days_ago=15,
        kind="project_intent",
        subject="colleague",
        conversation="a",
    )
    _noted(
        ada,
        cp,
        days_ago=1,
        kind="project_intent",
        subject="colleague",
        conversation="b",
    )
    deliberate.deliberate()
    assert not Finding.objects.filter(
        user=ada, outcome__in=[Finding.Outcome.SUGGEST, Finding.Outcome.CAPABILITY]
    ).exists()


def test_the_prompt_calls_decided_against_a_rejection():
    assert '"Decided against X" is a' in extract.PROMPT
    assert "rejection, never a decision" in extract.PROMPT


def test_a_rejection_under_another_kind_still_retires_the_interest(ada):
    """EXP-2026-09-013 run 4: "I'd like to try X" twice (an interest), then
    "we decided against X" read as a project development. The rejection
    retires the interest across kinds, and a retired row never counts again."""
    cp = _concept("molecular dynamics")
    _noted(ada, cp, days_ago=15, kind="current_curiosity", conversation="a")
    _noted(ada, cp, days_ago=8, kind="current_curiosity", conversation="b")
    _noted(
        ada,
        cp,
        days_ago=2,
        kind="project_development",
        force="rejection",
        subject="self",
        conversation="c",
    )
    deliberate.deliberate()
    finding = Finding.objects.get(
        user=ada, concept=cp, understanding_kind="current_curiosity"
    )
    assert finding.outcome == Finding.Outcome.IGNORE
    assert finding.reason == "superseded"
    deliberate.deliberate()  # and it stays that way on the next night
    assert Finding.objects.get(pk=finding.pk).reason == "superseded"

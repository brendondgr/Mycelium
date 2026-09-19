"""Plan 06 — the confirmation dialogue.

Consistency edge cases live with deliberation (``test_reasoning.py``); here:
only an explained finding is asked about; covered and declined stay silent
(they never become suggestions); the weekend, the quiet period, the daily cap
and shut-off; a free tier receives nothing; the first answer wins; every
answer and every expiry is a labelled record; replies in words are read by the
model and never guessed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Lab, LabMembership, Profile
from apps.ambient import deliberate, dialogue, evolve, service
from apps.ambient.models import (
    Finding,
    ListeningConsent,
    Observation,
    ObservationFeedback,
    PendingSuggestion,
    Platform,
    ProjectDevelopment,
    Source,
    ValidationRecord,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import DiscordIdentity
from apps.knowledge.models import Concept, Edge, EdgeStatus, Facet, Scope
from apps.knowledge.tests.conftest import embedder  # noqa: F401 - the fake embedder
from apps.knowledge.tests.fakes import FakeEmbedder
from apps.research.models import Project, ProjectMember

WEDNESDAY = timezone.make_aware(datetime(2026, 9, 16, 8, 0))
SATURDAY = timezone.make_aware(datetime(2026, 9, 19, 8, 0))


@pytest.fixture(autouse=True)
def _on(settings, embedder):  # noqa: F811
    settings.AMBIENT_ENABLED = True
    settings.AMBIENT_CONSISTENT_DAYS = 2
    settings.AMBIENT_CONSISTENT_SPAN_DAYS = 5
    settings.AMBIENT_CONSISTENT_CONVERSATIONS = 2
    settings.AMBIENT_QUESTIONS_PER_DAY = 2
    settings.AMBIENT_EXPLORATION_REVIEW_DAYS = 30


def _person(name, snowflake, *, tier=Tier.SPORE, linked=True):
    user = User.objects.create_user(name, f"{name}@example.org", "pw")
    if tier is not None:
        Subscription.objects.create(tier=tier, scope_user=user)
    if linked:
        DiscordIdentity.objects.create(
            user=user,
            discord_user_id=snowflake,
            link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
            state=DiscordIdentity.State.ACTIVE,
        )
    ListeningConsent.objects.create(user=user, platform=Platform.DISCORD, enabled=True)
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.interests = {"version": 2, "areas": ["medical imaging"]}
    profile.save()
    return user


@pytest.fixture
def ada(db):
    return _person("ada", "111")


def _concept(label, facet=Facet.METHOD):
    return Concept.objects.create(
        label=label,
        facet=facet,
        scope=Scope.GLOBAL,
        embedding=FakeEmbedder().vector(label),
    )


def _noted(
    person,
    concept,
    *,
    days_ago,
    now=WEDNESDAY,
    kind="current_curiosity",
    force="preference",
    subject="self",
    conversation,
    explicit=False,
    project=None,
    visibility=Visibility.PERSONAL,
    change="",
):
    source, _ = Source.objects.get_or_create(
        kind=Source.Kind.DISCORD_DM,
        external_id=f"dm-{person.pk}",
        defaults={"consent_state": Source.Consent.ACTIVE},
    )
    return Observation.objects.create(
        source=source,
        external_message_ids=[f"m-{conversation}"],
        observed_at=now - timedelta(days=days_ago),
        speaker=person,
        text="Said they want to look into this further.",
        subject=subject,
        understanding_kind=kind,
        force=force,
        place_kind="dm",
        visibility=visibility,
        facet=concept.facet,
        topic=concept.label,
        concept=concept,
        explicit=explicit,
        project=project,
        change=change,
        conversation_key=conversation,
    )


def _explain_all():
    Finding.objects.exclude(outcome=Finding.Outcome.IGNORE).update(
        explanation="You brought this up on two days in the last two weeks.",
        explained=Finding.Explained.WRITTEN,
    )


def _night(now=WEDNESDAY, *, explain=True):
    deliberate.deliberate(now=now)
    if explain:
        _explain_all()
    evolve.evolve(now=now)
    return dialogue.schedule(now=now)


def _consistent(person, label="conformal prediction", **kwargs):
    concept = _concept(label)
    _noted(person, concept, days_ago=15, conversation=f"{label}-a", **kwargs)
    _noted(person, concept, days_ago=1, conversation=f"{label}-b", **kwargs)
    return concept


# -- scheduling ----------------------------------------------------------------


def test_a_consistent_topic_becomes_one_question_with_the_real_choices(ada):
    concept = _consistent(ada)
    counts = _night()
    assert counts["created"] == 1
    s = PendingSuggestion.objects.get()
    assert (s.kind, s.topic, s.concept_id, s.state) == (
        "interest",
        "conformal prediction",
        concept.pk,
        "pending",
    )
    keys = [c["key"] for c in s.choices]
    assert keys[0] == "reports"
    assert "interests" in keys and "later" in keys and keys[-1] == "no"
    assert "theme" in keys  # a spore profile with one theme has room
    text = dialogue.question_text(s)
    assert "Shall I" in text and "tomorrow" in text
    assert "updated" not in text.casefold()
    assert _night()["created"] == 0  # idempotent: one open question per topic


def test_nothing_unexplained_is_asked(ada):
    _consistent(ada)
    assert _night(explain=False)["created"] == 0


def test_a_covered_topic_is_never_asked(ada):
    concept = _consistent(ada)
    Edge.objects.create(
        user=ada, concept=concept, relation="interested_in", tier="declared"
    )
    assert _night()["created"] == 0


def test_nothing_on_a_weekend(ada):
    concept = _concept("conformal prediction")
    _noted(ada, concept, days_ago=15, now=SATURDAY, conversation="a")
    _noted(ada, concept, days_ago=1, now=SATURDAY, conversation="b")
    counts = _night(now=SATURDAY)
    assert counts["created"] == 0 and counts["skipped"] == {"weekend": 1}


def test_shut_off_and_quiet_mean_nothing(ada):
    _consistent(ada)
    ListeningConsent.objects.filter(user=ada).update(questions_muted=True)
    assert _night()["skipped"] == {"shut_off": 1}
    ListeningConsent.objects.filter(user=ada).update(
        questions_muted=False,
        questions_quiet_until=WEDNESDAY.date() + timedelta(days=3),
    )
    assert _night()["skipped"] == {"quiet": 1}


def test_a_free_tier_or_unlinked_person_receives_nothing(db):
    free = _person("fay", "333", tier=Tier.FREE)
    unlinked = _person("uma", "444", linked=False)
    for person in (free, unlinked):
        _consistent(person, label=f"topic of {person.username}")
    deliberate.deliberate(now=WEDNESDAY)
    _explain_all()
    evolve.evolve(now=WEDNESDAY)
    counts = dialogue.schedule(now=WEDNESDAY)
    assert counts["created"] == 0
    assert counts["skipped"].get("unlinked") == 1


def test_the_daily_cap_asks_the_strongest_first(ada):
    for label in ("alpha method", "beta method", "gamma method"):
        _consistent(ada, label=label)
    deliberate.deliberate(now=WEDNESDAY)
    _explain_all()
    Finding.objects.filter(topic="gamma method").update(influence=9.0)
    evolve.evolve(now=WEDNESDAY)
    counts = dialogue.schedule(now=WEDNESDAY)
    assert counts["created"] == 2 and counts["skipped"] == {"daily_cap": 1}
    assert PendingSuggestion.objects.filter(topic="gamma method").exists()


def test_a_capability_is_asked_as_a_skill(ada):
    concept = _concept("kriging")
    for days, key in ((15, "a"), (1, "b")):
        _noted(
            ada,
            concept,
            days_ago=days,
            kind="capability",
            force="fact",
            conversation=key,
        )
    _night()
    s = PendingSuggestion.objects.get()
    assert s.kind == "skill" and [c["key"] for c in s.choices] == [
        "skill",
        "later",
        "no",
    ]


def test_an_unclear_subject_is_a_clarifying_question(ada):
    concept = _concept("conformal prediction")
    for days, key in ((15, "a"), (1, "b")):
        _noted(ada, concept, days_ago=days, subject="unknown", conversation=key)
    _night()
    s = PendingSuggestion.objects.get()
    assert (s.kind, s.reason) == ("clarify", "subject_unclear")
    ok, line = dialogue.answer(s, choice="self", surface="web", now=WEDNESDAY)
    assert ok and set(Observation.objects.values_list("subject", flat=True)) == {"self"}
    deliberate.deliberate(now=WEDNESDAY)
    assert (
        Finding.objects.get(user=ada, concept=concept).outcome
        == Finding.Outcome.SUGGEST
    )


def test_a_lab_development_is_asked_of_the_managers_and_answered_once(ada):
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    pi = _person("pia", "222")
    LabMembership.objects.create(user=pi, lab=lab, is_lead=True)
    admin = _person("adam", "555")
    LabMembership.objects.create(user=admin, lab=lab, role=LabMembership.Role.ADMIN)
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=ada)
    data = _concept("scanner dataset", Facet.SETTING)
    for days, key in ((15, "a"), (1, "b")):
        _noted(
            ada,
            data,
            days_ago=days,
            kind="project_development",
            force="fact",
            subject="project",
            project=project,
            visibility=Visibility.LAB,
            change="dataset_arrived",
            conversation=key,
        )
    _night()
    asked = PendingSuggestion.objects.filter(kind="development")
    assert set(asked.values_list("user__username", flat=True)) == {"pia", "adam"}
    first = asked.get(user=pi)
    assert dialogue.answer(first, choice="yes", surface="dm", now=WEDNESDAY)[0]
    development = ProjectDevelopment.objects.get()
    assert development.status == "confirmed" and development.decided_by == pi
    assert asked.get(user=admin).state == "withdrawn"


def test_an_exploration_due_for_review_is_asked_keep_or_let_go(ada):
    concept = _consistent(ada)
    _night()
    s = PendingSuggestion.objects.get()
    dialogue.answer(s, choice="reports", surface="web", now=WEDNESDAY)
    later = WEDNESDAY + timedelta(days=35)
    counts = dialogue.schedule(now=later)
    review = PendingSuggestion.objects.get(kind="review")
    assert counts["created"] == 1 and review.concept_id == concept.pk
    dialogue.answer(review, choice="drop", surface="web", now=later)
    assert Edge.objects.get(user=ada, tier="conversational").status == EdgeStatus.FADED


# -- answering -----------------------------------------------------------------


def test_include_it_in_my_reports_confirms_an_exploration(ada):
    concept = _consistent(ada)
    _night()
    s = PendingSuggestion.objects.get()
    ok, line = dialogue.answer(s, choice="reports", surface="dm", now=WEDNESDAY)
    assert ok and "tomorrow morning's run" in line
    edge = Edge.objects.get(user=ada, concept=concept, tier="conversational")
    assert edge.status == EdgeStatus.ACTIVE
    assert edge.review_on == (WEDNESDAY + timedelta(days=30)).date()
    s.refresh_from_db()
    assert s.applied_at is not None and s.verdict == "confirmed"
    record = ValidationRecord.objects.get()
    assert (record.verdict, record.choice, record.surface) == (
        "confirmed",
        "reports",
        "dm",
    )
    assert record.finding_snapshot["outcome"] == "suggest"
    assert ObservationFeedback.objects.filter(verdict="confirmed").count() == 2


def test_the_first_answer_wins(ada):
    _consistent(ada)
    _night()
    s = PendingSuggestion.objects.get()
    assert dialogue.answer(s, choice="reports", surface="web", now=WEDNESDAY)[0]
    taken, line = dialogue.answer(s, choice="no", surface="dm", now=WEDNESDAY)
    assert not taken and "already answered on the web" in line
    assert ValidationRecord.objects.count() == 1


def test_no_rejects_and_the_topic_rests(ada):
    concept = _consistent(ada)
    _night()
    dialogue.answer(
        PendingSuggestion.objects.get(), choice="no", surface="dm", now=WEDNESDAY
    )
    assert Edge.objects.get(user=ada, concept=concept).status == EdgeStatus.REJECTED
    _noted(ada, concept, days_ago=0, conversation="again")
    assert _night(now=WEDNESDAY + timedelta(days=7))["created"] == 0
    assert ObservationFeedback.objects.filter(verdict="rejected").count() == 2


def test_not_now_changes_nothing_for_a_month(ada):
    concept = _consistent(ada)
    _night()
    dialogue.answer(
        PendingSuggestion.objects.get(), choice="later", surface="web", now=WEDNESDAY
    )
    assert Edge.objects.get(user=ada, concept=concept).status == EdgeStatus.PENDING
    assert _night(now=WEDNESDAY + timedelta(days=7))["skipped"].get("deferred") == 1


def test_its_for_a_project_places_it_there(ada):
    lab = Lab.objects.create(name="PULSE", slug="pulse")
    project = Project.objects.create(name="Imaging pipeline", scope_lab=lab)
    ProjectMember.objects.create(project=project, user=ada)
    concept = _consistent(ada)
    _night()
    s = PendingSuggestion.objects.get()
    choice = f"project:{project.pk}"
    assert choice in [c["key"] for c in s.choices]
    dialogue.answer(s, choice=choice, surface="web", now=WEDNESDAY)
    assert Edge.objects.get(user=ada, concept=concept).status == EdgeStatus.REJECTED
    development = ProjectDevelopment.objects.get()
    assert development.project == project and development.status == "confirmed"
    assert development.visibility == "personal"


def test_a_choice_that_is_not_offered_is_refused(ada):
    _consistent(ada)
    _night()
    taken, line = dialogue.answer(
        PendingSuggestion.objects.get(), choice="drop", surface="web", now=WEDNESDAY
    )
    assert not taken and "isn't one of the choices" in line


def test_a_question_nobody_answers_expires_as_ignored(ada):
    _consistent(ada)
    _night()
    assert dialogue.expire(now=WEDNESDAY + timedelta(days=15)) == 1
    assert PendingSuggestion.objects.get().state == "expired"
    assert ValidationRecord.objects.get().verdict == "ignored"
    assert ObservationFeedback.objects.filter(verdict="ignored").count() == 2


# -- the conversation ----------------------------------------------------------


def _asked(user):
    _consistent(user)
    _night()
    PendingSuggestion.objects.update(state="asked", asked_at=WEDNESDAY)
    return PendingSuggestion.objects.get()


def test_a_reply_in_words_is_read_by_the_model(ada):
    s = _asked(ada)

    def model(system, prompt):
        assert "yeah go for it" in prompt
        return json.dumps(
            {"verdict": "confirmed", "choice": "reports", "correction": ""}
        )

    line = dialogue.turn(ada, "yeah go for it", complete=model, now=WEDNESDAY)
    assert "reports" in line
    s.refresh_from_db()
    assert s.state == "answered" and s.choice == "reports" and s.answered_on == "dm"


def test_a_reply_that_is_a_choice_needs_no_model(ada):
    _asked(ada)

    def model(system, prompt):
        raise AssertionError("not needed")

    line = dialogue.turn(
        ada, "2", complete=model, now=WEDNESDAY
    )  # "Add it to my interests"
    assert "interests" in line
    assert PendingSuggestion.objects.get().choice == "interests"


def test_without_the_model_nothing_is_guessed(ada):
    s = _asked(ada)

    def down(system, prompt):
        raise ConnectionError("down")

    line = dialogue.turn(ada, "hmm maybe", complete=down, now=WEDNESDAY)
    assert "couldn't read that" in line and "Nothing has changed" in line
    s.refresh_from_db()
    assert s.state == "asked"


def test_unclear_gets_one_more_turn_then_a_graceful_close(ada):
    s = _asked(ada)

    def unclear(system, prompt):
        return json.dumps({"verdict": "unclear", "choice": "", "correction": ""})

    assert "didn't follow" in dialogue.turn(
        ada, "what?", complete=unclear, now=WEDNESDAY
    )
    assert "didn't follow" in dialogue.turn(ada, "eh", complete=unclear, now=WEDNESDAY)
    close = dialogue.turn(ada, "dunno", complete=unclear, now=WEDNESDAY)
    assert "leave" in close
    s.refresh_from_db()
    assert (s.state, s.verdict) == ("answered", "unclear")
    assert (
        Edge.objects.get(user=ada, tier="conversational").status == EdgeStatus.PENDING
    )


def test_a_correction_is_the_persons_own_word(ada):
    _asked(ada)

    def model(system, prompt):
        return json.dumps(
            {
                "verdict": "corrected",
                "choice": "reports",
                "correction": "conformal inference",
            }
        )

    dialogue.turn(
        ada, "yes but call it conformal inference", complete=model, now=WEDNESDAY
    )
    edge = Edge.objects.get(user=ada, tier="conversational")
    assert edge.surface == "conformal inference" and edge.edited_by_person
    assert edge.status == EdgeStatus.ACTIVE
    assert ValidationRecord.objects.get().correction == "conformal inference"


def test_ordinary_conversation_gets_no_dialogue_reply(ada):
    assert dialogue.turn(ada, "the loader is flaky again", now=WEDNESDAY) is None


@pytest.mark.parametrize(
    "phrase", ["please stop asking", "shut it off", "no more questions, thanks"]
)
def test_shut_off_works_in_any_conversation_and_withdraws_open_questions(ada, phrase):
    s = _asked(ada)
    line = dialogue.turn(ada, phrase, now=WEDNESDAY)
    assert "no more questions" in line
    consent = ListeningConsent.objects.get(user=ada)
    assert consent.questions_muted and consent.enabled  # listening is separate
    s.refresh_from_db()
    assert s.state == "withdrawn"
    assert dialogue.askable(ada, now=WEDNESDAY) == (False, "shut_off")


def test_stop_listening_too_and_start_again(ada):
    dialogue.turn(ada, "stop listening to me please", now=WEDNESDAY)
    consent = ListeningConsent.objects.get(user=ada)
    assert consent.questions_muted and not consent.enabled
    dialogue.turn(ada, "you can ask me again", now=WEDNESDAY)
    consent.refresh_from_db()
    assert not consent.questions_muted


def test_a_reply_to_an_answered_question_says_where(ada):
    from apps.integrations.models import DiscordOutboxMessage

    s = _asked(ada)
    DiscordOutboxMessage.objects.create(
        dedupe_key="q",
        kind="ambient_question",
        target_type="dm",
        recipient_user=ada,
        subject_type="ambient_suggestion",
        subject_id=str(s.pk),
        discord_message_id="999",
        next_attempt_at=WEDNESDAY,
    )
    dialogue.answer(s, choice="reports", surface="web", now=WEDNESDAY)
    assert "already answered on the web" in dialogue.turn(
        ada, "yes", reply_to="999", now=WEDNESDAY
    )


# -- the gateway door and the web ----------------------------------------------


def test_a_button_is_only_the_askeds_to_press(ada):
    s = _asked(ada)
    _person("bo", "222")
    assert "isn't yours" in service.answer_button("222", str(s.pk), "reports")
    assert "reports" in service.answer_button("111", str(s.pk), "reports")


def test_the_web_lists_and_answers_my_questions(ada, client):
    s = _asked(ada)
    client.force_login(ada)
    listed = client.get("/api/ambient/suggestions/").json()["suggestions"]
    assert [row["id"] for row in listed] == [s.pk]
    assert listed[0]["choices"][0]["key"] == "reports"
    answered = client.post(
        f"/api/ambient/suggestions/{s.pk}/answer/",
        {"choice": "reports"},
        content_type="application/json",
    )
    assert answered.status_code == 200 and answered.json()["taken"]
    again = client.post(
        f"/api/ambient/suggestions/{s.pk}/answer/",
        {"choice": "no"},
        content_type="application/json",
    )
    assert again.status_code == 409


def test_nobody_else_can_answer_my_question_on_the_web(ada, client):
    s = _asked(ada)
    bo = _person("bo", "222")
    client.force_login(bo)
    response = client.post(
        f"/api/ambient/suggestions/{s.pk}/answer/",
        {"choice": "reports"},
        content_type="application/json",
    )
    assert response.status_code == 404


# -- found by EXP-2026-09-015 -------------------------------------------------


def test_a_model_that_says_yes_while_picking_no_records_a_no(ada):
    concept = _consistent(ada)
    _night()
    PendingSuggestion.objects.update(state="asked", asked_at=WEDNESDAY)

    def contradictory(system, prompt):
        return json.dumps({"verdict": "confirmed", "choice": "no", "correction": ""})

    dialogue.turn(ada, "nah, I'm good", complete=contradictory, now=WEDNESDAY)
    s = PendingSuggestion.objects.get()
    assert s.verdict == "rejected"
    assert Edge.objects.get(user=ada, concept=concept).status == EdgeStatus.REJECTED


def test_no_caller_can_make_a_chosen_no_a_yes(ada):
    concept = _consistent(ada)
    _night()
    s = PendingSuggestion.objects.get()
    dialogue.answer(s, choice="no", verdict="confirmed", surface="web", now=WEDNESDAY)
    s.refresh_from_db()
    assert s.verdict == "rejected"
    assert Edge.objects.get(user=ada, concept=concept).status == EdgeStatus.REJECTED


def test_stop_asking_in_other_words_is_read_by_the_model(ada):
    def model(system, prompt):
        assert "chill with the questions" in prompt
        return json.dumps({"intent": "stop_questions"})

    line = dialogue.turn(
        ada,
        "could you chill with the questions for a bit?",
        complete=model,
        now=WEDNESDAY,
    )  # noqa: E501
    assert "no more questions" in line
    assert ListeningConsent.objects.get(user=ada).questions_muted


def test_a_message_without_any_such_words_never_reaches_the_control_reader(ada):
    def model(system, prompt):
        raise AssertionError("not sent to the model")

    assert (
        dialogue.turn(
            ada, "the loader is flaky again today", complete=model, now=WEDNESDAY
        )
        is None
    )  # noqa: E501


def test_stop_asking_about_this_one_is_an_answer_not_a_setting(ada):
    _asked(ada)

    def model(system, prompt):
        if "Which choice did they pick" in prompt:
            return json.dumps({"choice": "no", "correction": ""})
        raise AssertionError("an answer, so no control reading")

    line = dialogue.turn(
        ada, "Nah, you can stop asking about it!", complete=model, now=WEDNESDAY
    )  # noqa: E501
    assert "won't ask about" in line
    assert not ListeningConsent.objects.get(user=ada).questions_muted


def test_an_unclear_reply_that_is_a_general_request_shuts_off(ada):
    s = _asked(ada)

    def model(system, prompt):
        if "Which choice did they pick" in prompt:
            return json.dumps({"choice": "unclear", "correction": ""})
        return json.dumps({"intent": "stop_questions"})

    line = dialogue.turn(
        ada, "honestly, enough with all these questions", complete=model, now=WEDNESDAY
    )  # noqa: E501
    assert "no more questions" in line
    s.refresh_from_db()
    assert s.state == "withdrawn"


def test_a_correction_that_only_repeats_a_choice_is_not_a_new_name(ada):
    s = _asked(ada)

    def model(system, prompt):
        return json.dumps(
            {"choice": "reports", "correction": "Include it in my reports"}
        )

    dialogue.turn(ada, "yes, include it in my reports", complete=model, now=WEDNESDAY)
    s.refresh_from_db()
    assert s.verdict == "confirmed" and s.correction == ""


@pytest.mark.parametrize(
    "text",
    [
        "the sensor might have shut off mid-experiment",
        "I shut off the centrifuge before leaving",
    ],
)
def test_shut_off_in_passing_is_not_the_switch(text):
    assert dialogue.shut_off_request(text) is None


def test_the_switch_itself_still_is():
    for text in ("shut it off", "shut off the questions", "no more questions"):
        assert dialogue.shut_off_request(text) == "off"


@pytest.mark.parametrize(
    ("correction", "echo"),
    [
        ("Include it in my reports", True),
        ("RL", False),
        ("graph neural networks", False),
    ],
)
def test_what_counts_as_repeating_a_choice(correction, echo):
    choices = [
        {"key": "reports", "label": "Include it in my reports"},
        {"key": "no", "label": "No, not really"},
    ]
    assert dialogue._echoes_a_choice(correction, choices) is echo


def test_a_bare_stop_asking_while_answering_is_the_answer(ada):
    """EXP-2026-09-015 run 4: "not really interested right now, so you can stop
    asking" muted every question and left this one unanswered."""
    s = _asked(ada)

    def model(system, prompt):
        if "Which choice did they pick" in prompt:
            return json.dumps({"choice": "no", "correction": ""})
        raise AssertionError("an answer, so no control reading")

    line = dialogue.turn(
        ada,
        "not really interested right now, so you can stop asking.",
        complete=model,
        now=WEDNESDAY,
    )
    assert "won't ask about" in line
    s.refresh_from_db()
    assert s.state == "answered" and s.verdict == "rejected"
    assert not ListeningConsent.objects.get(user=ada).questions_muted


def test_no_more_questions_while_answering_is_still_the_switch(ada):
    _asked(ada)

    def model(system, prompt):
        raise AssertionError("the literal switch needs no model")

    line = dialogue.turn(
        ada, "no, and no more questions please", complete=model, now=WEDNESDAY
    )
    assert "no more questions" in line
    assert ListeningConsent.objects.get(user=ada).questions_muted


def test_a_bare_stop_asking_with_nothing_open_is_the_switch(ada):
    ListeningConsent.objects.get_or_create(user=ada, platform="discord")
    line = dialogue.turn(ada, "you can stop asking", now=WEDNESDAY)
    assert "no more questions" in line


@pytest.mark.parametrize(
    ("text", "more"),
    [
        ("please stop asking", False),
        ("ok just stop asking now, thanks", False),
        ("not really interested right now, so you can stop asking.", True),
        ("nah, not for me, don't ask me", True),
    ],
)
def test_what_says_more_than_stop(text, more):
    assert dialogue._says_more_than_stop(text) is more

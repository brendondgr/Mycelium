"""Plan 10 — the measures and the harm checks.

Each harm check is shown to be zero on a clean record and to catch the one
violation it exists for. Validation precision is checked by hand on a small
set of answers.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.ambient import evaluation
from apps.ambient.models import (
    AppliedChange,
    Finding,
    Observation,
    PendingSuggestion,
    Retraction,
    Source,
    ValidationRecord,
    Visibility,
)
from apps.billing.models import Subscription, Tier
from apps.integrations.models import DiscordIdentity
from apps.knowledge.models import Concept, Edge, Facet, Scope

NOW = timezone.now()


@pytest.fixture
def ada(db):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    Subscription.objects.create(tier=Tier.SPORE, scope_user=user)
    DiscordIdentity.objects.create(
        user=user,
        discord_user_id="111",
        link_method=DiscordIdentity.LinkMethod.ACTIVATION_CODE,
        state=DiscordIdentity.State.ACTIVE,
    )
    return user


@pytest.fixture
def source(db):
    return Source.objects.create(
        kind=Source.Kind.DISCORD_DM,
        external_id="dm-1",
        consent_state=Source.Consent.ACTIVE,
    )


def _observation(user, source, **fields):
    defaults = {
        "external_message_ids": ["m1"],
        "observed_at": NOW - timedelta(days=1),
        "text": "Said they want to try conformal prediction on the imaging data.",
        "subject": "self",
        "understanding_kind": "current_curiosity",
        "force": "preference",
        "place_kind": "dm",
        "visibility": Visibility.PERSONAL,
        "topic": "conformal prediction",
    }
    return Observation.objects.create(
        source=source, speaker=user, **{**defaults, **fields}
    )


def _concept(label="conformal prediction"):
    return Concept.objects.create(label=label, facet=Facet.METHOD, scope=Scope.GLOBAL)


def _suggestion(user, concept=None, **fields):
    defaults = {
        "kind": "interest",
        "topic": concept.label if concept else "conformal prediction",
        "relation": "interested_in",
        "expires_at": NOW + timedelta(days=14),
    }
    return PendingSuggestion.objects.create(
        user=user, concept=concept, **{**defaults, **fields}
    )


def _answered(user, verdict, *, concept=None, choice="reports", **fields):
    return _suggestion(
        user,
        concept,
        state="answered",
        verdict=verdict,
        choice=choice,
        asked_at=NOW - timedelta(days=2),
        answered_at=NOW - timedelta(days=1),
        answered_on="dm",
        **fields,
    )


def _harms(**kwargs):
    return evaluation.harm_checks(lab_reports=kwargs.get("lab_reports", []))


# -- clean ---------------------------------------------------------------------


def test_a_clean_record_has_no_harm(ada, source):
    concept = _concept()
    _observation(ada, source, concept=concept)
    yes = _answered(ada, "confirmed", concept=concept)
    AppliedChange.objects.create(
        user=ada, kind="exploration_confirmed", topic="x", suggestion=yes
    )
    AppliedChange.objects.create(
        user=ada, kind="development_recorded", topic="y", surface="told"
    )
    AppliedChange.objects.create(
        user=ada, kind="exploration_confirmed", topic="z", surface="web"
    )
    result = _harms()
    assert result["_total"] == 0, {k: v for k, v in result.items() if k[0] != "_"}


# -- each harm, caught ---------------------------------------------------------


def test_a_profile_edit_with_no_yes_is_caught(ada):
    AppliedChange.objects.create(
        user=ada, kind="profile_edit", topic="kriging", field="interests.skills"
    )
    no = _answered(ada, "rejected", choice="no")
    AppliedChange.objects.create(
        user=ada,
        kind="profile_edit",
        topic="x",
        field="interests.skills",
        suggestion=no,
    )
    assert _harms()["stated_field_without_a_yes"]["count"] == 2


def test_a_state_edit_with_no_accepted_proposal_is_caught(ada):
    AppliedChange.objects.create(
        user=ada, kind="state_edit", topic="annotation budget", field="slow.blockers"
    )
    assert _harms()["stated_field_without_a_yes"]["count"] == 1
    AppliedChange.objects.update(proposal_id="p-1")
    assert _harms()["stated_field_without_a_yes"]["count"] == 0


def test_a_change_with_no_confirmation_is_caught(ada):
    AppliedChange.objects.create(
        user=ada, kind="understanding_confirmed", topic="kriging", surface="dm"
    )
    assert _harms()["change_without_a_confirmation"]["count"] == 1


def test_a_personal_row_in_a_lab_report_is_caught(ada):
    AppliedChange.objects.create(
        user=ada, kind="profile_edit", topic="clinical research", field="x"
    )
    body = "## What changed\n### Projects\n- **clinical research** — added. [O1]"
    assert _harms(lab_reports=[(1, body)])["personal_in_lab_reports"]["count"] == 1
    clean = "## What changed\n### Projects\n- **P** — milestone — Bo told Mylo. [O1]"
    assert _harms(lab_reports=[(1, clean)])["personal_in_lab_reports"]["count"] == 0


def test_the_lab_report_check_says_when_it_did_not_run(ada):
    result = evaluation.harm_checks(lab_reports=None)
    assert result["personal_in_lab_reports"]["not_run"] is True
    assert result["_total"] == 0


def test_too_many_questions_in_a_day_is_caught(ada, settings):
    settings.AMBIENT_QUESTIONS_PER_DAY = 2
    for n in range(3):
        _suggestion(ada, topic=f"t{n}", asked_at=NOW, state="asked")
    assert _harms()["questions_over_the_daily_cap"]["count"] == 1


def test_a_quotation_in_the_record_is_caught(ada, source):
    _observation(
        ada,
        source,
        text='Said "we should really try conformal prediction on the scans" today.',
    )
    assert _harms()["quoted_words_outside_the_buffer"]["count"] == 1


def test_a_short_quoted_term_is_not_a_quotation(ada, source):
    _observation(ada, source, text='Mentioned "SAM" and "U-Net" as baselines.')
    assert _harms()["quoted_words_outside_the_buffer"]["count"] == 0


def test_an_observation_surviving_an_opt_out_is_caught(ada, source):
    _observation(ada, source)
    Retraction.objects.create(reason=Retraction.Reason.OPT_OUT, user=ada)
    assert _harms()["observations_after_opt_out"]["count"] == 1


def test_an_observation_of_an_unlinked_person_is_caught(db, source):
    stranger = User.objects.create_user("zed", "zed@example.org", "pw")
    _observation(stranger, source)
    assert _harms()["observations_of_unlinked_people"]["count"] == 1


def test_a_lapsed_person_is_counted_not_flagged(ada, source):
    _observation(ada, source)
    Subscription.objects.filter(scope_user=ada).update(tier=Tier.FREE)
    result = _harms()
    assert result["_info"]["free_tier_speakers_paused"]["count"] == 1
    assert result["_total"] == 0


def test_a_declined_topic_asked_again_inside_30_days_is_caught(ada):
    concept = _concept()
    _answered(ada, "rejected", concept=concept, choice="no")
    _suggestion(ada, concept, asked_at=NOW + timedelta(days=5), state="asked")
    assert _harms()["declined_asked_again_within_30_days"]["count"] == 1


def test_a_declined_topic_after_the_rest_is_fine(ada):
    concept = _concept()
    _answered(ada, "rejected", concept=concept, choice="no")
    _suggestion(ada, concept, asked_at=NOW + timedelta(days=31), state="asked")
    assert _harms()["declined_asked_again_within_30_days"]["count"] == 0


def test_a_covered_topic_asked_is_caught(ada):
    concept = _concept()
    Edge.objects.create(
        user=ada, concept=concept, relation="interested_in", tier="declared"
    )
    _suggestion(ada, concept, asked_at=NOW + timedelta(minutes=1), state="asked")
    assert _harms()["covered_topic_asked"]["count"] == 1


def test_a_rule_written_observation_is_caught(ada, source):
    _observation(ada, source, origin="rule")
    assert _harms()["rule_written_observations"]["count"] == 1


# -- measures ------------------------------------------------------------------


def _record(user, verdict, *, kind="current_curiosity", surface="dm", suggestion=None):
    return ValidationRecord.objects.create(
        user=user,
        suggestion=suggestion,
        kind="interest",
        understanding_kind=kind,
        topic="t",
        surface=surface,
        verdict=verdict,
    )


def test_validation_precision_by_kind_and_surface(ada, source):
    concept = _concept()
    obs = _observation(ada, source, concept=concept, force="plan", place_kind="channel")
    finding = Finding.objects.create(
        user=ada,
        concept=concept,
        topic="conformal prediction",
        understanding_kind="current_curiosity",
        relation="interested_in",
        visibility="personal",
        outcome="suggest",
        reason="consistent",
        observation_ids=[obs.pk],
        decided_at=NOW,
    )
    s = _suggestion(ada, concept, finding=finding)
    _record(ada, "confirmed", suggestion=s)
    _record(ada, "corrected", suggestion=s, surface="web")
    _record(ada, "rejected", kind="enduring_interest")
    _record(ada, "defer")
    result = evaluation.validation_precision()
    assert result["precision"] == round(2 / 3, 4)
    assert result["by"]["kind"]["current_curiosity"]["precision"] == 1.0
    assert result["by"]["kind"]["enduring_interest"]["precision"] == 0.0
    assert result["by"]["surface"]["web"]["yes"] == 1
    assert result["by"]["force"]["plan"]["yes"] == 2
    assert result["by"]["heard_in"]["channel"]["yes"] == 2
    assert result["verdicts"]["defer"] == 1


def test_maintenance_counts_edits_questions_and_undos(ada):
    yes = _answered(ada, "confirmed", choice="skill")
    AppliedChange.objects.create(
        user=ada, kind="profile_edit", topic="k", suggestion=yes, undone_at=NOW
    )
    AppliedChange.objects.create(
        user=ada, kind="exploration_confirmed", topic="e", surface="web"
    )
    result = evaluation.maintenance(
        since=NOW - timedelta(days=30), until=NOW + timedelta(minutes=1)
    )
    assert result["profile_edits"] == 1 and result["people_with_edits"] == 1
    assert result["questions_asked"] == 1 and result["questions_answered"] == 1
    assert result["undo_rate"] == 0.5


def test_nothing_in_the_report_is_text(ada, source):
    """Counts and ids only: no observation text reaches the report."""
    import json

    _observation(ada, source, text="A very particular sentence about kriging.")
    text = json.dumps(evaluation.report(lab_reports=[]), default=str)
    assert "particular sentence" not in text


# -- the dataset export ------------------------------------------------------------


def test_the_export_hashes_people_and_carries_no_typed_words(ada, source, tmp_path):
    import json
    from io import StringIO

    from django.core.management import call_command

    s = _answered(ada, "corrected", correction="my own private wording")
    ValidationRecord.objects.create(
        user=ada,
        suggestion=s,
        kind="interest",
        topic="conformal prediction",
        explanation="You brought this up on two days.",
        surface="dm",
        verdict="corrected",
        choice="reports",
        correction="my own private wording",
        finding_snapshot={"user": ada.pk, "reason": "consistent"},
    )
    call_command(
        "export_ambient_dataset",
        salt="pepper-123",
        out=str(tmp_path),
        stdout=StringIO(),
    )
    [answer] = [
        json.loads(line)
        for line in (tmp_path / "answers.jsonl").read_text().splitlines()
    ]
    text = (tmp_path / "answers.jsonl").read_text()
    assert "my own private wording" not in text
    assert answer["renamed"] is True and answer["person"] != str(ada.pk)
    assert "user" not in answer["finding"]
    assert len(answer["person"]) == 16
    # The same person hashes the same way within one salt, differently in another.
    call_command(
        "export_ambient_dataset",
        salt="pepper-456",
        out=str(tmp_path / "b"),
        stdout=StringIO(),
    )
    other = json.loads((tmp_path / "b" / "answers.jsonl").read_text().splitlines()[0])
    assert other["person"] != answer["person"]


def test_the_export_refuses_a_short_salt(tmp_path, db):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("export_ambient_dataset", salt="x", out=str(tmp_path))

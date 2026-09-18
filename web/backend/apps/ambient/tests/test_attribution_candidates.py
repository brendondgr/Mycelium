"""Who the candidates are: only projects the speaker is on, plus shared lab ones.

The hard filter matters more than any score. A DM must never attribute to a
project the speaker is not on, and a personal project belongs to its owner.
"""

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import Lab
from apps.ambient.attribution import candidates_for
from apps.ambient.models import Source
from apps.research.models import Project, ProjectMember, ProjectState


@pytest.fixture
def lab(db) -> Lab:
    return Lab.objects.create(name="PULSE", slug="pulse")


@pytest.fixture
def guild(lab) -> Source:
    return Source.objects.create(
        kind=Source.Kind.DISCORD_GUILD,
        external_id="g",
        lab=lab,
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def dm(db) -> Source:
    return Source.objects.create(
        kind=Source.Kind.DISCORD_DM,
        external_id="u",
        consent_state=Source.Consent.ACTIVE,
    )


@pytest.fixture
def ada(db) -> User:
    return User.objects.create_user("ada", "ada@example.org", "pw")


def _ids(candidates):
    return {candidate.name for candidate in candidates}


def test_personal_and_member_projects_are_candidates(ada, lab, guild):
    Project.objects.create(name="Mine", scope_user=ada)
    on = Project.objects.create(name="On it", scope_lab=lab)
    ProjectMember.objects.create(project=on, user=ada)
    Project.objects.create(name="Not on it", scope_lab=lab)

    assert _ids(candidates_for(ada, guild, place_kind="channel")) == {"Mine", "On it"}


def test_a_lab_channel_adds_the_labs_shared_projects(ada, lab, guild):
    Project.objects.create(name="Shared", scope_lab=lab, share_in_lab_reports=True)
    assert "Shared" in _ids(candidates_for(ada, guild, place_kind="channel"))


def test_a_dm_never_attributes_to_a_project_the_speaker_is_not_on(ada, lab, dm):
    Project.objects.create(name="Shared", scope_lab=lab, share_in_lab_reports=True)
    Project.objects.create(name="Mine", scope_user=ada)
    assert _ids(candidates_for(ada, dm, place_kind="dm")) == {"Mine"}


def test_another_labs_shared_project_is_never_a_candidate(ada, guild):
    other = Lab.objects.create(name="Elsewhere", slug="elsewhere")
    Project.objects.create(name="Theirs", scope_lab=other, share_in_lab_reports=True)
    assert "Theirs" not in _ids(candidates_for(ada, guild, place_kind="channel"))


def test_somebody_elses_personal_project_is_never_a_candidate(ada, guild):
    bo = User.objects.create_user("bo", "bo@example.org", "pw")
    Project.objects.create(name="Bo's", scope_user=bo)
    assert _ids(candidates_for(ada, guild, place_kind="channel")) == set()


def test_archived_projects_are_not_candidates(ada, guild):
    Project.objects.create(name="Old", scope_user=ada, is_archived=True)
    assert _ids(candidates_for(ada, guild, place_kind="channel")) == set()


def test_a_candidate_carries_aliases_entities_and_members(ada, lab, guild):
    project = Project.objects.create(
        name="Imaging pipeline", scope_lab=lab, aliases=["IMG-seg", "  "]
    )
    ProjectMember.objects.create(project=project, user=ada)
    ProjectState.objects.create(
        project=project,
        slow={
            "problem": "segmenting tumours",
            "data": ["BraTS 2021", "tiny"],
            "method": ["conformal prediction"],
        },
        fast={
            "venue_targets": [{"venue": "MICCAI"}],
            "milestones": [{"what": "results on BraTS", "date": ""}],
        },
    )
    (candidate,) = candidates_for(ada, guild, place_kind="channel")
    assert candidate.aliases == ("IMG-seg",)
    assert "BraTS 2021" in candidate.entities
    assert "MICCAI" in candidate.entities
    assert "results on BraTS" in candidate.entities
    assert "tiny" not in candidate.entities  # too short to be distinctive
    assert ada.pk in candidate.member_ids
    assert "segmenting tumours" in candidate.slow_text


def test_a_personal_projects_owner_is_a_member(ada, guild):
    Project.objects.create(name="Mine", scope_user=ada)
    (candidate,) = candidates_for(ada, guild, place_kind="channel")
    assert ada.pk in candidate.member_ids

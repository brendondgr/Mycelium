"""A project's state: its shape, its provenance, and who may read or change it.

``Project.goals`` promised methods, datasets and deadlines and delivered a display
blob. This is the shape that actually holds them, and the contract around it:

* the **slow/fast split** exists so that editing a milestone does not re-bill the
  model for every write-up on the project, and the fingerprint is what enforces it;
* **provenance** exists so a reader can tell what they said from what Mylo guessed,
  and a stated field is never auto-edited;
* the **read is wider than the write**, and both are narrower than the lab.

Project state is the most sensitive thing Mycelium stores — unpublished plans and
what is not working — so the permission assertions here are load-bearing, not
housekeeping.
"""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Lab, LabMembership, WatchPreference
from apps.content.timeline_settings import (
    SOURCE_LAB,
    SOURCE_PROJECT,
    SOURCE_SYSTEM,
    SOURCE_USER,
    effective_timeline,
)
from apps.research import state as schema
from apps.research.models import Project, ProjectMember, ProjectState


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner(db) -> User:
    return User.objects.create_user(username="owner", password="p")


@pytest.fixture
def project(owner: User) -> Project:
    return Project.objects.create(name="Synapse", scope_user=owner)


SAMPLE = {
    "slow": {
        "problem": "Whether multi-hop QA benchmarks detect KG quality at all",
        "claimed_contribution": "A measurement-validity study",
        "method": [
            "multi-lens LLM extraction",
            "  schema settling  ",
            "schema settling",
        ],
        "data": ["MuSiQue", "HotpotQA"],
        "blockers": [{"text": "No labeled evaluation set"}, "Single unblinded rater"],
    },
    "fast": {
        "stage": "experiments",
        "milestones": [
            {"kind": "results_by", "what": "MuSiQue pilot", "date": "2026-10-09"},
            {"kind": "nonsense", "what": "draft", "date": "end of year"},
        ],
        "venue_targets": ["TMLR", {"venue": "CIKM 2027", "slot": "2027-05-16"}],
        "timeline_overrides": {"deadline_buffer_days": 21},
    },
}


# --------------------------------------------------------------------------- #
# The shape
# --------------------------------------------------------------------------- #
def test_normalising_cleans_without_rejecting() -> None:
    """Written by a wizard, an extractor and an API — all partial answers.

    A schema that 400s on an extra key turns a partial answer into no answer.
    """
    out = schema.normalise_state({**SAMPLE, "slow": {**SAMPLE["slow"], "junk": 1}})

    assert "junk" not in out["slow"]
    # Deduped and trimmed, order preserved.
    assert out["slow"]["method"] == ["multi-lens LLM extraction", "schema settling"]
    # A bare string is promoted to a record, and ids are minted positionally so a
    # round-trip through the API does not renumber what alerts point at.
    assert [b["id"] for b in out["slow"]["blockers"]] == ["b1", "b2"]
    assert out["slow"]["blockers"][1]["text"] == "Single unblinded rater"


def test_an_undatable_milestone_keeps_no_date_rather_than_a_guess() -> None:
    """"end of year" is not a date, and the timeline matcher would rather know."""
    out = schema.normalise_state(SAMPLE)
    milestones = out["fast"]["milestones"]

    assert milestones[0]["date"] == "2026-10-09"
    assert milestones[1]["date"] == ""
    # An unknown kind degrades to "other" rather than failing the whole save.
    assert milestones[1]["kind"] == "other"


def test_a_bare_venue_name_is_as_valid_as_a_dated_slot() -> None:
    """Forcing the first shape into the second would mean inventing a date."""
    targets = schema.normalise_state(SAMPLE)["fast"]["venue_targets"]

    assert targets[0] == {"venue": "TMLR", "slot": "", "fallback": ""}
    assert targets[1]["slot"] == "2027-05-16"


def test_an_out_of_range_override_inherits_rather_than_clamping() -> None:
    """Clamping would silently turn a typo into a setting."""
    out = schema.normalise_state(
        {"fast": {"timeline_overrides": {"deadline_buffer_days": 900}}}
    )
    assert out["fast"]["timeline_overrides"]["deadline_buffer_days"] is None


def test_slow_fingerprint_ignores_fast_field_changes() -> None:
    """Moving a milestone must not re-bill the model for forty write-ups."""
    first = schema.slow_fingerprint(SAMPLE["slow"])
    moved = {**SAMPLE, "fast": {**SAMPLE["fast"], "stage": "writing"}}

    assert schema.slow_fingerprint(moved["slow"]) == first
    # Key order must not matter, or two equal states would hash differently.
    reordered = dict(reversed(list(SAMPLE["slow"].items())))
    assert schema.slow_fingerprint(reordered) == first
    # A changed claim is a changed identity.
    changed = {**SAMPLE["slow"], "claimed_contribution": "Something else"}
    assert schema.slow_fingerprint(changed) != first


def test_provenance_defaults_to_stated_and_keeps_what_mylo_recorded() -> None:
    """The only way in without provenance is a person's doing."""
    out = schema.normalise_state(
        {**SAMPLE, "provenance": {"method": "inferred", "stage": "nonsense"}}
    )

    assert out["provenance"]["method"] == "inferred"
    assert out["provenance"]["problem"] == "stated"
    assert out["provenance"]["stage"] == "stated"
    # Empty fields carry no provenance at all — there is nothing to attribute.
    assert "exclusions" not in out["provenance"]


# --------------------------------------------------------------------------- #
# The model
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_patch_merges_rather_than_replacing(project: Project) -> None:
    """The wizard, the extractor and the panel each write only what they know."""
    state = ProjectState.objects.create(project=project)
    state.apply(SAMPLE).save()
    identity = state.slow_fingerprint

    state.apply({"fast": {"stage": "writing"}}).save()

    assert state.slow["problem"].startswith("Whether multi-hop")
    assert state.fast["stage"] == "writing"
    assert state.slow_fingerprint == identity
    # Zero is "created but never written"; two saves make it two.
    assert state.state_version == 2


@pytest.mark.django_db
def test_never_confirmed_and_confirmed_today_are_different_answers(
    project: Project,
) -> None:
    state = ProjectState.objects.create(project=project)
    assert state.days_since_confirmed() is None

    state.confirmed_at = timezone.localdate()
    assert state.days_since_confirmed() == 0


# --------------------------------------------------------------------------- #
# Timeline resolution (plan 2.5)
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_effective_timeline_resolution_order(owner: User) -> None:
    """Project override → the reader's own → the lab's → the system default."""
    lab = Lab.objects.create(name="Pulse", slug="pulse")
    lab.watch.deadline_buffer_days = 30
    lab.watch.min_paper_window_days = 90
    lab.watch.save()
    project = Project.objects.create(name="Ariadne", scope_lab=lab)

    # Nobody has said anything: the system defaults, labelled as such.
    bare = effective_timeline(project)
    assert (bare.buffer_days, bare.buffer_source) == (30, SOURCE_LAB)

    WatchPreference.objects.create(
        user=owner, deadline_buffer_days=7, min_paper_window_days=45
    )
    owner.refresh_from_db()
    # A lab project in someone's personal report is judged by whether *they* can
    # make the deadline, so the reader outranks the lab.
    mine = effective_timeline(project, owner)
    assert (mine.buffer_days, mine.buffer_source) == (7, SOURCE_USER)
    assert (mine.window_days, mine.window_source) == (45, SOURCE_USER)

    ProjectState.objects.create(project=project).apply(
        {"fast": {"timeline_overrides": {"deadline_buffer_days": 3}}}
    ).save()
    project.refresh_from_db()
    resolved = effective_timeline(project, owner)
    # The project overrides the buffer and inherits the window — each half is
    # resolved independently.
    assert (resolved.buffer_days, resolved.buffer_source) == (3, SOURCE_PROJECT)
    assert (resolved.window_days, resolved.window_source) == (45, SOURCE_USER)


@pytest.mark.django_db
def test_a_reader_with_no_settings_gets_the_system_default(owner: User) -> None:
    resolved = effective_timeline(None, owner)
    assert (resolved.buffer_days, resolved.window_days) == (14, 60)
    assert resolved.buffer_source == SOURCE_SYSTEM


# --------------------------------------------------------------------------- #
# The API
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_an_editor_writes_and_the_read_reports_the_resolved_timeline(
    client: APIClient, owner: User, project: Project
) -> None:
    client.force_authenticate(owner)

    resp = client.patch(f"/api/projects/{project.id}/state/", SAMPLE, format="json")
    assert resp.status_code == 200
    assert resp.data["slow"]["claimed_contribution"] == "A measurement-validity study"
    assert resp.data["state_version"] == 1
    assert resp.data["is_empty"] is False
    # Editing *is* confirming what you just read, or the staleness prompt fires on
    # state edited an hour ago.
    assert resp.data["days_since_confirmed"] == 0
    assert resp.data["effective_timeline"]["buffer_days"] == 21
    assert resp.data["effective_timeline"]["buffer_source"] == SOURCE_PROJECT

    read = client.get(f"/api/projects/{project.id}/state/")
    assert read.data["slow_fingerprint"] == resp.data["slow_fingerprint"]


@pytest.mark.django_db
def test_a_project_with_no_state_reads_as_unasked_not_as_empty(
    client: APIClient, owner: User, project: Project
) -> None:
    """A project nobody has asked yet is a prompt, not a blank document."""
    client.force_authenticate(owner)

    resp = client.get(f"/api/projects/{project.id}/state/")

    assert resp.status_code == 200
    assert resp.data["is_empty"] is True
    assert resp.data["state_version"] == 0
    assert resp.data["days_since_confirmed"] is None
    assert resp.data["slow"]["problem"] == ""


@pytest.mark.django_db
def test_confirming_changes_nothing_but_the_date(
    client: APIClient, owner: User, project: Project
) -> None:
    """"Still right" is a different act from an edit, and cheaper."""
    client.force_authenticate(owner)
    client.patch(f"/api/projects/{project.id}/state/", SAMPLE, format="json")
    ProjectState.objects.filter(project=project).update(confirmed_at=None)

    resp = client.post(f"/api/projects/{project.id}/state/confirm/")

    assert resp.status_code == 200
    assert resp.data["days_since_confirmed"] == 0
    assert resp.data["state_version"] == 1  # unchanged by a confirmation


@pytest.mark.django_db
def test_a_member_reads_but_cannot_write(
    client: APIClient, owner: User, project: Project
) -> None:
    member = User.objects.create_user(username="member", password="p")
    ProjectMember.objects.create(project=project, user=member)
    client.force_authenticate(member)

    assert client.get(f"/api/projects/{project.id}/state/").status_code == 200
    assert (
        client.patch(
            f"/api/projects/{project.id}/state/", SAMPLE, format="json"
        ).status_code
        == 403
    )
    assert client.post(f"/api/projects/{project.id}/state/confirm/").status_code == 403


@pytest.mark.django_db
def test_an_outsider_cannot_read_project_state_at_all(
    client: APIClient, project: Project
) -> None:
    """The most sensitive thing stored: unpublished plans and what is not working."""
    lab = Lab.objects.create(name="Pulse", slug="pulse")
    stranger = User.objects.create_user(username="stranger", password="p")
    LabMembership.objects.create(user=stranger, lab=lab)
    client.force_authenticate(stranger)

    assert client.get(f"/api/projects/{project.id}/state/").status_code == 403


@pytest.mark.django_db
def test_the_audit_log_records_the_change_without_recording_the_state(
    client: APIClient, owner: User, project: Project
) -> None:
    """Staff read this log, and the state is what they have no business seeing."""
    from apps.accounts.models import AuditEvent

    client.force_authenticate(owner)
    client.patch(f"/api/projects/{project.id}/state/", SAMPLE, format="json")

    event = AuditEvent.objects.filter(action="project.state.update").get()
    rendered = str(event.metadata)
    assert "multi-hop" not in rendered
    assert event.metadata["identity_changed"] is True

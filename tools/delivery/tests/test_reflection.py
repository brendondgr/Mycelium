"""What Mylo proposes about a project's state, and who decides.

The design constraint is one sentence: **the rules are deterministic and the
model only phrases them**. A model deciding on its own that a project's method
has changed, and writing that into the state, is the failure invariant 9 exists
to prevent — the reader would find their own words replaced by a machine's, in
the one document they are supposed to trust because they wrote it.

So each rule is a count with a threshold, each proposal is a concrete edit, and
accepting is the only thing that applies one.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from apps.research.models import Project, ProjectMember, ProjectState
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from tools.delivery import reflection
from tools.delivery.models import ReflectionProposal

TODAY = timezone.localdate()


@pytest.fixture
def owner(db) -> User:
    return User.objects.create_user("owner", password="p")


@pytest.fixture
def project(owner: User) -> Project:
    project = Project.objects.create(name="Synapse", scope_user=owner)
    state = ProjectState.objects.create(project=project)
    state.apply({"slow": {"claimed_contribution": "A measurement-validity study"}})
    # As the API sets it: editing state *is* confirming what you just read, so a
    # freshly-written state is not stale.
    state.confirmed_at = TODAY
    state.save()
    project.refresh_from_db()
    return project


# --------------------------------------------------------------------------- #
# The rules
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_repeated_saves_on_one_term_propose_a_method(project: Project) -> None:
    titles = [
        "Calibrated confidence scores for extracted triples",
        "Confidence estimation under schema drift",
        "Measuring confidence in knowledge graphs",
    ]

    proposal = reflection.method_proposal(project, titles)

    assert proposal is not None
    assert proposal.kind == ReflectionProposal.Kind.ADD_METHOD
    assert proposal.evidence["shared_term"] == "confidence"
    assert proposal.evidence["saved"] == 3
    assert "confidence" in proposal.proposal["slow"]["method"]


@pytest.mark.django_db
def test_two_saves_are_a_coincidence_not_a_pattern(project: Project) -> None:
    assert (
        reflection.method_proposal(
            project, ["Confidence scores", "Confidence estimation"]
        )
        is None
    )


@pytest.mark.django_db
def test_a_term_the_project_already_names_is_never_proposed(owner: User) -> None:
    """A proposal that restates the state is a question nobody should be asked."""
    project = Project.objects.create(name="Synapse", scope_user=owner)
    ProjectState.objects.create(project=project).apply(
        {"slow": {"method": ["confidence vectors"]}}
    ).save()
    project.refresh_from_db()

    proposal = reflection.method_proposal(
        project,
        [
            "Confidence scores for triples",
            "Confidence under drift",
            "Confidence in graphs",
        ],
    )

    assert proposal is None


@pytest.mark.django_db
def test_repeated_dismissals_propose_an_exclusion(project: Project) -> None:
    """The rule that pays for itself: Mylo admitting it got something wrong."""
    titles = [f"Federated learning for task {n}" for n in range(4)]

    proposal = reflection.exclusion_proposal(project, titles)

    assert proposal is not None
    # "federated", "learning" and "task" are equally frequent here. The longest
    # wins, because excluding "task" would suppress an enormous amount the reader
    # never objected to — a more specific exclusion is a safer one.
    assert proposal.evidence["shared_term"] == "federated"
    assert "federated" in proposal.proposal["fast"]["exclusions"]


@pytest.mark.django_db
def test_an_undated_milestone_proposes_setting_one(project: Project) -> None:
    """"Give me a date and I can answer this" beats a guessed verdict."""
    rows = [
        {"status": "no_milestone", "venue": "ECIR 2027"},
        {"status": "fits", "venue": "SOT 2027"},
    ]

    proposal = reflection.milestone_proposal(project, rows)

    assert proposal.kind == ReflectionProposal.Kind.SET_MILESTONE
    assert proposal.evidence["unjudged"] == 1
    assert proposal.evidence["venues"] == ["ECIR 2027"]


@pytest.mark.django_db
def test_state_nobody_has_confirmed_in_a_month_asks_to_be_reviewed(
    project: Project,
) -> None:
    """Stale state is the most dangerous input, because it reads as current."""
    assert reflection.review_proposal(project, today=TODAY) is None

    ProjectState.objects.filter(project=project).update(
        confirmed_at=TODAY - timedelta(days=40)
    )
    project.refresh_from_db()

    proposal = reflection.review_proposal(project, today=TODAY)
    assert proposal.kind == ReflectionProposal.Kind.REVIEW_STATE
    assert proposal.evidence["days_since_confirmed"] == 40


@pytest.mark.django_db
def test_state_nobody_has_ever_confirmed_is_asked_about_too(owner: User) -> None:
    """The reports quote it as though somebody had said it was right."""
    never = Project.objects.create(name="Imported", scope_user=owner)
    ProjectState.objects.create(project=never).apply(
        {"slow": {"problem": "Something a document said"}}
    ).save()
    never.refresh_from_db()

    proposal = reflection.review_proposal(never, today=TODAY)

    assert proposal is not None
    assert proposal.evidence["days_since_confirmed"] is None


@pytest.mark.django_db
def test_a_project_that_has_said_nothing_is_not_asked_to_review_nothing(
    owner: User,
) -> None:
    empty = Project.objects.create(name="Blank", scope_user=owner)
    ProjectState.objects.create(project=empty)
    empty.refresh_from_db()

    assert reflection.review_proposal(empty, today=TODAY) is None


# --------------------------------------------------------------------------- #
# Persisting
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_pending_proposal_is_not_raised_twice(
    owner: User, project: Project
) -> None:
    proposal = reflection.Proposal(
        project_id=str(project.id),
        kind=ReflectionProposal.Kind.ADD_METHOD,
        evidence={"shared_term": "confidence"},
    )

    first = reflection.persist([proposal], {"target_user": owner}, today=TODAY)
    second = reflection.persist([proposal], {"target_user": owner}, today=TODAY)

    assert (first, second) == (1, 0)
    assert ReflectionProposal.objects.count() == 1


@pytest.mark.django_db
def test_a_rejected_proposal_is_not_asked_again_next_monday(
    owner: User, project: Project
) -> None:
    """Declining is a decision the system respects, not a question it repeats."""
    proposal = reflection.Proposal(
        project_id=str(project.id),
        kind=ReflectionProposal.Kind.ADD_EXCLUSION,
        evidence={"shared_term": "federated"},
    )
    reflection.persist([proposal], {"target_user": owner}, today=TODAY)
    ReflectionProposal.objects.update(
        status=ReflectionProposal.Status.REJECTED, decided_at=timezone.now()
    )

    assert reflection.persist([proposal], {"target_user": owner}, today=TODAY) == 0
    # Past the cooldown, it may be raised again.
    later = TODAY + timedelta(days=reflection.COOLDOWN_DAYS + 1)
    assert reflection.persist([proposal], {"target_user": owner}, today=later) == 1


@pytest.mark.django_db
def test_a_pending_proposal_lapses_on_its_date(
    owner: User, project: Project
) -> None:
    reflection.persist(
        [
            reflection.Proposal(
                project_id=str(project.id),
                kind=ReflectionProposal.Kind.ADD_METHOD,
            )
        ],
        {"target_user": owner},
        today=TODAY,
    )

    assert reflection.expire_stale(TODAY) == 0
    lapsed = TODAY + timedelta(days=reflection.EXPIRES_AFTER_DAYS + 1)
    assert reflection.expire_stale(lapsed) == 1
    assert ReflectionProposal.objects.get().status == (
        ReflectionProposal.Status.EXPIRED
    )


@pytest.mark.django_db
def test_the_block_says_what_prompted_each_proposal(
    owner: User, project: Project
) -> None:
    """A request to change what someone wrote has to say plainly why."""
    ReflectionProposal.objects.create(
        target_user=owner,
        project=project,
        kind=ReflectionProposal.Kind.ADD_EXCLUSION,
        evidence={"dismissed": 6, "shared_term": "federated"},
        expires_on=TODAY + timedelta(days=14),
    )

    block = reflection.reflection_block(list(ReflectionProposal.objects.all()))

    assert "## Mylo's reflection" in block
    assert "you dismissed 6 items" in block
    assert '"federated"' in block


# --------------------------------------------------------------------------- #
# Deciding
# --------------------------------------------------------------------------- #
@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_accepting_is_the_only_thing_that_applies_a_proposal(
    client: APIClient, owner: User, project: Project
) -> None:
    """Invariant 9: nothing else in the product writes a proposal into a state."""
    row = ReflectionProposal.objects.create(
        target_user=owner,
        project=project,
        kind=ReflectionProposal.Kind.ADD_METHOD,
        proposal={"slow": {"method": ["triple confidence estimation"]}},
        expires_on=TODAY + timedelta(days=14),
    )
    client.force_authenticate(owner)

    assert project.state.slow["method"] == []

    resp = client.post(f"/api/reflections/{row.id}/action/", {"action": "accept"})

    assert resp.status_code == 200
    project.refresh_from_db()
    assert project.state.slow["method"] == ["triple confidence estimation"]
    # Accepting is the reader saying the state is right, so it confirms it too.
    assert project.state.days_since_confirmed() == 0


@pytest.mark.django_db
def test_rejecting_changes_the_state_not_at_all(
    client: APIClient, owner: User, project: Project
) -> None:
    row = ReflectionProposal.objects.create(
        target_user=owner,
        project=project,
        kind=ReflectionProposal.Kind.ADD_METHOD,
        proposal={"slow": {"method": ["something"]}},
        expires_on=TODAY + timedelta(days=14),
    )
    client.force_authenticate(owner)

    client.post(f"/api/reflections/{row.id}/action/", {"action": "reject"})

    project.refresh_from_db()
    assert project.state.slow["method"] == []
    assert ReflectionProposal.objects.get().status == (
        ReflectionProposal.Status.REJECTED
    )


@pytest.mark.django_db
def test_a_proposal_belongs_to_whoever_wrote_the_state(
    client: APIClient, owner: User, project: Project
) -> None:
    """A request to change someone's own words belongs to them and nobody else."""
    stranger = User.objects.create_user("stranger", password="p")
    row = ReflectionProposal.objects.create(
        target_user=owner,
        project=project,
        kind=ReflectionProposal.Kind.REVIEW_STATE,
        expires_on=TODAY + timedelta(days=14),
    )
    client.force_authenticate(stranger)

    assert client.get("/api/reflections/").data == []
    assert (
        client.post(
            f"/api/reflections/{row.id}/action/", {"action": "accept"}
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_a_member_who_cannot_edit_cannot_accept(
    client: APIClient, owner: User, project: Project
) -> None:
    """Re-checked here rather than trusted from when it was proposed."""
    member = User.objects.create_user("member", password="p")
    ProjectMember.objects.create(project=project, user=member)
    row = ReflectionProposal.objects.create(
        target_user=member,
        project=project,
        kind=ReflectionProposal.Kind.ADD_METHOD,
        proposal={"slow": {"method": ["something"]}},
        expires_on=TODAY + timedelta(days=14),
    )
    client.force_authenticate(member)

    assert (
        client.post(
            f"/api/reflections/{row.id}/action/", {"action": "accept"}
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_a_decided_proposal_cannot_be_decided_again(
    client: APIClient, owner: User, project: Project
) -> None:
    row = ReflectionProposal.objects.create(
        target_user=owner,
        project=project,
        kind=ReflectionProposal.Kind.REVIEW_STATE,
        status=ReflectionProposal.Status.ACCEPTED,
        expires_on=TODAY + timedelta(days=14),
    )
    client.force_authenticate(owner)

    assert (
        client.post(
            f"/api/reflections/{row.id}/action/", {"action": "reject"}
        ).status_code
        == 400
    )

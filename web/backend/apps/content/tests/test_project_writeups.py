"""Judging an item against what a project **claims**, not just what it is about.

A personal write-up answers "does this fit your interests". A project write-up
can answer something much sharper — "does this do what you were going to do, and
if not, what do you still have that it does not" — because a project has stated
its contribution. These tests are about that variant: when it is asked for, what
invalidates it, and what it costs a target that has said nothing.

The last one matters most. The project state is optional, so a project that has
not been asked must produce exactly the prompt and exactly the cost it did
before, or the feature would be a tax on everybody who ignored it.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from tools.recommendation import cluster_fit
from tools.recommendation.cluster_fit import (
    Candidate,
    Evidence,
    areas_fingerprint,
    build_prompt,
    is_current,
    make_writeup,
    parse,
    project_claim_block,
)
from tools.recommendation.clustering import Cluster
from tools.recommendation.theme_run import _project_claim
from tools.retrieval.models import ContentItem

from apps.research.models import Project, ProjectState

CLAIM = {
    "problem": "Whether multi-hop QA benchmarks detect graph quality",
    "claimed_contribution": "A measurement-validity study",
    "method": ["multi-lens LLM extraction"],
    "data": ["MuSiQue"],
    "planned_components": ["confidence vectors"],
}


def _candidate() -> Candidate:
    item = ContentItem(
        type=ContentItem.Type.PAPER, metadata={"title": "A corruption study"}
    )
    return Candidate(item=item, evidence=Evidence(position=1, is_new=True))


def _cluster() -> Cluster:
    return Cluster(id="c1", label="Agentic KG", areas=["knowledge graphs"])


# --------------------------------------------------------------------------- #
# The prompt
# --------------------------------------------------------------------------- #
def test_the_claim_block_carries_the_claim_and_not_the_calendar() -> None:
    """Milestones are the timeline matcher's business.

    Putting them in the prompt would invite the model to reason about dates,
    which is the one thing the report contract forbids it from doing (plan H2).
    """
    block = project_claim_block({**CLAIM, "milestones": [{"date": "2026-10-09"}]})

    assert "A measurement-validity study" in block
    assert "MuSiQue" in block
    assert "2026-10-09" not in block


def test_a_project_prompt_asks_where_the_item_still_falls_short() -> None:
    prompt = build_prompt(
        "a researcher",
        _cluster(),
        [],
        [_candidate()],
        project_claim=project_claim_block(CLAIM),
    )

    assert "the team has stated what it claims" in prompt
    assert "A measurement-validity study" in prompt


def test_a_target_with_no_claim_gets_the_prompt_it_always_got() -> None:
    """The state is optional, so it cannot be a tax on people who ignored it."""
    plain = build_prompt("a researcher", _cluster(), [], [_candidate()])
    unstated = build_prompt(
        "a researcher", _cluster(), [], [_candidate()], project_claim=""
    )

    assert plain == unstated
    assert "still has that the item does not" not in plain


# --------------------------------------------------------------------------- #
# The answer
# --------------------------------------------------------------------------- #
def test_differs_is_kept_only_when_a_claim_was_actually_given() -> None:
    """A confident answer to a question nobody asked is an invention."""
    raw = json.dumps(
        {
            "items": [
                {
                    "n": 1,
                    "verdict": "read",
                    "matters": "It asks your question.",
                    "use": "Read the protocol.",
                    "take": "The corruption design.",
                    "caveat": "It is a preprint.",
                    "differs": "It does not vary the construction pipeline.",
                }
            ]
        }
    )
    candidates = [_candidate()]
    fingerprint = areas_fingerprint(["knowledge graphs"])

    with_claim = parse(
        raw, candidates, fingerprint=fingerprint, state_fingerprint="abc123"
    )
    without = parse(raw, candidates, fingerprint=fingerprint)

    entry = next(iter(with_claim.values()))
    assert entry["differs"].startswith("It does not vary")
    assert entry["state_fingerprint"] == "abc123"
    assert "differs" not in next(iter(without.values()))


def test_a_changed_claim_invalidates_a_stored_writeup() -> None:
    """The point of the slow/fast split, enforced."""
    writeup = make_writeup(
        verdict="read",
        beats=["It asks your question."],
        caveat="A preprint.",
        bridge_note="",
        fingerprint="areas1",
        source="llm",
        state_fingerprint="claim1",
    )

    assert is_current(writeup, "areas1", "claim1") is True
    assert is_current(writeup, "areas1", "claim2") is False
    # And in the other direction: a write-up judged against a claim the project
    # has since deleted is as stale as one judged against a different claim.
    assert is_current(writeup, "areas1", "") is False


def test_a_personal_writeup_is_unaffected_by_the_new_field() -> None:
    writeup = make_writeup(
        verdict="read",
        beats=["Matches your interests."],
        caveat="Not read for you.",
        bridge_note="",
        fingerprint="areas1",
        source="deterministic",
    )

    assert "state_fingerprint" not in writeup
    assert is_current(writeup, "areas1") is True


def test_the_rubric_version_moved_with_the_contract() -> None:
    """A prompt edit without a bump silently serves answers to the old question."""
    assert cluster_fit.RUBRIC_VERSION == "b2"


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_the_plan_reads_the_projects_claim(db) -> None:
    owner = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Synapse", scope_user=owner)
    ProjectState.objects.create(project=project).apply({"slow": CLAIM}).save()
    project.refresh_from_db()

    resolved = _project_claim({"target_project": project})

    assert "A measurement-validity study" in resolved["project_claim"]
    assert resolved["state_fingerprint"] == project.state.slow_fingerprint


@pytest.mark.django_db
def test_a_project_that_has_said_nothing_resolves_to_nothing(db) -> None:
    owner = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Synapse", scope_user=owner)
    ProjectState.objects.create(project=project)
    project.refresh_from_db()

    assert _project_claim({"target_project": project}) == {
        "project_claim": "",
        "state_fingerprint": "",
    }
    assert _project_claim({"target_user": owner}) == {
        "project_claim": "",
        "state_fingerprint": "",
    }


@pytest.mark.django_db
def test_moving_a_milestone_does_not_invalidate_a_writeup(db) -> None:
    """The whole reason the state is split in two (plan 2.1)."""
    owner = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Synapse", scope_user=owner)
    state = ProjectState.objects.create(project=project)
    state.apply({"slow": CLAIM}).save()
    before = _project_claim({"target_project": project})

    state.apply(
        {"fast": {"milestones": [{"kind": "draft_by", "date": "2027-01-01"}]}}
    ).save()
    project.refresh_from_db()

    assert _project_claim({"target_project": project}) == before

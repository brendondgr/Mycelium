"""Reading a project's state out of a document, and refusing to invent one.

The contract that matters is not "can it read an abstract" — it is what happens
when it cannot. An extractor that fills in a claimed contribution the document
never made produces a sentence in the team's voice that nobody wrote, and that
sentence then grounds every report about the project. Refusal is the right
answer, and it is the answer these tests are mostly about.

Everything produced is a **proposal**: marked inferred, applied by nobody but a
person. The endpoint saves nothing at all.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from apps.research.models import Project, ProjectState
from apps.research.state_extract import (
    GROUNDING_FLOOR,
    extract_project_state,
    grounding_failures,
)

DOCUMENT = """
We ask whether multi-hop question answering benchmarks can detect knowledge graph
construction quality at all. Our contribution is a measurement-validity study:
config-diff ablations over the construction pipeline, paired with an analysis
relating spurious edge density to retrieval error. We build graphs with multi-lens
LLM extraction and schema settling, and evaluate on MuSiQue and 2WikiMultiHopQA.
We do not yet have a labeled evaluation set, and all labels come from a single
unblinded rater. We plan to add confidence vectors and contradiction detection.
"""

GOOD = {
    "problem": "Whether multi-hop question answering benchmarks detect knowledge"
    " graph construction quality",
    "claimed_contribution": "A measurement-validity study using config-diff"
    " ablations and spurious edge density analysis",
    "method": ["multi-lens LLM extraction", "schema settling"],
    "data": ["MuSiQue", "2WikiMultiHopQA"],
    "planned_components": ["confidence vectors", "contradiction detection"],
    "blockers": ["no labeled evaluation set", "single unblinded rater"],
    "stage": "experiments",
}


def _replies(*payloads):
    """A ``complete`` stub that returns each payload in turn."""
    queue = list(payloads)

    def ask(_system: str, _prompt: str) -> str | None:
        return queue.pop(0) if queue else None

    return ask


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #
def test_a_grounded_reading_becomes_a_proposal() -> None:
    outcome = extract_project_state(
        DOCUMENT, complete=_replies(json.dumps(GOOD))
    )

    assert outcome.ok is True
    assert outcome.attempts == 1
    slow = outcome.proposal["slow"]
    assert "multi-hop" in slow["problem"]
    assert slow["data"] == ["MuSiQue", "2WikiMultiHopQA"]
    assert [b["text"] for b in slow["blockers"]] == [
        "no labeled evaluation set",
        "single unblinded rater",
    ]


def test_everything_a_document_produced_is_marked_inferred() -> None:
    """Invariant 9: a stated field is never overwritten by a machine reading."""
    outcome = extract_project_state(DOCUMENT, complete=_replies(json.dumps(GOOD)))

    assert outcome.proposal["provenance"]
    assert set(outcome.proposal["provenance"].values()) == {"inferred"}


def test_json_wrapped_in_prose_or_fences_is_still_read() -> None:
    """Refusing anything but a bare object throws away correct answers."""
    wrapped = (
        f"Here is what I found:\n```json\n{json.dumps(GOOD)}\n```\nHope that helps."
    )

    outcome = extract_project_state(DOCUMENT, complete=_replies(wrapped))

    assert outcome.ok is True
    assert outcome.proposal["fast"]["stage"] == "experiments"


# --------------------------------------------------------------------------- #
# Refusing
# --------------------------------------------------------------------------- #
def test_an_invented_contribution_is_rejected_and_retried_once() -> None:
    """The invention would arrive wearing the team's voice."""
    invented = {
        "claimed_contribution": "A federated transformer achieving state of the"
        " art across nine multilingual retrieval corpora"
    }

    outcome = extract_project_state(
        DOCUMENT, complete=_replies(json.dumps(invented), json.dumps(GOOD))
    )

    assert outcome.attempts == 2
    assert outcome.ok is True
    assert any("ungrounded" in failure for failure in outcome.failures)


def test_invented_numbers_are_rejected_however_short_the_claim() -> None:
    """A short claim cannot carry an overlap ratio, so it carries this instead."""
    assert grounding_failures("a 2029 deadline", DOCUMENT)
    assert grounding_failures("$4,000,000 award", DOCUMENT)
    # The document's own specifics are fine.
    assert not grounding_failures("2WikiMultiHopQA", DOCUMENT)


def test_two_ungrounded_attempts_end_in_a_refusal_not_a_guess() -> None:
    bad = json.dumps(
        {
            "problem": "Whether federated learning improves multilingual"
            " speech recognition across distributed edge devices"
        }
    )

    outcome = extract_project_state(DOCUMENT, complete=_replies(bad, bad))

    assert outcome.ok is False
    assert outcome.proposal == {}
    assert "ground" in outcome.reason
    assert outcome.attempts == 2


def test_a_document_that_describes_no_project_is_a_clean_empty_answer() -> None:
    """Not a failure: the correct reading of a document that does not say."""
    outcome = extract_project_state(DOCUMENT, complete=_replies("{}"))

    assert outcome.ok is True
    assert outcome.is_empty
    assert "does not describe" in outcome.reason


def test_too_little_text_is_refused_before_any_model_call() -> None:
    called = []

    def ask(_s, _p):
        called.append(1)
        return "{}"

    outcome = extract_project_state("A short note.", complete=ask)

    assert outcome.ok is False
    assert not called
    assert "too little text" in outcome.reason


def test_a_model_that_is_down_refuses_rather_than_raising() -> None:
    def ask(_s, _p):
        raise RuntimeError("connection refused")

    outcome = extract_project_state(DOCUMENT, complete=ask)

    assert outcome.ok is False
    assert "could not read" in outcome.reason


def test_the_grounding_floor_is_a_ratio_not_a_substring() -> None:
    """Rephrasing in the model's own words must survive; inventing must not."""
    rephrased = (
        "Investigating whether multi-hop benchmarks can detect construction"
        " quality of knowledge graphs"
    )
    assert not grounding_failures(rephrased, DOCUMENT)
    assert GROUNDING_FLOOR < 0.5  # a short answer cannot be held to half


# --------------------------------------------------------------------------- #
# The endpoint
# --------------------------------------------------------------------------- #
@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_the_endpoint_proposes_and_saves_nothing(
    client: APIClient, monkeypatch
) -> None:
    """An extractor that wrote into the state would overwrite what a team said."""
    from apps.research import views

    owner = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Synapse", scope_user=owner)
    monkeypatch.setattr(
        views,
        "get_object_or_404",
        views.get_object_or_404,
    )
    monkeypatch.setattr(
        "apps.research.state_extract.extract_project_state",
        lambda text, **_kw: extract_project_state(
            text, complete=_replies(json.dumps(GOOD))
        ),
    )
    client.force_authenticate(owner)

    resp = client.post(
        f"/api/projects/{project.id}/state/extract/",
        {"text": DOCUMENT},
        format="json",
    )

    assert resp.status_code == 200
    assert resp.data["ok"] is True
    assert set(resp.data["proposal"]["provenance"].values()) == {"inferred"}
    assert not ProjectState.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_a_member_who_cannot_edit_cannot_extract(client: APIClient) -> None:
    from apps.research.models import ProjectMember

    owner = User.objects.create_user("owner", password="p")
    member = User.objects.create_user("member", password="p")
    project = Project.objects.create(name="Synapse", scope_user=owner)
    ProjectMember.objects.create(project=project, user=member)
    client.force_authenticate(member)

    resp = client.post(
        f"/api/projects/{project.id}/state/extract/",
        {"text": DOCUMENT},
        format="json",
    )

    assert resp.status_code == 403


@pytest.mark.django_db
def test_an_empty_request_is_a_400_not_a_model_call(client: APIClient) -> None:
    owner = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Synapse", scope_user=owner)
    client.force_authenticate(owner)

    resp = client.post(
        f"/api/projects/{project.id}/state/extract/", {}, format="json"
    )

    assert resp.status_code == 400

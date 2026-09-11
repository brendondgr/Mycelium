"""The three semantic matchers, and the one that needs no model at all.

Similarity is stubbed throughout. What is under test is not whether an embedder
can tell two sentences apart — that is the embedder's job and measuring it here
would be measuring fastembed — but the decisions built on top of it: what gets
compared against what, what happens when a project has said nothing, and which
failures are silent rather than wrong.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import AuthorWork, Lab, LabMembership, Profile
from apps.content.matchers import blockers as blocker_matcher
from apps.content.matchers import known_literature as known
from apps.content.matchers import overlap as overlap_matcher
from apps.content.matchers import similarity as sim
from apps.content.matchers import team_gap
from apps.content.models import (
    Collection,
    CollectionItem,
    ContentItem,
    ItemComprehension,
    ProjectShare,
)
from apps.research.models import Project, ProjectState


class _Precis:
    """A stand-in for ``ItemComprehension`` — the matchers only read attributes."""

    def __init__(self, **fields):
        for name in ("problem", "method", "setting", "claim", "limitations",
                     "reusable", "source_fingerprint"):
            setattr(self, name, fields.get(name, ""))


@pytest.fixture(autouse=True)
def _no_real_embedder(monkeypatch):
    """Every similarity is 1.0 for identical text and 0.0 otherwise.

    Crude on purpose: it makes "what is compared against what" visible, which is
    the thing these tests are about.
    """
    monkeypatch.setattr(sim, "embed_many", lambda texts, **_kw: {})
    monkeypatch.setattr(
        sim,
        "similarity",
        lambda left, right, **_kw: 1.0
        if " ".join((left or "").split()) == " ".join((right or "").split())
        else 0.0,
    )
    monkeypatch.setattr(overlap_matcher, "similarity", sim.similarity)
    monkeypatch.setattr(overlap_matcher, "embed_many", sim.embed_many)
    monkeypatch.setattr(blocker_matcher, "similarity", sim.similarity)
    monkeypatch.setattr(blocker_matcher, "embed_many", sim.embed_many)
    monkeypatch.setattr(team_gap, "similarity", sim.similarity)
    monkeypatch.setattr(team_gap, "embed_many", sim.embed_many)


def _project(db, **state) -> Project:
    user = User.objects.create_user("owner", password="p")
    project = Project.objects.create(name="Synapse", scope_user=user)
    if state:
        ProjectState.objects.create(project=project).apply(state).save()
        project.refresh_from_db()
    return project


# --------------------------------------------------------------------------- #
# Overlap
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_overlap_compares_the_claim_not_the_topic(db) -> None:
    """Everything in the feed is already on the topic; only the claim informs."""
    project = _project(
        db, slow={"claimed_contribution": "A measurement-validity study"}
    )
    rows = overlap_matcher.overlap_rows(
        project,
        {
            "a": _Precis(claim="A measurement-validity study"),
            "b": _Precis(claim="A survey of graph databases",
                         problem="A measurement-validity study"),
        },
    )

    by_id = {row.content_id: row for row in rows}
    assert by_id["a"].claim_similarity == 1.0
    # The same words in the *problem* field are not a competing claim.
    assert by_id["b"].claim_similarity == 0.0


@pytest.mark.django_db
def test_the_approach_corroborates_rather_than_fires_on_its_own(db) -> None:
    """Same method, different question is a neighbour, not a threat."""
    project = _project(
        db,
        slow={
            "claimed_contribution": "A measurement-validity study",
            "method": ["multi-lens LLM extraction"],
        },
    )
    rows = overlap_matcher.overlap_rows(
        project, {"a": _Precis(method="multi-lens LLM extraction")}
    )

    assert rows[0].approach_similarity == 1.0
    # Discounted: a perfect method match alone scores below a claim match.
    assert rows[0].score == pytest.approx(0.6)


@pytest.mark.django_db
def test_a_project_that_has_not_said_what_it_claims_gets_no_overlap_rows(db) -> None:
    """The honest answer, and the reason the state panel exists."""
    assert overlap_matcher.overlap_rows(_project(db), {"a": _Precis(claim="x")}) == []


@pytest.mark.django_db
def test_where_you_still_differ_is_decided_in_code(db) -> None:
    """The model phrases it; it does not choose what the sentence is about."""
    project = _project(
        db,
        slow={
            "claimed_contribution": "A measurement-validity study",
            "planned_components": ["confidence vectors", "contradiction detection"],
            "data": ["MuSiQue"],
        },
    )

    rows = overlap_matcher.overlap_rows(
        project,
        {
            "a": _Precis(
                claim="A measurement-validity study",
                reusable="We release confidence vectors for every triple.",
                setting="Evaluated on MuSiQue.",
            )
        },
    )

    # Only what the précis genuinely never mentions.
    assert rows[0].differences == ["contradiction detection"]


# --------------------------------------------------------------------------- #
# Blockers
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_blocker_is_matched_against_what_is_on_offer(db) -> None:
    """Against ``reusable`` alone: the abstract would match everything."""
    project = _project(
        db, slow={"blockers": [{"text": "No labeled evaluation set"}]}
    )

    rows = blocker_matcher.blocker_rows(
        project,
        {
            "a": _Precis(reusable="No labeled evaluation set"),
            "b": _Precis(
                reusable="A new attention kernel",
                claim="No labeled evaluation set",
            ),
        },
    )

    assert rows[0].content_id == "a"
    assert rows[0].score == 1.0
    assert rows[0].blocker_id == "b1"
    assert all(row.score == 0.0 for row in rows if row.content_id == "b")


@pytest.mark.django_db
def test_an_item_with_nothing_reusable_produces_no_pair(db) -> None:
    project = _project(db, slow={"blockers": [{"text": "No baseline"}]})

    assert blocker_matcher.blocker_rows(project, {"a": _Precis()}) == []


@pytest.mark.django_db
def test_a_project_with_no_blockers_produces_nothing(db) -> None:
    assert blocker_matcher.blocker_rows(
        _project(db), {"a": _Precis(reusable="A dataset")}
    ) == []


# --------------------------------------------------------------------------- #
# Known literature
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_reader_is_never_shown_their_own_paper_as_a_discovery(db) -> None:
    """The most credibility-destroying thing a research feed can do."""
    user = User.objects.create_user("ada", password="p")
    AuthorWork.objects.create(
        user=user,
        source="openalex",
        source_id="W1",
        title="Notes on the Analytical Engine",
    )
    mine = ContentItem(
        type=ContentItem.Type.PAPER,
        metadata={"title": "  notes on the ANALYTICAL engine!  "},
    )

    store = known.known_literature(None, user)
    is_known, revised, how = store.verdict(mine)

    assert is_known is True
    assert revised is False
    assert how.how == "authored"


@pytest.mark.django_db
def test_a_paper_the_team_collected_is_not_news_again(db) -> None:
    project = _project(db)
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="test",
        external_id="p1",
        metadata={"title": "A filed paper"},
    )
    collection = Collection.objects.create(project=project, name="Scoop watch")
    CollectionItem.objects.create(collection=collection, content=item)

    store = known.known_literature(project, None)

    assert store.verdict(item)[0] is True
    assert store.lookup(item).where == "Scoop watch"


@pytest.mark.django_db
def test_a_revision_of_a_known_paper_is_news_again(db) -> None:
    """The one case where re-surfacing something known is right."""
    project = _project(db)
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER,
        source="test",
        external_id="p1",
        metadata={"title": "A filed paper"},
    )
    ItemComprehension.objects.create(content=item, source_fingerprint="abc")
    ProjectShare.objects.create(
        project=project, content=item, shared_by=project.scope_user
    )

    store = known.known_literature(project, None)
    item.refresh_from_db()
    fresh = ItemComprehension.objects.get(content=item)
    fresh.source_fingerprint = "def"

    is_known, revised, _how = store.verdict(item, fresh)

    assert (is_known, revised) == (True, True)


@pytest.mark.django_db
def test_a_project_that_named_collections_means_those_collections(db) -> None:
    """A team that curates a list has said those papers are theirs."""
    project = _project(
        db, fast={"known_literature": {"collections": ["Scoop watch"]}}
    )
    watched, other = (
        Collection.objects.create(project=project, name=name)
        for name in ("Scoop watch", "Someday")
    )
    items = {}
    for key, collection in (("watched", watched), ("other", other)):
        item = ContentItem.objects.create(
            type=ContentItem.Type.PAPER,
            source="test",
            external_id=key,
            metadata={"title": f"Paper {key}"},
        )
        CollectionItem.objects.create(collection=collection, content=item)
        items[key] = item

    store = known.known_literature(project, None)

    assert store.verdict(items["watched"])[0] is True
    assert store.verdict(items["other"])[0] is False


def test_the_title_key_survives_punctuation_and_case() -> None:
    """A preprint and its published version are not two discoveries."""
    assert known.title_key("Do Multi-Hop QA Scores Track Graph Quality?") == (
        known.title_key("do multi hop qa scores track graph quality")
    )


# --------------------------------------------------------------------------- #
# Team gap
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_a_requirement_nobody_states_is_a_gap(db) -> None:
    lab = Lab.objects.create(name="Pulse", slug="pulse")
    member = User.objects.create_user("member", password="p")
    LabMembership.objects.create(user=member, lab=lab)
    Profile.objects.filter(user=member).update(
        interests={"version": 2, "areas": ["knowledge graphs"]}
    )
    grant = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="test",
        external_id="g1",
        metadata={
            "title": "Exposure science grant",
            "ai_fields": {
                "required_expertise": ["knowledge graphs", "environmental health"]
            },
        },
    )

    gaps = team_gap.team_gaps({"target_lab": lab}, [grant], threshold=0.9)

    by_need = {gap.requirement: gap for gap in gaps}
    assert by_need["knowledge graphs"].is_gap is False
    assert by_need["knowledge graphs"].covered_by[0].username == "member"
    assert by_need["environmental health"].is_gap is True


@pytest.mark.django_db
def test_a_call_that_names_no_requirement_produces_no_gap(db) -> None:
    """Silence in the source means no gap, not an unknown one."""
    lab = Lab.objects.create(name="Pulse", slug="pulse")
    grant = ContentItem.objects.create(
        type=ContentItem.Type.GRANT,
        source="test",
        external_id="g1",
        metadata={"title": "A grant", "ai_fields": {"required_expertise": []}},
    )

    assert team_gap.team_gaps({"target_lab": lab}, [grant]) == []


@pytest.mark.django_db
def test_requirements_come_from_the_verified_extraction_only(db) -> None:
    """An invented requirement talks a team out of a grant they could have won."""
    unverified = ContentItem(
        type=ContentItem.Type.GRANT,
        metadata={"summary": "Requires an environmental health co-investigator."},
    )

    assert team_gap.required_expertise(unverified) == []

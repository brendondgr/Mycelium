"""The "who is this for?" layer — shortlist by cosine, explained by Mylo.

The invariants that matter:

- the shortlist is arithmetic, so it exists with the model down;
- Mylo may drop a shortlisted member, but may never add one;
- what is persisted is a username, not a display name, so a rename lands free;
- a member who leaves the lab stops being named, stale signal or not.
"""

from __future__ import annotations

import json

import pytest
from apps.accounts.models import Lab, LabMembership, Profile
from django.contrib.auth.models import User

from tools.recommendation import member_fit
from tools.recommendation.models import RelevanceScore
from tools.retrieval.models import ContentItem

# Three orthogonal unit vectors — a member "matches" an item only when they share
# an axis, which keeps every expectation below exact rather than approximate.
VEC_A = [1.0, 0.0, 0.0]
VEC_B = [0.0, 1.0, 0.0]
VEC_C = [0.0, 0.0, 1.0]


@pytest.fixture
def lab(db):
    return Lab.objects.create(name="Lab", slug="lab")


def _member(lab, username, vector, *, areas=(), statement=""):
    user = User.objects.create_user(username, first_name=username.title())
    LabMembership.objects.create(user=user, lab=lab)
    Profile.objects.filter(user=user).update(
        embedding=vector,
        interests={"areas": list(areas), "statement": statement, "keywords": []},
    )
    user.refresh_from_db()
    return user


def _item(external_id, vector, *, title="Item", abstract="", ctype=None):
    return ContentItem.objects.create(
        type=ctype or ContentItem.Type.PAPER,
        source="test",
        external_id=external_id,
        metadata={"title": title, "abstract": abstract},
        embedding=vector,
    )


def _score(lab, item, *, match=80):
    return RelevanceScore.objects.create(
        content=item,
        target_lab=lab,
        score=0.9,
        signals={"suggested": True, "match_percent": match},
    )


def _no_llm(_prompt):
    """A model that is simply not there."""
    return None


# --------------------------------------------------------------------------- #
# Signal 1 — the shortlist
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_shortlist_ranks_by_cosine_and_drops_below_the_floor(lab) -> None:
    ana = _member(lab, "ana", VEC_A)
    bo = _member(lab, "bo", VEC_B)
    candidates = member_fit.build_candidates([ana, bo])

    ranked = member_fit.rank_members(VEC_A, candidates)

    assert [c.username for c, _ in ranked] == ["ana"]  # bo is orthogonal → 0.0
    assert ranked[0][1] == pytest.approx(1.0)


@pytest.mark.django_db
def test_shortlist_is_capped(lab) -> None:
    members = [_member(lab, f"m{i}", VEC_A) for i in range(5)]
    candidates = member_fit.build_candidates(members)
    assert len(member_fit.rank_members(VEC_A, candidates, limit=2)) == 2


@pytest.mark.django_db
def test_a_member_with_no_vector_is_never_a_candidate(lab) -> None:
    user = User.objects.create_user("vectorless")
    LabMembership.objects.create(user=user, lab=lab)
    assert member_fit.build_candidates([user], embed_missing=False) == []


# --------------------------------------------------------------------------- #
# Signal 2 — Mylo
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_mylo_writes_the_reason(lab) -> None:
    ana = _member(lab, "ana", VEC_A, areas=["mycology"])
    item = _item("p1", VEC_A, title="Fungal networks")
    score = _score(lab, item)

    def complete(_prompt):
        return json.dumps(
            {
                "items": [
                    {"item": 1, "members": [{"member": 1, "why": "Ana's exact area."}]}
                ]
            }
        )

    fits = member_fit.compute_member_fit(
        [score], member_fit.build_candidates([ana]), complete=complete
    )
    row = fits[str(item.id)][0]
    assert row == {
        "username": "ana",
        "fit": 100,
        "reason": "Ana's exact area.",
        "source": "llm",
    }


@pytest.mark.django_db
def test_mylo_may_drop_a_shortlisted_member_but_never_add_one(lab) -> None:
    ana = _member(lab, "ana", VEC_A)
    bo = _member(lab, "bo", [0.9, 0.44, 0.0])  # close enough to clear the floor
    item = _item("p1", VEC_A)
    score = _score(lab, item)

    def complete(_prompt):
        # Names member 1 only, plus an out-of-range member the shortlist never had.
        return json.dumps(
            {
                "items": [
                    {
                        "item": 1,
                        "members": [
                            {"member": 1, "why": "Squarely Ana's."},
                            {"member": 9, "why": "Nobody."},
                        ],
                    }
                ]
            }
        )

    candidates = member_fit.build_candidates([ana, bo])
    assert len(member_fit.rank_members(VEC_A, candidates)) == 2  # both shortlisted

    fits = member_fit.compute_member_fit([score], candidates, complete=complete)
    named = [row["username"] for row in fits[str(item.id)]]
    assert named == ["ana"]  # bo dropped by Mylo; the phantom member never lands


@pytest.mark.django_db
def test_the_layer_survives_the_model_being_down(lab) -> None:
    ana = _member(lab, "ana", VEC_A, areas=["mycelial networks"])
    item = _item("p1", VEC_A, title="Mycelial networks in soil")
    score = _score(lab, item)

    fits = member_fit.compute_member_fit(
        [score], member_fit.build_candidates([ana]), complete=_no_llm
    )
    row = fits[str(item.id)][0]
    assert row["source"] == "similarity"
    assert row["fit"] == 100
    # The deterministic reason names the overlap it actually found.
    assert "mycelial networks" in row["reason"]


@pytest.mark.django_db
def test_an_item_with_no_embedding_is_skipped(lab) -> None:
    ana = _member(lab, "ana", VEC_A)
    item = ContentItem.objects.create(
        type=ContentItem.Type.PAPER, source="test", external_id="nov", metadata={}
    )
    score = _score(lab, item)
    assert (
        member_fit.compute_member_fit(
            [score], member_fit.build_candidates([ana]), complete=_no_llm
        )
        == {}
    )


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_annotate_persists_and_then_clears_a_stale_signal(lab) -> None:
    ana = _member(lab, "ana", VEC_A)
    item = _item("p1", VEC_A)
    score = _score(lab, item)

    member_fit.annotate_member_fit(
        {"target_lab": lab}, [ana], complete=_no_llm
    )
    score.refresh_from_db()
    assert [row["username"] for row in score.signals["member_fit"]] == ["ana"]

    # Ana's interests move away from this item entirely; the layer must not keep
    # asserting a recommendation nobody re-derived.
    Profile.objects.filter(user=ana).update(embedding=VEC_C)
    ana.refresh_from_db()
    member_fit.annotate_member_fit({"target_lab": lab}, [ana], complete=_no_llm)
    score.refresh_from_db()
    assert "member_fit" not in score.signals


@pytest.mark.django_db
def test_annotate_for_target_resolves_the_labs_members(lab) -> None:
    from tools.recommendation.targets import target_for_lab

    ana = _member(lab, "ana", VEC_A)
    item = _item("p1", VEC_A)
    score = _score(lab, item)

    written = member_fit.annotate_for_target(target_for_lab(lab), complete=_no_llm)

    assert written[ContentItem.Type.PAPER] == 1
    score.refresh_from_db()
    assert score.signals["member_fit"][0]["username"] == ana.get_username()


@pytest.mark.django_db
def test_annotate_for_target_never_raises(lab, monkeypatch) -> None:
    from tools.recommendation.targets import target_for_lab

    _member(lab, "ana", VEC_A)
    _score(lab, _item("p1", VEC_A))

    def boom(*_args, **_kwargs):
        raise RuntimeError("embedder exploded")

    monkeypatch.setattr(member_fit, "annotate_member_fit", boom)
    assert member_fit.annotate_for_target(target_for_lab(lab)) == {}


@pytest.mark.django_db
def test_a_departed_member_is_not_named_at_read_time(lab) -> None:
    """A stale signal must not outlive the membership it referred to."""
    from tools.delivery.views import _recommended_for

    ana = _member(lab, "ana", VEC_A)
    gone = _member(lab, "gone", VEC_A)
    item = _item("p1", VEC_A)
    score = _score(lab, item)
    score.signals["member_fit"] = [
        {"username": "ana", "fit": 90, "reason": "r", "source": "llm"},
        {"username": "gone", "fit": 88, "reason": "r", "source": "llm"},
    ]
    score.save(update_fields=["signals"])

    LabMembership.objects.filter(user=gone).delete()
    rows = _recommended_for([score], [ana.id], {})[str(item.id)]
    assert [row["username"] for row in rows] == ["ana"]
    assert rows[0]["name"] == "Ana"  # resolved live, not from the stored signal


@pytest.mark.django_db
def test_a_written_rationale_carries_forward(lab) -> None:
    """The nightly run explains the day's arrivals, not the whole feed again."""
    ana = _member(lab, "ana", VEC_A)
    old = _item("old", VEC_A)
    old_score = _score(lab, old, match=90)
    new = _item("new", VEC_A)
    new_score = _score(lab, new, match=80)

    calls: list[str] = []

    def complete(prompt):
        calls.append(prompt)
        return json.dumps(
            {"items": [{"item": 1, "members": [{"member": 1, "why": "Fresh line."}]}]}
        )

    candidates = member_fit.build_candidates([ana])
    fits = member_fit.compute_member_fit(
        [old_score, new_score],
        candidates,
        complete=complete,
        prior={str(old.id): {"ana": "Yesterday's line."}},
    )

    # Only the unexplained item was sent to the model …
    assert len(calls) == 1
    assert "new" not in calls[0] or str(old.id) not in calls[0]
    # … and yesterday's wording is preserved rather than churned.
    assert fits[str(old.id)][0]["reason"] == "Yesterday's line."
    assert fits[str(old.id)][0]["source"] == "llm"
    assert fits[str(new.id)][0]["reason"] == "Fresh line."


@pytest.mark.django_db
def test_a_deterministic_reason_does_not_block_a_later_llm_pass(lab) -> None:
    ana = _member(lab, "ana", VEC_A)
    item = _item("p1", VEC_A)
    score = _score(lab, item)

    # First pass with the model down leaves a similarity reason …
    member_fit.annotate_member_fit({"target_lab": lab}, [ana], complete=_no_llm)
    score.refresh_from_db()
    assert score.signals["member_fit"][0]["source"] == "similarity"

    # … which must not be carried forward as if Mylo had written it.
    def complete(_prompt):
        return json.dumps(
            {"items": [{"item": 1, "members": [{"member": 1, "why": "Mylo's line."}]}]}
        )

    member_fit.annotate_member_fit({"target_lab": lab}, [ana], complete=complete)
    score.refresh_from_db()
    assert score.signals["member_fit"][0]["reason"] == "Mylo's line."
    assert score.signals["member_fit"][0]["source"] == "llm"

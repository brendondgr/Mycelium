"""Plan 08 — applying what a person said yes to, and undoing it exactly.

The person's own words change only when the person says so: every write to
``Profile.interests`` from this feature traces to one answered question, goes
through the interests contract, carries its provenance, and is undone to
exactly what was there. Project state changes only through a proposal an
editor accepts.
"""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Profile
from apps.ambient import apply, review
from apps.ambient.models import (
    AppliedChange,
    Finding,
    PendingSuggestion,
)
from apps.knowledge.models import Concept, Facet, Scope

AMBIENT = Path(__file__).resolve().parent.parent


@pytest.fixture
def ada(db):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.interests = {
        "version": 2,
        "statement": "I study medical imaging.",
        "areas": ["medical imaging", "segmentation", "radiomics"],
        "keywords": ["mri"],
        "clusters": [
            {
                "id": "c-imaging",
                "label": "Imaging",
                "areas": ["medical imaging", "segmentation"],
            },
            {"id": "c-radiomics", "label": "Radiomics", "areas": ["radiomics"]},
        ],
    }
    profile.save()
    return user


def _answered(
    user, choice, topic="conformal prediction", *, budget=None, correction=""
):
    concept = Concept.objects.create(
        label=topic, facet=Facet.METHOD, scope=Scope.GLOBAL
    )
    finding = Finding.objects.create(
        user=user,
        concept=concept,
        topic=topic,
        understanding_kind="current_curiosity",
        relation="interested_in",
        visibility="personal",
        outcome="suggest",
        reason="consistent",
        budget=budget or {},
        decided_at=timezone.now(),
    )
    return PendingSuggestion.objects.create(
        user=user,
        kind="interest",
        finding=finding,
        concept=concept,
        relation="interested_in",
        topic=topic,
        choices=[{"key": choice, "label": choice}],
        state="answered",
        verdict="corrected" if correction else "confirmed",
        choice=choice,
        correction=correction,
        answered_on="dm",
        answered_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=14),
    )


def _interests(user):
    return Profile.objects.get(user=user).interests


def test_add_to_my_interests_goes_into_the_theme_with_room(ada):
    _answered(ada, "interests")
    assert apply.apply_answers() == {"applied": 1, "nothing_to_do": 0, "refused": 0}
    after = _interests(ada)
    assert after["areas"][-1] == "conformal prediction"
    radiomics = next(c for c in after["clusters"] if c["id"] == "c-radiomics")
    assert radiomics["areas"] == ["radiomics", "conformal prediction"]
    [trail] = after["sources"]["ambient"]
    assert trail["provenance"] == "stated" and trail["surface"] == "dm"
    change = AppliedChange.objects.get()
    assert change.kind == "profile_edit" and change.field == "interests.areas"
    # Untouched fields are byte-identical.
    assert after["statement"] == "I study medical imaging." and after["keywords"] == [
        "mri"
    ]


def test_a_new_theme_and_its_exact_undo(ada):
    before = dict(_interests(ada))
    _answered(ada, "theme")
    apply.apply_answers()
    after = _interests(ada)
    assert [c["id"] for c in after["clusters"]] == [
        "c-imaging",
        "c-radiomics",
        "c-conformal-prediction",
    ]
    change = AppliedChange.objects.get()
    review.undo(change, by=ada)
    restored = _interests(ada)
    assert restored["areas"] == before["areas"]
    assert restored["clusters"] == before["clusters"]


def test_a_new_theme_on_an_unclustered_profile_keeps_the_implicit_one(db):
    user = User.objects.create_user("bo", "bo@example.org", "pw")
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.interests = {"version": 1, "areas": ["ecology"]}
    profile.save()
    _answered(user, "theme", "coral reefs")
    apply.apply_answers()
    clusters = _interests(user)["clusters"]
    assert [c["id"] for c in clusters] == ["c-all", "c-coral-reefs"]
    assert clusters[0]["areas"] == ["ecology"]


def test_a_swap_replaces_only_the_named_stale_theme(ada):
    _answered(
        ada,
        "swap",
        budget={"swap_candidate": {"id": "c-radiomics", "label": "Radiomics"}},
    )
    apply.apply_answers()
    after = _interests(ada)
    assert "radiomics" not in after["areas"]
    assert [c["id"] for c in after["clusters"]] == [
        "c-imaging",
        "c-conformal-prediction",
    ]


@pytest.mark.parametrize(
    ("choice", "field", "expected"),
    [
        ("skill", "skills", ["kriging"]),
        ("learning", "learning_goals", ["kriging"]),
        ("preference", "preferences", ["kriging"]),
        ("direction", "trajectory", {"direction": "kriging"}),
    ],
)
def test_the_other_fields(ada, choice, field, expected):
    _answered(ada, choice, "kriging")
    apply.apply_answers()
    assert _interests(ada)[field] == expected


def test_a_correction_is_written_in_the_persons_words(ada):
    _answered(ada, "skill", "kriging", correction="universal kriging")
    apply.apply_answers()
    assert _interests(ada)["skills"] == ["universal kriging"]


def test_already_there_is_nothing_to_do(ada):
    _answered(ada, "interests", "radiomics")
    assert apply.apply_answers()["nothing_to_do"] == 1
    assert not AppliedChange.objects.exists()


def test_the_contract_refuses_a_seventh_theme(ada):
    profile = Profile.objects.get(user=ada)
    areas = [f"area {i}" for i in range(6)]
    profile.interests = {
        "version": 2,
        "areas": areas,
        "clusters": [
            {"id": f"c{i}", "label": f"T{i}", "areas": [a]} for i, a in enumerate(areas)
        ],
    }
    profile.save()
    before = dict(_interests(ada))
    _answered(ada, "theme")
    assert apply.apply_answers()["refused"] == 1
    assert _interests(ada) == before


def test_an_undo_never_throws_away_a_later_edit_of_the_persons(ada):
    _answered(ada, "skill", "kriging")
    apply.apply_answers()
    profile = Profile.objects.get(user=ada)
    profile.interests = {**profile.interests, "skills": ["kriging", "variograms"]}
    profile.save()
    with pytest.raises(ValueError):
        review.undo(AppliedChange.objects.get(), by=ada)
    assert _interests(ada)["skills"] == ["kriging", "variograms"]


def test_each_answer_is_applied_once(ada):
    _answered(ada, "skill", "kriging")
    apply.apply_answers()
    assert apply.apply_answers() == {"applied": 0, "nothing_to_do": 0, "refused": 0}


def test_a_no_or_not_now_writes_nothing(ada):
    s = _answered(ada, "interests")
    PendingSuggestion.objects.filter(pk=s.pk).update(verdict="rejected", choice="no")
    before = dict(_interests(ada))
    apply.apply_answers()
    assert _interests(ada) == before


def test_the_applier_is_the_only_writer_of_a_profile_in_this_app():
    """Acceptance: grep for writes to ``interests`` — the only one is here."""
    writers = []
    for path in sorted(AMBIENT.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "interests":
                        writers.append(path.name)
    assert set(writers) <= {"apply.py"}, writers

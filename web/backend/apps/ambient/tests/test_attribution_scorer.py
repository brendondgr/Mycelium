"""The attribution rule, exhaustively, without a database.

The scorer is pure on purpose: the rule that decides which project a sentence
is filed under is the part most worth pinning down, and it should be testable
without fixtures. The cases that matter most are the ones where the honest
answer is "unresolved" — two projects that share vocabulary, a signal that is
suggestive but not decisive — because guessing is the failure mode.
"""

import pytest

from apps.ambient.attribution import (
    Candidate,
    Context,
    phrase_match,
    score,
)

IMAGING = Candidate(
    project_id="img",
    name="Imaging pipeline",
    aliases=("IMG-seg",),
    entities=("BraTS 2021", "conformal prediction", "MICCAI"),
    member_ids=frozenset({1, 2}),
)
ANNOTATION = Candidate(
    project_id="ann",
    name="Annotation study",
    aliases=("the labelling study",),
    entities=("annotation cost", "inter-rater agreement", "MICCAI"),
    member_ids=frozenset({1, 3}),
)
BOTH = [IMAGING, ANNOTATION]


@pytest.fixture(autouse=True)
def _defaults(settings):
    settings.AMBIENT_ATTRIBUTION_FLOOR = 0.6
    settings.AMBIENT_ATTRIBUTION_MARGIN = 0.25
    settings.AMBIENT_CONTINUITY_MINUTES = 30
    settings.AMBIENT_THREAD_OVERRIDE = 0.9


# -- matching ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase,text,expected",
    [
        ("Imaging pipeline", "the imaging pipeline is broken again", "exact"),
        ("Imaging pipeline", "the IMAGING-PIPELINE is broken", "exact"),
        ("Imaging pipeline", "the pipeline for imaging is broken", "fuzzy"),
        ("Imaging pipeline", "imaging pipelines are slow", "fuzzy"),
        ("Imaging pipeline", "imaging is slow", ""),
        ("segmentation", "the segmentaton step failed", "fuzzy"),
        ("IMG-seg", "IMG seg is done", "exact"),
        ("ML", "ML is everywhere", ""),  # too short to mean anything
    ],
)
def test_phrase_matching(phrase, text, expected):
    from apps.ambient.attribution import fold

    assert phrase_match(phrase, fold(text)) == expected


# -- the acceptance criteria ---------------------------------------------------------


def test_naming_a_project_alias_attributes_with_high_confidence():
    result = score(BOTH, Context(text="IMG-seg finally converged last night"))
    assert result.project_id == "img"
    assert result.confidence >= 0.9
    assert result.matched["img"] == ["IMG-seg"]


def test_two_plausible_projects_and_no_margin_is_left_unresolved():
    """MICCAI is on both projects' venue lists — it cannot decide between them."""
    result = score(
        BOTH, Context(text="we should push harder for MICCAI this cycle and more")
    )
    assert not result.resolved
    assert result.project_id is None
    assert result.confidence == 0.0


def test_naming_both_projects_is_unresolved():
    result = score(
        BOTH,
        Context(text="the imaging pipeline feeds the annotation study, so both slip"),
    )
    assert result.decided_by == "no_margin"


def test_shared_vocabulary_alone_does_not_decide():
    """'imaging' is part of a name, not the name."""
    result = score(BOTH, Context(text="imaging results look noisy today"))
    assert not result.resolved
    assert result.decided_by == "below_floor"


ANNOTATION_RICH = Candidate(
    project_id="ann",
    name="Annotation study",
    entities=("annotation cost", "inter-rater agreement", "rater pool"),
    member_ids=frozenset({1, 3}),
)


def test_three_distinctive_entities_can_decide_alone():
    result = score(
        [IMAGING, ANNOTATION_RICH],
        Context(
            text="the annotation cost is killing us, inter-rater agreement is "
            "still low and the rater pool is thin"
        ),
    )
    assert result.project_id == "ann"
    assert result.scores["ann"]["entities"] == pytest.approx(0.6)


def test_two_entities_alone_are_suggestive_not_decisive():
    """Conservative by design (OD-03b) — two matches need one more signal."""
    text = "the annotation cost is killing us and inter-rater agreement is low"
    alone = score(BOTH, Context(text=text))
    assert not alone.resolved
    assert alone.scores["ann"]["entities"] == pytest.approx(0.5)

    helped = score(BOTH, Context(text=text, hinted_project_id="ann"))
    assert helped.project_id == "ann"


def test_no_candidates_is_its_own_answer():
    result = score([], Context(text="anything at all"))
    assert result.decided_by == "no_candidates"


# -- signals that raise confidence but never decide alone -------------------------------


def test_a_channel_hint_alone_never_decides():
    result = score(BOTH, Context(text="ok let's do it", hinted_project_id="img"))
    assert not result.resolved
    assert result.scores["img"] == {"hint": 0.3}


def test_a_thread_title_alone_never_decides():
    result = score(
        BOTH,
        Context(
            text="agreed", place_kind="thread", place_label="Imaging pipeline v2"
        ),
    )
    assert not result.resolved
    assert result.scores["img"]["title"] == pytest.approx(0.4)


def test_a_channel_name_is_not_a_title():
    """Only threads and forum posts have titles; a channel called #imaging does not."""
    result = score(
        BOTH, Context(text="agreed", place_kind="channel", place_label="imaging")
    )
    assert "img" not in result.scores


def test_participants_alone_never_decide():
    result = score(BOTH, Context(text="yes", participant_ids=frozenset({2})))
    assert not result.resolved
    assert result.scores["img"]["participants"] == pytest.approx(0.3)


def test_continuity_carries_a_short_follow_up():
    result = score(BOTH, Context(text="yes, today", continuity=("img", 0.0)))
    assert result.project_id == "img"


def test_continuity_fades_below_the_floor():
    result = score(BOTH, Context(text="yes, today", continuity=("img", 10.0)))
    assert not result.resolved


def test_continuity_outside_the_window_says_nothing():
    result = score(BOTH, Context(text="yes", continuity=("img", 45.0)))
    assert "img" not in result.scores


def test_continuity_and_participants_together_can_decide():
    result = score(
        BOTH,
        Context(
            text="yes, today",
            continuity=("img", 10.0),
            participant_ids=frozenset({2}),
        ),
    )
    assert result.project_id == "img"


# -- threads -----------------------------------------------------------------------------


def test_a_thread_inherits_its_opening():
    result = score(
        BOTH,
        Context(text="sounds good", place_kind="thread", inherited_project_id="img"),
    )
    assert result.project_id == "img"


def test_a_thread_that_moves_on_strongly_is_not_held_to_its_opening():
    result = score(
        BOTH,
        Context(
            text="separately — the annotation study needs a new rater",
            place_kind="thread",
            inherited_project_id="img",
        ),
    )
    assert result.project_id == "ann"
    assert "inherited" not in result.scores.get("img", {})


def test_a_passing_mention_does_not_break_inheritance():
    """One shared entity is not strong disagreement."""
    result = score(
        BOTH,
        Context(
            text="annotation cost matters here too",
            place_kind="thread",
            inherited_project_id="img",
        ),
    )
    assert result.project_id == "img"


# -- semantic similarity -------------------------------------------------------------------


def test_semantic_similarity_is_absent_unless_supplied():
    result = score(BOTH, Context(text="nothing named"))
    assert all("semantic" not in parts for parts in result.scores.values())


def test_semantic_similarity_alone_never_decides():
    result = score(
        BOTH, Context(text="nothing named", semantic={"img": 0.95, "ann": 0.2})
    )
    assert result.scores["img"]["semantic"] == pytest.approx(0.5)
    assert not result.resolved


def test_semantic_similarity_can_tip_a_close_call():
    result = score(
        BOTH,
        Context(
            text="nothing named", semantic={"img": 0.8}, hinted_project_id="img"
        ),
    )
    assert result.project_id == "img"


def test_unrelated_similarity_scores_nothing():
    result = score(BOTH, Context(text="x", semantic={"img": 0.2, "ann": float("nan")}))
    assert all("semantic" not in parts for parts in result.scores.values())


# -- what is stored ---------------------------------------------------------------------------


def test_the_stored_form_holds_numbers_and_project_vocabulary_only():
    text = "IMG-seg finally converged after the weekend"
    stored = score(BOTH, Context(text=text)).as_json()
    flat = repr(stored)
    assert "converged" not in flat
    assert "weekend" not in flat
    assert stored["matched"]["img"] == ["IMG-seg"]
    assert stored["decided_by"] == "resolved"


def test_the_floor_and_margin_are_settings(settings):
    settings.AMBIENT_ATTRIBUTION_FLOOR = 0.25
    result = score(BOTH, Context(text="ok", hinted_project_id="img"))
    assert result.project_id == "img"

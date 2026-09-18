"""The work-facet extractor: grounded, repaired once, refused field by field.

Plan CN-02's extractor acceptance: a changed abstract is re-read and an
unchanged one never is; a neutral phrase from the deny-list is refused and the
work keeps its field-specific method; and nothing is invented.
"""

import json

import pytest
from django.contrib.auth.models import User

from apps.accounts.models import AuthorWork
from apps.content import embeddings
from apps.knowledge import works
from apps.knowledge.models import WorkFacets

ABSTRACT = (
    "We detect coral bleaching in drone imagery of shallow reefs. A U-Net "
    "semantic segmentation model is trained on labelled survey mosaics from the "
    "Great Barrier Reef, and a Kalman filter tracks bleaching extent over "
    "repeated surveys. We release the labelled mosaics as a benchmark dataset "
    "for reef monitoring and report accuracy against diver transects."
)

GOOD = {
    "problem": "Detecting coral bleaching in drone imagery of shallow reefs.",
    "method": "A U-Net semantic segmentation model with a Kalman filter tracking "
    "bleaching extent over repeated surveys.",
    "setting": "Labelled drone survey mosaics from the Great Barrier Reef.",
    "reusable": "The labelled mosaics, released as a benchmark dataset.",
    "problem_terms": ["coral bleaching detection"],
    "method_terms": ["semantic segmentation", "Kalman filter"],
    "setting_terms": ["drone survey mosaics"],
    "reusable_terms": ["labelled reef mosaics"],
    "method_neutral": "labelling each pixel of an image and tracking a hidden "
    "quantity through noisy repeated observations",
    "thin": False,
}


@pytest.fixture
def work(db):
    user = User.objects.create_user("ada", "ada@example.org", "pw")
    return AuthorWork.objects.create(
        user=user,
        source="openalex",
        source_id="W1",
        title="Mapping coral bleaching from drones",
        abstract=ABSTRACT,
        year=2024,
        openalex_field_id="23",
    )


class Model:
    """A scripted model: each call returns the next reply and records the prompt."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def __call__(self, system, user):
        self.prompts.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def test_a_good_reply_is_kept_whole_in_one_call(work):
    model = Model(GOOD)
    outcome = works.extract(work, complete=model)
    assert len(model.prompts) == 1
    assert outcome.refused == [] and not outcome.thin
    assert outcome.terms["method"] == ["semantic segmentation", "Kalman filter"]
    assert outcome.method_neutral.startswith("labelling each pixel")
    # Profile-blind: the reader appears nowhere in what the model is asked.
    assert work.user.email not in model.prompts[0]


def test_an_ungrounded_term_is_repaired_once(work):
    bad = {**GOOD, "method_terms": ["semantic segmentation", "transformer attention"]}
    model = Model(bad, GOOD)
    outcome = works.extract(work, complete=model)
    assert len(model.prompts) == 2
    assert "transformer attention" in model.prompts[1]
    assert outcome.refused == []
    assert outcome.attempts == 2


def test_what_is_still_ungrounded_after_the_repair_is_dropped_alone(work):
    bad = {
        **GOOD,
        "setting": "Satellite radar scenes of Antarctic sea ice collected in 1998.",
    }
    outcome = works.extract(work, complete=Model(bad, bad))
    assert outcome.sentences["setting"] == ""
    assert outcome.sentences["problem"] == GOOD["problem"]
    assert outcome.terms["method"] == GOOD["method_terms"]
    assert any(failure.startswith("setting:") for failure in outcome.refused)


@pytest.mark.parametrize(
    "neutral",
    [
        "machine learning",  # a category, not an operation
        "Uses statistics.",
        "segmentation",  # too short to name an operation
        "Semantic Segmentation",  # the method's own name
    ],
)
def test_an_empty_abstraction_is_refused_and_the_method_kept(work, neutral):
    reply = {**GOOD, "method_neutral": neutral}
    outcome = works.extract(work, complete=Model(reply, reply))
    assert outcome.method_neutral == ""
    assert outcome.terms["method"] == GOOD["method_terms"]
    assert any("method_neutral" in failure for failure in outcome.refused)


def test_a_neutral_phrase_may_not_invent_a_number(work):
    reply = {
        **GOOD,
        "method_neutral": "tracking a hidden quantity through 250 noisy observations",
    }
    outcome = works.extract(work, complete=Model(reply, reply))
    assert outcome.method_neutral == ""


def test_too_many_terms_keep_the_first_few(work):
    reply = {
        **GOOD,
        "problem_terms": ["coral bleaching", "reef monitoring", "drone imagery"],
    }
    outcome = works.extract(work, complete=Model(reply, reply))
    assert outcome.terms["problem"] == ["coral bleaching", "reef monitoring"]


def test_a_work_without_an_abstract_is_thin_and_costs_nothing(work):
    work.abstract = "Short."
    model = Model()
    outcome = works.extract(work, complete=model)
    assert outcome.thin and model.prompts == []


def test_an_unreachable_model_means_try_again_later(work):
    assert works.extract(work, complete=Model(ConnectionError("down"))) is None


def test_a_model_lost_mid_repair_keeps_the_first_answer(work):
    bad = {**GOOD, "setting_terms": ["arctic sea ice"]}
    outcome = works.extract(work, complete=Model(bad, ConnectionError("down")))
    assert outcome is not None
    assert outcome.terms["setting"] == []
    assert outcome.terms["method"] == GOOD["method_terms"]


def test_a_reply_that_is_not_json_is_thin(work):
    outcome = works.extract(work, complete=Model("I cannot help.", "Still no."))
    assert outcome.thin
    assert outcome.refused == ["the reply was not one JSON object"]


def test_a_stored_work_is_never_read_twice_unless_its_text_changes(work, embedder):
    assert works.pending([work]) == [work]
    works.store(work, works.extract(work, complete=Model(GOOD)))
    assert works.pending([work]) == []

    work.year = 2025  # nothing the model reads
    work.save()
    assert works.pending([work]) == []

    work.abstract = ABSTRACT + " We also test on Red Sea reefs."
    work.save()
    assert works.pending([work]) == [work]


def test_a_prompt_change_re_reads_only_old_rows(work, embedder, monkeypatch):
    works.store(work, works.extract(work, complete=Model(GOOD)))
    monkeypatch.setattr(works, "PROMPT_VERSION", "w-next")
    assert works.pending([work]) == [work]


def test_storing_embeds_each_facet_separately(work, embedder):
    row = works.store(work, works.extract(work, complete=Model(GOOD)))
    row.refresh_from_db()
    for name in ("problem_vec", "method_vec", "method_neutral_vec", "setting_vec"):
        assert getattr(row, name) is not None, name
    assert row.openalex_field_id == "23"
    assert row.prompt_version == works.PROMPT_VERSION


def test_vectors_missed_while_the_embedder_was_down_are_filled_later(work, embedder):
    embeddings.set_embedder(None)
    row = works.store(work, works.extract(work, complete=Model(GOOD)))
    assert row.method_vec is None
    embeddings.set_embedder(embedder)
    assert works.fill_vectors(WorkFacets.objects.all()) == 5
    row.refresh_from_db()
    assert row.method_vec is not None


def test_extract_many_leaves_out_what_the_model_could_not_read(work):
    other = AuthorWork.objects.create(
        user=work.user, source="openalex", source_id="W2", title="x", abstract=ABSTRACT
    )
    replies = {work.pk: GOOD, other.pk: ConnectionError("down")}

    def model(system, user):
        key = work.pk if "Mapping coral" in user else other.pk
        reply = replies[key]
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply)

    assert set(works.extract_many([work, other], complete=model)) == {work.pk}


@pytest.mark.parametrize(
    "term",
    ["high-dimensional structural representations", "sequential optimization problem"],
)
def test_a_method_term_that_only_describes_is_refused(work, term):
    reply = {**GOOD, "method_terms": ["semantic segmentation", term]}
    outcome = works.extract(work, complete=Model(reply, reply))
    assert outcome.terms["method"] == ["semantic segmentation"]
    assert any("a description, not a name" in f for f in outcome.refused)


def test_a_named_technique_with_generic_words_is_kept(work):
    reply = {**GOOD, "method_terms": ["semantic segmentation model", "Kalman filter"]}
    outcome = works.extract(work, complete=Model(reply))
    assert outcome.terms["method"] == ["semantic segmentation model", "Kalman filter"]

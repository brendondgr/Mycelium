"""Requirement slots: grounded in the call, repaired once, refused per slot.

Plan CN-03's slot acceptance: a call that states nothing yields no slots, not
an unknown; a slot the call does not support is dropped; a role is kept and
never gets a vector; a call is read once per text.
"""

import json

import pytest
from tools.retrieval.models import ContentItem

from apps.collab import slots
from apps.collab.models import RequirementSlots

DESCRIPTION = (
    "This programme funds research on early warning of coral bleaching. Teams "
    "must include expertise in satellite remote sensing and must partner with a "
    "local marine park authority. Projects should use long-term reef survey "
    "data and may apply machine learning to sea surface temperature records."
)

GOOD = {
    "slots": [
        {
            "facet": "problem",
            "text": "early warning of coral bleaching",
            "required": False,
        },
        {"facet": "method", "text": "satellite remote sensing", "required": True},
        {"facet": "role", "text": "local marine park authority", "required": True},
        {"facet": "data", "text": "long-term reef survey data", "required": False},
    ],
    "thin": False,
}


@pytest.fixture
def call(db):
    return ContentItem.objects.create(
        type="grant",
        source="grants",
        external_id="G-1",
        metadata={
            "title": "Reef resilience programme",
            "funder": "Ocean Fund",
            "description": DESCRIPTION,
            "eligibility": "Universities and research institutes.",
        },
    )


class Model:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, system, user):
        self.prompts.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def test_a_good_reply_becomes_slots_in_one_call(call):
    model = Model(GOOD)
    outcome = slots.extract(call, complete=model)
    assert len(model.prompts) == 1 and outcome.refused == []
    assert [(s["facet"], s["required"]) for s in outcome.slots] == [
        ("problem", False),
        ("method", True),
        ("role", True),
        ("data", False),
    ]


def test_an_invented_slot_is_repaired_then_dropped_alone(call):
    bad = {
        **GOOD,
        "slots": GOOD["slots"] + [{"facet": "method", "text": "quantum annealing"}],
    }
    outcome = slots.extract(call, complete=Model(bad, bad))
    assert [s["text"] for s in outcome.slots] == [s["text"] for s in GOOD["slots"]]
    assert any("not in the call" in f for f in outcome.refused)


def test_an_unknown_facet_is_refused(call):
    bad = {"slots": [{"facet": "budget", "text": "coral bleaching"}]}
    outcome = slots.extract(call, complete=Model(bad, bad))
    assert outcome.slots == []


def test_a_call_that_states_nothing_has_no_slots(call, embedder):
    row = slots.store(
        call, slots.extract(call, complete=Model({"slots": [], "thin": False}))
    )
    assert row.status == RequirementSlots.Status.NONE and row.slots == []


def test_too_little_text_is_thin_and_costs_nothing(db):
    item = ContentItem.objects.create(
        type="grant", source="grants", external_id="G-2", metadata={"title": "x"}
    )
    model = Model()
    outcome = slots.extract(item, complete=model)
    assert outcome.thin and model.prompts == []


def test_an_unreachable_model_means_try_again(call):
    assert slots.extract(call, complete=Model(ConnectionError("down"))) is None


def test_roles_get_no_vector_and_the_rest_do(call, embedder):
    row = slots.store(call, slots.extract(call, complete=Model(GOOD)))
    by_facet = {s["facet"]: s for s in row.slots}
    assert "vector" not in by_facet["role"]
    assert by_facet["method"]["vector"]
    assert [s["text"] for s in row.required] == [
        "satellite remote sensing",
        "local marine park authority",
    ]


def test_a_call_is_read_once_per_text(call, embedder):
    calls = []

    def model(system, user):
        calls.append(user)
        return json.dumps(GOOD)

    assert slots.read_calls([call], complete=model).read == 1
    assert slots.read_calls([call], complete=model).read == 0
    call.metadata["description"] = DESCRIPTION + " Applicants may also use drones."
    call.save()
    assert slots.read_calls([call], complete=model).read == 1
    assert len(calls) == 2


def test_the_nightly_read_respects_its_cap(db, embedder):
    items = [
        ContentItem.objects.create(
            type="grant",
            source="grants",
            external_id=f"G-{n}",
            metadata={"title": f"Call {n}", "description": DESCRIPTION},
        )
        for n in range(5)
    ]
    run = slots.read_calls(items, limit=2, complete=Model(GOOD, GOOD))
    assert run.read == 2 and len(slots.pending(items)) == 3


def test_a_wrapped_method_is_unwrapped(call):
    reply = {
        "slots": [
            {"facet": "problem", "text": "early warning of coral bleaching"},
            {"facet": "method", "text": "expertise in satellite remote sensing"},
        ]
    }
    outcome = slots.extract(call, complete=Model(reply))
    assert outcome.slots[1]["text"] == "satellite remote sensing"


def test_a_described_activity_is_not_a_method(call):
    reply = {
        "slots": [
            {"facet": "problem", "text": "early warning of coral bleaching"},
            {"facet": "method", "text": "rigorous data analysis"},
        ]
    }
    outcome = slots.extract(call, complete=Model(reply, reply))
    assert [s["facet"] for s in outcome.slots] == ["problem"]
    assert any("a description, not a method" in f for f in outcome.refused)


def test_a_problem_is_never_required(call):
    reply = {
        "slots": [
            {
                "facet": "problem",
                "text": "early warning of coral bleaching",
                "required": True,
            },
            {"facet": "method", "text": "satellite remote sensing", "required": True},
        ]
    }
    outcome = slots.extract(call, complete=Model(reply))
    assert [s["required"] for s in outcome.slots] == [False, True]


# --- typed text (EXP-2026-11-023) ---------------------------------------------


class Recorder(Model):
    def __init__(self, *replies):
        super().__init__(*replies)
        self.systems = []

    def __call__(self, system, user):
        self.systems.append(system)
        return super().__call__(system, user)


def test_the_funding_call_path_still_reads_with_the_call_prompt(call):
    model = Recorder(GOOD)
    slots.extract(call, complete=model)
    assert model.systems == [slots.SYSTEM]
    assert model.prompts == [
        slots.PROMPT.format(
            max_words=slots.MAX_SLOT_WORDS,
            max_slots=slots.MAX_SLOTS,
            source=slots.source_text(call),
        )
    ]


def test_typed_text_is_read_with_its_own_prompt_and_the_same_checks():
    question = "Who should I collaborate with on ocean modelling using kriging?"
    model = Recorder(
        {
            "slots": [
                {"facet": "problem", "text": "ocean modelling"},
                {"facet": "method", "text": "kriging"},
                {"facet": "data", "text": "Argo float profiles"},
            ]
        },
        {
            "slots": [
                {"facet": "problem", "text": "ocean modelling"},
                {"facet": "method", "text": "kriging"},
            ]
        },
    )
    outcome = slots.extract_need(question, complete=model)
    assert model.systems == [slots.NEED_SYSTEM, slots.NEED_SYSTEM]
    assert "funding call" not in model.prompts[0]
    assert question in model.prompts[0]
    # A slot the text does not contain is repaired away, as for a call.
    assert "Argo float profiles" in model.prompts[1]
    assert [s["text"] for s in outcome.slots] == ["ocean modelling", "kriging"]


@pytest.mark.parametrize(
    ("text", "topic"),
    [
        (
            "Who in the department should I collaborate with on ocean modelling?",
            "ocean modelling",
        ),
        (
            "Who should I collaborate with in the department on reef data; kriging.",
            "reef data; kriging",
        ),
        ("Anyone to work with about  sea ice\nretreat?", "sea ice retreat"),
        ("Hello, can you help me please?", ""),
        ("Who should I collaborate with on it?", ""),
    ],
)
def test_the_typed_topic_is_the_text_after_collaborate_on(text, topic):
    assert slots.typed_topic(text) == topic

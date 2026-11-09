"""Tests for the decision-backend switch (offline: fake HTTP, fake transport)."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from apps.core import decisions
from apps.core.decisions import (
    DecisionError,
    PortConfig,
    PortDecisionClient,
    base_url,
    build_decision_client,
    choice,
    score,
    yesno,
)
from apps.core.models import LLMUsageDaily

LEVELS = ["skip", "file", "skim", "read"]
QUESTIONS = {
    "worth": yesno("Worth it?", true="on topic", false="off topic"),
    "fit": score("How well?", LEVELS),
}


class FakeHttp:
    """Replays ``/v1/models`` and answers posts with a function of the body."""

    def __init__(self, models, answer):
        self.models = models
        self.answer = answer
        self.posts: list[tuple[str, dict]] = []
        self.gets = 0

    def get(self, path):
        assert path == "/v1/models"
        self.gets += 1
        return self.models

    def post(self, path, body):
        self.posts.append((path, body))
        return self.answer(path, body)


DECIDE_MODELS = {
    "models": [{"id": "d3-lite", "revision": "abc123", "default": True}],
    "question_types": ["yesno", "choice", "score"],
}


def _decide_answer(path, body):
    assert path == "/v1/decide"
    out = {}
    for q in body["questions"]:
        if q["type"] == "yesno":
            out[q["id"]] = {"probs": {"yes": 0.8, "no": 0.2}, "top": "yes", "p": 0.8}
        elif q["type"] == "score":
            probs = dict(zip(q["scale"], [0.1, 0.1, 0.2, 0.6], strict=True))
            out[q["id"]] = {
                "probs": probs,
                "top": q["scale"][3],
                "p": 0.6,
                "value": 2.3,
            }
        else:
            names = list(q["options"])
            out[q["id"]] = {"probs": {n: 1 / len(names) for n in names}}
    return {"model": "d3-lite", "revision": "abc123", "answers": out}


def _port(models, answer, **cfg):
    config = PortConfig(url="http://127.0.0.1:5107", **cfg)
    http = FakeHttp(models, answer)
    return PortDecisionClient(config, http=http), http


# -- resolution --------------------------------------------------------------


def _settings(**kw):
    base = dict(DECISION_BACKEND="auto", TYPESAFE_API_KEY="", DECISION_PORT_URL="")
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "kw,expected",
    [
        ({}, "off"),
        ({"TYPESAFE_API_KEY": "k"}, "jev"),
        ({"DECISION_PORT_URL": "http://x"}, "port"),
        ({"TYPESAFE_API_KEY": "k", "DECISION_PORT_URL": "http://x"}, "jev"),
        (
            {
                "DECISION_BACKEND": "port",
                "TYPESAFE_API_KEY": "k",
                "DECISION_PORT_URL": "http://x",
            },
            "port",
        ),
        ({"DECISION_BACKEND": "port"}, "off"),
        ({"DECISION_BACKEND": "jev"}, "off"),
        ({"DECISION_BACKEND": "off", "TYPESAFE_API_KEY": "k"}, "off"),
        ({"DECISION_BACKEND": "typesafe", "TYPESAFE_API_KEY": "k"}, "jev"),
        ({"DECISION_BACKEND": "local", "TYPESAFE_API_KEY": "k"}, "off"),
    ],
)
def test_resolve(kw, expected):
    backend, reason = decisions.resolve(_settings(**kw))
    assert backend == expected
    assert reason


def test_nothing_configured_builds_no_client():
    assert build_decision_client(_settings()) is None


def test_override_still_needs_its_url():
    assert (
        build_decision_client(_settings(TYPESAFE_API_KEY="k"), backend="port") is None
    )


@pytest.mark.parametrize(
    "url", ["http://h:8080", "http://h:8080/", "http://h:8080/v1", "http://h:8080/v1/"]
)
def test_base_url_accepts_the_openai_spelling(url):
    assert base_url(url) == "http://h:8080"


def test_question_specs_validate_sizes():
    with pytest.raises(ValueError):
        score("x", ["only one"])
    with pytest.raises(ValueError):
        choice("x", {"a": None})


# -- decide protocol ---------------------------------------------------------


def test_protocol_and_model_come_from_one_listing():
    client, http = _port(DECIDE_MODELS, _decide_answer)
    assert client.protocol == "decide"
    assert client.model == "decide:d3-lite@abc123"
    client.ask({"x": 1}, QUESTIONS)
    client.ask({"x": 2}, QUESTIONS)
    assert http.gets == 1


def test_decide_answers_take_the_systemone_shapes():
    client, http = _port(DECIDE_MODELS, _decide_answer)
    result = client.ask({"x": 1}, QUESTIONS)
    sent = http.posts[0][1]
    assert sent["model"] == "d3-lite"
    yes_q = next(q for q in sent["questions"] if q["id"] == "worth")
    assert "Answer yes if: on topic" in yes_q["question"]
    assert next(q for q in sent["questions"] if q["id"] == "fit")["scale"] == LEVELS
    answers = result.answers_as_dicts()
    assert answers["worth"] == {"noul": 0.8}
    assert answers["fit"]["probabilities"] == {"0": 0.1, "1": 0.1, "2": 0.2, "3": 0.6}
    assert answers["fit"]["score"] == pytest.approx(2.3)
    assert answers["fit"]["confidence"] == pytest.approx(0.6)
    assert result.backend == "port"
    assert result.model == "decide:d3-lite@abc123"


def test_a_question_the_server_could_not_answer_fails_the_call():
    def answer(path, body):
        return {"answers": {"worth": {"error": "bad", "message": "nope"}}}

    client, _ = _port(DECIDE_MODELS, answer)
    with pytest.raises(DecisionError, match="nope"):
        client.ask({}, {"worth": QUESTIONS["worth"]})


def test_explicit_model_must_be_listed():
    client, _ = _port(DECIDE_MODELS, _decide_answer, model="pplx-decider")
    with pytest.raises(DecisionError, match="pplx-decider"):
        _ = client.model


# -- openai protocol (llama.cpp / vLLM) --------------------------------------


OPENAI_MODELS = {"object": "list", "data": [{"id": "qwen3-4b"}]}


def _logprobs(tokens: dict[str, float]):
    top = [{"token": t, "logprob": math.log(p)} for t, p in tokens.items()]
    return {
        "choices": [{"logprobs": {"content": [{**top[0], "top_logprobs": top}]}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 1},
    }


def _openai_answer(path, body):
    assert path == "/v1/chat/completions"
    assert body["max_tokens"] == 1 and body["logprobs"] is True
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    text = body["messages"][-1]["content"]
    if "Allowed answers: yes, no" in text:
        # Two spellings of yes are one answer; the stray token is ignored.
        return _logprobs({"Yes": 0.5, " yes": 0.1, "no": 0.2, "Maybe": 0.2})
    return _logprobs({"3": 0.4, "2": 0.4, "0": 0.2})


def test_openai_is_detected_without_question_types():
    client, _ = _port(OPENAI_MODELS, _openai_answer)
    assert client.protocol == "openai"
    assert client.model == "openai:qwen3-4b"


def test_openai_reads_the_answer_from_first_token_logprobs():
    client, http = _port(OPENAI_MODELS, _openai_answer)
    result = client.ask({"x": 1}, QUESTIONS)
    answers = result.answers_as_dicts()
    assert answers["worth"]["noul"] == pytest.approx(0.75)  # 0.6 / (0.6 + 0.2)
    assert answers["fit"]["probabilities"] == {"0": 0.2, "1": 0.0, "2": 0.4, "3": 0.4}
    assert answers["fit"]["score"] == pytest.approx(2.0)
    assert result.usage == {"input_tokens": 200, "output_tokens": 2}
    assert len(http.posts) == 2  # one completion per question
    assert all(body["model"] == "qwen3-4b" for _, body in http.posts)


def test_openai_without_any_allowed_token_fails():
    client, _ = _port(OPENAI_MODELS, lambda p, b: _logprobs({"Sure": 1.0}))
    with pytest.raises(DecisionError, match="none of"):
        client.ask({}, {"worth": QUESTIONS["worth"]})


def test_openai_server_without_logprobs_fails_clearly():
    client, _ = _port(OPENAI_MODELS, lambda p, b: {"choices": [{"message": {}}]})
    with pytest.raises(DecisionError, match="logprobs"):
        client.ask({}, {"worth": QUESTIONS["worth"]})


def test_openai_choice_uses_letters():
    def answer(path, body):
        assert "A: alpha" in body["messages"][-1]["content"]
        return _logprobs({"B": 0.9, "A": 0.1})

    client, _ = _port(OPENAI_MODELS, answer)
    result = client.ask({}, {"pick": choice("Which?", {"alpha": None, "beta": None})})
    assert result.answers["pick"]["choice"] == "beta"


# -- jev and the ledger --------------------------------------------------------


def test_jev_receives_the_same_sdk_questions(monkeypatch):
    seen = {}

    class Inner:
        config = SimpleNamespace(model="jev-1.13.0")

        def ask(self, state, questions, *, model=None):
            seen.update(questions)
            return SimpleNamespace(
                model="jev-1.13.0",
                usage={"input_tokens": 5, "output_tokens": 0},
                answers_as_dicts=lambda: {"worth": {"noul": 0.4}},
            )

    from apps.core import systemone

    monkeypatch.setattr(
        systemone, "noul", lambda i, true=None, false=None: ("noul", i, true, false)
    )
    monkeypatch.setattr(
        systemone, "score", lambda i, levels: ("score", i, tuple(levels))
    )
    client = decisions.JevDecisionClient(Inner())
    result = client.ask({}, QUESTIONS)
    assert seen["worth"] == ("noul", "Worth it?", "on topic", "off topic")
    assert seen["fit"] == ("score", "How well?", tuple(LEVELS))
    assert result.answers == {"worth": {"noul": 0.4}} and client.model == "jev-1.13.0"


@pytest.mark.django_db
def test_port_calls_are_counted_in_the_ledger():
    settings = _settings(
        DECISION_BACKEND="port",
        DECISION_PORT_URL="http://127.0.0.1:5107",
        DECISION_PORT_PROTOCOL="auto",
        DECISION_PORT_MODEL="",
        DECISION_PORT_API_KEY="",
        DECISION_PORT_TIMEOUT=5,
    )
    client = build_decision_client(
        settings,
        component="port_rerank.paper",
        http=FakeHttp(DECIDE_MODELS, _decide_answer),
    )
    client.ask({}, QUESTIONS)
    row = LLMUsageDaily.objects.get(component="port_rerank.paper")
    assert row.calls == 1

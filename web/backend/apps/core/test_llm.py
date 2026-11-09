"""Tests for the OpenAI-compatible LLM client (offline, fake transport)."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from apps.core.llm import (
    LLMClient,
    LLMConfig,
    LLMConfigurationError,
    LLMMessage,
    ReasoningLevel,
    ReasoningStyle,
    reasoning_extra_body,
)


class RecordingCompletions:
    """A fake ``client.chat.completions`` that records calls and replays a response."""

    def __init__(self, response=None):
        self.calls: list[dict] = []
        self._response = response or _fake_response()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _fake_response(
    *, content="hi there", reasoning_content="let me think", model="test-model"
):
    message = SimpleNamespace(content=content, reasoning_content=reasoning_content)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(
        model_dump=lambda: {"prompt_tokens": 5, "completion_tokens": 7}
    )
    return SimpleNamespace(choices=[choice], model=model, usage=usage)


def _config(**overrides):
    base = dict(base_url="http://x/v1", model="test-model")
    base.update(overrides)
    return LLMConfig(**base)


# -- config -----------------------------------------------------------------


@dataclass
class _Settings:
    LLM_BASE_URL = "http://srv:8001/v1"
    LLM_API_KEY = "EMPTY"
    LLM_MODEL = "qwen3"
    LLM_TIMEOUT = "45"
    LLM_TEMPERATURE = "0.7"
    LLM_MAX_TOKENS = "2048"
    LLM_REASONING = "high"
    LLM_REASONING_STYLE = "thinking"


def test_config_from_settings_parses_and_coerces():
    config = LLMConfig.from_settings(_Settings())

    assert config.base_url == "http://srv:8001/v1"
    assert config.model == "qwen3"
    assert config.timeout == 45.0
    assert config.temperature == 0.7
    assert config.max_tokens == 2048
    assert config.reasoning is ReasoningLevel.HIGH
    assert config.reasoning_style is ReasoningStyle.THINKING


def test_reasoning_level_coerce_rejects_unknown():
    with pytest.raises(LLMConfigurationError):
        ReasoningLevel.coerce("ponder")


def test_reasoning_style_coerce_rejects_unknown():
    with pytest.raises(LLMConfigurationError):
        ReasoningStyle.coerce("vibes")


# -- reasoning -> extra_body mapping ----------------------------------------


@pytest.mark.parametrize(
    "level,expected",
    [
        (ReasoningLevel.NONE, {}),
        (ReasoningLevel.LOW, {"reasoning_effort": "low"}),
        (ReasoningLevel.MEDIUM, {"reasoning_effort": "medium"}),
        (ReasoningLevel.HIGH, {"reasoning_effort": "high"}),
    ],
)
def test_effort_style_mapping(level, expected):
    assert reasoning_extra_body(level, ReasoningStyle.EFFORT) == expected


@pytest.mark.parametrize(
    "level,enabled",
    [
        (ReasoningLevel.NONE, False),
        (ReasoningLevel.LOW, True),
        (ReasoningLevel.HIGH, True),
    ],
)
def test_thinking_style_mapping(level, enabled):
    assert reasoning_extra_body(level, ReasoningStyle.THINKING) == {
        "chat_template_kwargs": {"enable_thinking": enabled}
    }


# -- request payload --------------------------------------------------------


def test_complete_sends_reasoning_effort_and_defaults():
    completions = RecordingCompletions()
    client = LLMClient(_config(reasoning=ReasoningLevel.HIGH), completions=completions)

    client.complete("hello")

    (call,) = completions.calls
    assert call["model"] == "test-model"
    assert call["messages"] == [{"role": "user", "content": "hello"}]
    assert call["temperature"] == 0.2
    # No cap is sent unless one is configured (D-6).
    assert "max_tokens" not in call
    assert call["extra_body"] == {"reasoning_effort": "high"}


def test_complete_per_call_reasoning_overrides_default():
    completions = RecordingCompletions()
    client = LLMClient(_config(reasoning=ReasoningLevel.LOW), completions=completions)

    client.complete("hello", reasoning="high")

    assert completions.calls[0]["extra_body"] == {"reasoning_effort": "high"}


def test_complete_none_reasoning_omits_extra_body_in_effort_style():
    completions = RecordingCompletions()
    client = LLMClient(_config(), completions=completions)

    client.complete("hello", reasoning=ReasoningLevel.NONE)

    assert "extra_body" not in completions.calls[0]


def test_thinking_style_toggles_enable_thinking():
    completions = RecordingCompletions()
    client = LLMClient(
        _config(reasoning_style=ReasoningStyle.THINKING), completions=completions
    )

    client.complete("hello", reasoning=ReasoningLevel.NONE)

    assert completions.calls[0]["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_caller_extra_body_merges_chat_template_kwargs():
    completions = RecordingCompletions()
    client = LLMClient(
        _config(reasoning_style=ReasoningStyle.THINKING), completions=completions
    )

    client.complete(
        "hello",
        reasoning=ReasoningLevel.HIGH,
        extra_body={"chat_template_kwargs": {"max_thinking_tokens": 100}},
    )

    assert completions.calls[0]["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True, "max_thinking_tokens": 100}
    }


def test_message_normalization_accepts_objects_and_dicts():
    completions = RecordingCompletions()
    client = LLMClient(_config(), completions=completions)

    client.complete(
        [
            LLMMessage(role="system", content="be terse"),
            {"role": "user", "content": "hi"},
        ]
    )

    assert completions.calls[0]["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ]


def test_tools_passed_through_when_present():
    completions = RecordingCompletions()
    client = LLMClient(_config(), completions=completions)
    tool = {"type": "function", "function": {"name": "lookup"}}

    client.complete("hi", tools=[tool])

    assert completions.calls[0]["tools"] == [tool]


def test_complete_requires_a_model():
    client = LLMClient(_config(model=""), completions=RecordingCompletions())

    with pytest.raises(LLMConfigurationError):
        client.complete("hi")


# -- response parsing -------------------------------------------------------


def test_parse_separates_content_and_reasoning():
    completions = RecordingCompletions()
    client = LLMClient(_config(), completions=completions)

    response = client.complete("hello")

    assert response.content == "hi there"
    assert response.reasoning == "let me think"
    assert response.model == "test-model"
    assert response.finish_reason == "stop"
    assert response.usage == {"prompt_tokens": 5, "completion_tokens": 7}


def test_parse_falls_back_to_reasoning_field():
    # No reasoning_content attribute: simulate a server that uses `reasoning`.
    message = SimpleNamespace(content="answer", reasoning="alt-trace")
    choice = SimpleNamespace(message=message, finish_reason="stop")
    raw = SimpleNamespace(choices=[choice], model="m", usage=None)
    client = LLMClient(_config(), completions=RecordingCompletions(response=raw))

    response = client.complete("hello")

    assert response.content == "answer"
    assert response.reasoning == "alt-trace"
    assert response.usage is None


def test_parse_raises_when_no_choices():
    raw = SimpleNamespace(choices=[], model="m", usage=None)
    client = LLMClient(_config(), completions=RecordingCompletions(response=raw))

    with pytest.raises(LLMConfigurationError):
        client.complete("hello")


# -- output cap, tool calls, streaming (Mylo agent groundwork) -------------


def test_configured_cap_is_sent_and_per_call_cap_overrides():
    completions = RecordingCompletions()
    client = LLMClient(_config(max_tokens=300), completions=completions)
    client.complete("a")
    client.complete("b", max_tokens=50)
    client.complete("c", max_tokens=0)
    assert completions.calls[0]["max_tokens"] == 300
    assert completions.calls[1]["max_tokens"] == 50
    assert "max_tokens" not in completions.calls[2]


def test_config_from_settings_without_cap_means_no_cap():
    class S(_Settings):
        LLM_MAX_TOKENS = 0

    assert LLMConfig.from_settings(S()).max_tokens == 0


def test_tool_calls_are_parsed_and_tool_choice_sent():
    call = SimpleNamespace(
        id="c1",
        function=SimpleNamespace(name="corpus_search", arguments='{"q": "x"}'),
    )
    message = SimpleNamespace(content=None, reasoning_content=None, tool_calls=[call])
    raw = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        model="m",
        usage=None,
    )
    completions = RecordingCompletions(raw)
    client = LLMClient(_config(), completions=completions)
    tools = [{"type": "function", "function": {"name": "corpus_search"}}]
    response = client.complete("q", tools=tools, tool_choice="auto")
    assert completions.calls[0]["tool_choice"] == "auto"
    assert response.content == ""
    (parsed,) = response.tool_calls
    assert (parsed.id, parsed.name) == ("c1", "corpus_search")
    assert parsed.arguments == '{"q": "x"}'


def test_tool_messages_pass_through():
    completions = RecordingCompletions()
    client = LLMClient(_config(), completions=completions)
    calls = [{"id": "c1", "type": "function",
              "function": {"name": "f", "arguments": "{}"}}]
    client.complete([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": calls},
        {"role": "tool", "tool_call_id": "c1", "content": "result"},
    ])
    sent = completions.calls[0]["messages"]
    assert sent[1] == {"role": "assistant", "content": None, "tool_calls": calls}
    assert sent[2] == {"role": "tool", "content": "result", "tool_call_id": "c1"}


def _chunk(content=None, reasoning=None, tool_calls=None, finish=None, usage=None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning,
                            tool_calls=tool_calls)
    return SimpleNamespace(
        model="m",
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)],
        usage=usage,
    )


def test_stream_accumulates_text_thinking_and_calls():
    part = lambda **kw: SimpleNamespace(**kw)  # noqa: E731
    chunks = [
        _chunk(reasoning="hmm"),
        _chunk(content="Hel"),
        _chunk(content="lo"),
        _chunk(tool_calls=[part(index=0, id="c1",
                                function=part(name="f", arguments='{"a"'))]),
        _chunk(tool_calls=[part(index=0, id=None,
                                function=part(name=None, arguments=': 1}'))]),
        _chunk(finish="tool_calls"),
        SimpleNamespace(model="m", choices=[],
                        usage={"prompt_tokens": 3, "completion_tokens": 4}),
    ]
    completions = RecordingCompletions(iter(chunks))
    client = LLMClient(_config(), completions=completions)
    seen = []
    response = client.complete_stream("q", on_delta=lambda k, t: seen.append((k, t)))
    assert completions.calls[0]["stream"] is True
    assert seen == [("thinking", "hmm"), ("text", "Hel"), ("text", "lo")]
    assert response.content == "Hello"
    assert response.reasoning == "hmm"
    assert response.finish_reason == "tool_calls"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 4}
    (call,) = response.tool_calls
    assert (call.name, call.arguments) == ("f", '{"a": 1}')


def test_stream_stops_when_asked():
    chunks = iter([_chunk(content="a"), _chunk(content="b"), _chunk(content="c")])
    client = LLMClient(_config(), completions=RecordingCompletions(chunks))
    seen = []
    response = client.complete_stream(
        "q", on_delta=lambda k, t: seen.append(t), should_stop=lambda: len(seen) >= 2
    )
    assert response.content == "ab"
    assert response.finish_reason == "cancelled"

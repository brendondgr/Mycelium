"""Tests for the TypeSafe System One client (offline, fake transport)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.core import systemone
from apps.core.models import LLMUsageDaily
from apps.core.systemone import (
    SystemOneClient,
    SystemOneConfig,
    SystemOneConfigurationError,
    answer_to_dict,
    is_pinned,
)


class RecordingTransport:
    """A fake ``TypeSafeClient`` that records calls and replays a response."""

    def __init__(self, response=None, error: Exception | None = None):
        self.calls: list[dict] = []
        self._response = response or _fake_response()
        self._error = error

    def system_one(self, state, questions, *, model=None):
        self.calls.append({"state": state, "questions": questions, "model": model})
        if self._error is not None:
            raise self._error
        return self._response


def _fake_response(*, input_tokens=120, output_tokens=None, model="jev-1.13.0"):
    return SimpleNamespace(
        model=model,
        request_id="req-1",
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        answers={
            "worth": SimpleNamespace(noul=0.83),
            "fit": SimpleNamespace(
                score=2.4,
                confidence=0.7,
                probabilities={0: 0.0, 1: 0.1, 2: 0.4, 3: 0.5},
                legend={0: "skip", 1: "file", 2: "skim", 3: "read"},
            ),
        },
    )


def _config(**overrides):
    base = dict(api_key="k", model="jev-1.13.0")
    base.update(overrides)
    return SystemOneConfig(**base)


# -- config -----------------------------------------------------------------


def test_config_from_settings_reads_the_typesafe_group():
    settings = SimpleNamespace(
        TYPESAFE_API_KEY="abc",
        TYPESAFE_MODEL="jev-1.13.0",
        TYPESAFE_BASE_URL="https://example.test",
        TYPESAFE_TIMEOUT="4.5",
        TYPESAFE_MAX_RETRIES="2",
    )
    config = SystemOneConfig.from_settings(settings)
    assert config.api_key == "abc"
    assert config.model == "jev-1.13.0"
    assert config.base_url == "https://example.test"
    assert config.timeout == 4.5
    assert config.max_retries == 2


def test_config_defaults_pin_a_version_not_an_alias():
    config = SystemOneConfig.from_settings(SimpleNamespace())
    assert is_pinned(config.model)


@pytest.mark.parametrize(
    "model,pinned",
    [
        ("jev-1.13.0", True),
        ("jev-latest", False),
        ("JEV-PREVIEW", False),
        ("", False),
        (None, False),
    ],
)
def test_is_pinned(model, pinned):
    assert is_pinned(model) is pinned


# -- the call ---------------------------------------------------------------


@pytest.mark.django_db
def test_ask_passes_state_questions_and_model_to_the_transport():
    transport = RecordingTransport()
    client = SystemOneClient(_config(), transport=transport, component="t")
    result = client.ask({"a": 1}, {"worth": "q"})
    assert transport.calls == [
        {"state": {"a": 1}, "questions": {"worth": "q"}, "model": "jev-1.13.0"}
    ]
    assert result.model == "jev-1.13.0"
    assert result.request_id == "req-1"
    assert result.answers["worth"].noul == 0.83


@pytest.mark.django_db
def test_ask_overrides_model_per_call():
    transport = RecordingTransport()
    client = SystemOneClient(_config(), transport=transport)
    client.ask("s", {"q": "q"}, model="jev-1.12.0")
    assert transport.calls[0]["model"] == "jev-1.12.0"


@pytest.mark.django_db
def test_usage_none_becomes_zero_and_keys_match_the_ledger():
    transport = RecordingTransport(
        _fake_response(input_tokens=None, output_tokens=None)
    )
    result = SystemOneClient(_config(), transport=transport).ask("s", {"q": "q"})
    assert result.usage == {"input_tokens": 0, "output_tokens": 0}


def test_ask_refuses_empty_questions_before_any_call():
    transport = RecordingTransport()
    with pytest.raises(SystemOneConfigurationError):
        SystemOneClient(_config(), transport=transport).ask("s", {})
    assert transport.calls == []


def test_missing_key_fails_before_the_network():
    client = SystemOneClient(_config(api_key=""))
    with pytest.raises(SystemOneConfigurationError, match="TYPESAFE_API_KEY"):
        _ = client.transport


# -- the ledger -------------------------------------------------------------


@pytest.mark.django_db
def test_success_is_counted_with_tokens():
    client = SystemOneClient(_config(), transport=RecordingTransport(), component="exp")
    client.ask("s", {"q": "q"})
    row = LLMUsageDaily.objects.get(component="exp")
    assert (row.calls, row.failures, row.prompt_tokens) == (1, 0, 120)


@pytest.mark.django_db
def test_failure_is_counted_and_reraised():
    transport = RecordingTransport(error=RuntimeError("boom"))
    client = SystemOneClient(_config(), transport=transport, component="exp")
    with pytest.raises(RuntimeError, match="boom"):
        client.ask("s", {"q": "q"})
    row = LLMUsageDaily.objects.get(component="exp")
    assert (row.calls, row.failures) == (1, 1)


@pytest.mark.django_db
def test_response_without_answers_is_a_configuration_error():
    transport = RecordingTransport(SimpleNamespace(model="m", usage=None, answers=None))
    with pytest.raises(SystemOneConfigurationError):
        SystemOneClient(_config(), transport=transport).ask("s", {"q": "q"})


# -- flattening -------------------------------------------------------------


def test_answer_to_dict_flattens_each_type():
    response = _fake_response()
    assert answer_to_dict(response.answers["worth"]) == {"noul": 0.83}
    fit = answer_to_dict(response.answers["fit"])
    assert fit["score"] == 2.4 and fit["confidence"] == 0.7
    assert fit["probabilities"] == {"0": 0.0, "1": 0.1, "2": 0.4, "3": 0.5}
    assert fit["legend"]["3"] == "read"


def test_module_imports_without_the_sdk_installed():
    # The SDK is imported lazily; the module itself must never need it.
    assert systemone.DEFAULT_MODEL == "jev-1.13.0"

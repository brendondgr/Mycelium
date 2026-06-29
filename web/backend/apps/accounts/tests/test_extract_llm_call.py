"""The settings-backed LLM call honors configuration and reports trouble.

Regression guard: a hardcoded ``max_tokens`` here starved reasoning models (the
reasoning trace ate the budget, the JSON answer was truncated to nothing, and the
profile fell back to skills-only). These tests pin the call to the configured
budget and check that silent fallbacks now leave a trace in the logs.
"""

from __future__ import annotations

import logging
from typing import Any

import apps.core.llm as llm_module
from apps.accounts.intake import extract
from apps.accounts.intake.extract import extract_profile_fields


class _FakeResponse:
    def __init__(self, content: str, finish_reason: str | None = None) -> None:
        self.content = content
        self.finish_reason = finish_reason
        self.reasoning = None


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = _FakeResponse('{"areas": ["ai"]}')

    def complete(self, messages: Any, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return self.response


def test_settings_call_does_not_override_token_budget(monkeypatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(llm_module, "build_llm_client", lambda: fake)

    extract._settings_complete("some prompt")

    assert len(fake.calls) == 1
    kwargs = fake.calls[0]["kwargs"]
    # The hardcoded max_tokens/reasoning caps are gone — the configured
    # LLM_MAX_TOKENS / LLM_REASONING drive the request instead.
    assert "max_tokens" not in kwargs
    assert "reasoning" not in kwargs


def test_truncated_empty_response_warns(monkeypatch, caplog) -> None:
    fake = _FakeClient()
    fake.response = _FakeResponse("", finish_reason="length")
    monkeypatch.setattr(llm_module, "build_llm_client", lambda: fake)

    with caplog.at_level(logging.WARNING):
        extract._settings_complete("some prompt")

    assert any("LLM_MAX_TOKENS" in record.message for record in caplog.records)


def test_failed_extraction_logs_warning(caplog) -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("connection refused")

    with caplog.at_level(logging.WARNING):
        fields = extract_profile_fields(
            "Ada Lovelace researches recursion.",
            complete=boom,
            fallback=lambda: {"areas": ["fallback"]},
        )

    assert fields["areas"] == ["fallback"]
    assert any("using deterministic fallback" in r.message for r in caplog.records)


def test_unparseable_output_logs_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        extract_profile_fields(
            "Ada Lovelace researches recursion.",
            complete=lambda _p: "I cannot help with that.",
            fallback=lambda: {"areas": ["fallback"]},
        )

    assert any("no parseable JSON" in r.message for r in caplog.records)

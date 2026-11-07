"""The nightly model-call budget (``nightly.model_calls``)."""

from datetime import date
from types import SimpleNamespace

import pytest

from apps.core import llm_budget
from apps.core.llm import LLMClient, LLMConfig
from apps.core.models import LLMUsageDaily

TODAY = date(2026, 11, 7)


class _Completions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        message = SimpleNamespace(content="ok", reasoning_content=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        return SimpleNamespace(choices=[choice], model="m", usage=usage)


def _client():
    completions = _Completions()
    config = LLMConfig(base_url="http://x/v1", api_key="k", model="m")
    return LLMClient(config, completions=completions, component="test"), completions


@pytest.fixture
def nightly(monkeypatch, settings):
    """Inside a nightly run that started with 5 calls already on today's ledger."""
    LLMUsageDaily.objects.create(day=TODAY, component="daytime", calls=5)
    monkeypatch.setenv(llm_budget.ENV_SINCE, TODAY.isoformat())
    monkeypatch.setenv(llm_budget.ENV_BASELINE, "5")
    monkeypatch.setattr(llm_budget, "_warned", False)
    return settings


@pytest.mark.django_db
def test_start_records_the_ledger_so_far():
    LLMUsageDaily.objects.create(day=TODAY, component="a", calls=3)
    LLMUsageDaily.objects.create(day=date(2026, 11, 6), component="a", calls=9)
    assert llm_budget.start(TODAY) == {
        llm_budget.ENV_SINCE: "2026-11-07",
        llm_budget.ENV_BASELINE: "3",
    }


@pytest.mark.django_db
def test_unlimited_never_refuses(nightly, monkeypatch):
    nightly.NIGHTLY_MODEL_CALLS = None
    monkeypatch.setattr("django.utils.timezone.localdate", lambda: TODAY)
    client, completions = _client()
    for _ in range(3):
        client.complete("hi")
    assert completions.calls == 3


@pytest.mark.django_db
def test_budget_refuses_once_spent(nightly, monkeypatch):
    nightly.NIGHTLY_MODEL_CALLS = 2
    monkeypatch.setattr("django.utils.timezone.localdate", lambda: TODAY)
    client, completions = _client()
    client.complete("one")
    client.complete("two")
    with pytest.raises(llm_budget.LLMBudgetExceeded):
        client.complete("three")
    assert completions.calls == 2  # the refused call never reached the API
    # A refusal is not a call: the ledger holds the two real ones only.
    assert llm_budget.used() == 2


@pytest.mark.django_db
def test_outside_the_nightly_run_nothing_is_budgeted(settings, monkeypatch):
    monkeypatch.delenv(llm_budget.ENV_SINCE, raising=False)
    settings.NIGHTLY_MODEL_CALLS = 0
    client, completions = _client()
    client.complete("a person onboarding at noon")
    assert completions.calls == 1
    assert llm_budget.used() is None

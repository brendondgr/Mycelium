"""The LLM ledger records what happened and never changes what the caller sees."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from apps.core import llm_usage
from apps.core.llm import LLMClient, LLMConfig, LLMConfigurationError
from apps.core.models import LLMUsageDaily


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.reasoning_content = None


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.finish_reason = "stop"


class _FakeCompletion:
    def __init__(self, content: str, usage: dict | None) -> None:
        self.choices = [_FakeChoice(content)]
        self.model = "test-model"
        self.usage = usage


class _Completions:
    """Chat-completions stand-in: answers, or raises what it was handed."""

    def __init__(self, *, content="ok", usage=None, error: Exception | None = None):
        self.content = content
        self.usage = usage
        self.error = error
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return _FakeCompletion(self.content, self.usage)


def _client(completions, component="papers") -> LLMClient:
    return LLMClient(
        LLMConfig(base_url="http://llm.invalid/v1", model="test-model"),
        completions=completions,
        component=component,
    )


class RecordTests(TestCase):
    def test_first_call_creates_the_day_row(self):
        llm_usage.record(
            "briefing", ok=True, usage={"prompt_tokens": 120, "completion_tokens": 30}
        )
        row = LLMUsageDaily.objects.get(component="briefing")
        self.assertEqual(row.day, timezone.localdate())
        self.assertEqual(row.calls, 1)
        self.assertEqual(row.failures, 0)
        self.assertEqual(row.prompt_tokens, 120)
        self.assertEqual(row.completion_tokens, 30)
        self.assertEqual(row.total_tokens, 150)

    def test_repeated_calls_accumulate_on_one_row(self):
        for _ in range(3):
            llm_usage.record(
                "papers", ok=True, usage={"prompt_tokens": 10, "completion_tokens": 5}
            )
        llm_usage.record("papers", ok=False)

        self.assertEqual(LLMUsageDaily.objects.filter(component="papers").count(), 1)
        row = LLMUsageDaily.objects.get(component="papers")
        self.assertEqual(row.calls, 4)
        self.assertEqual(row.failures, 1)
        self.assertEqual(row.prompt_tokens, 30)
        self.assertEqual(row.completion_tokens, 15)

    def test_components_are_counted_separately(self):
        llm_usage.record("papers", ok=True)
        llm_usage.record("opportunities", ok=True)
        self.assertEqual(LLMUsageDaily.objects.count(), 2)

    def test_alternate_token_key_spelling_is_read(self):
        llm_usage.record(
            "intake.lab", ok=True, usage={"input_tokens": 7, "output_tokens": 9}
        )
        row = LLMUsageDaily.objects.get(component="intake.lab")
        self.assertEqual((row.prompt_tokens, row.completion_tokens), (7, 9))

    def test_unlabelled_client_still_gets_counted(self):
        llm_usage.record("", ok=True)
        self.assertTrue(
            LLMUsageDaily.objects.filter(
                component=llm_usage.UNKNOWN_COMPONENT
            ).exists()
        )

    def test_recording_never_raises(self):
        # A usage mapping full of nonsense must not propagate anything.
        llm_usage.record("papers", ok=True, usage={"prompt_tokens": "lots"})
        row = LLMUsageDaily.objects.get(component="papers")
        self.assertEqual(row.prompt_tokens, 0)


class ClientInstrumentationTests(TestCase):
    def test_successful_completion_is_recorded_with_its_tokens(self):
        client = _client(
            _Completions(usage={"prompt_tokens": 200, "completion_tokens": 50})
        )
        response = client.complete("hello")

        self.assertEqual(response.content, "ok")
        row = LLMUsageDaily.objects.get(component="papers")
        self.assertEqual(row.calls, 1)
        self.assertEqual(row.failures, 0)
        self.assertEqual(row.prompt_tokens, 200)
        self.assertEqual(row.completion_tokens, 50)

    def test_transport_failure_is_counted_and_still_raises(self):
        client = _client(_Completions(error=RuntimeError("endpoint down")))

        with self.assertRaises(RuntimeError):
            client.complete("hello")

        row = LLMUsageDaily.objects.get(component="papers")
        self.assertEqual((row.calls, row.failures), (1, 1))

    def test_unparseable_response_counts_as_a_failure(self):
        class _NoChoices:
            def create(self, **kwargs):
                return _FakeCompletion("", None).__class__.__new__(
                    _FakeCompletion
                )  # object without .choices

        client = _client(_NoChoices())
        with self.assertRaises((LLMConfigurationError, AttributeError)):
            client.complete("hello")

        row = LLMUsageDaily.objects.get(component="papers")
        self.assertEqual((row.calls, row.failures), (1, 1))

    def test_completion_without_usage_still_counts_the_call(self):
        client = _client(_Completions(usage=None))
        client.complete("hello")
        row = LLMUsageDaily.objects.get(component="papers")
        self.assertEqual((row.calls, row.prompt_tokens), (1, 0))

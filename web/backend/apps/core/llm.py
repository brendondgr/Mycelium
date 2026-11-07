"""OpenAI-compatible LLM client for Mycelium.

This is the shared seam every future LLM-backed feature routes through (the
planner drafter, relevance scoring rationales, digest summaries, report
drafting). It talks to any OpenAI-compatible ``/v1`` endpoint — in particular a
self-hosted **vLLM** server — and exposes structured *reasoning levels* on top
of plain chat completion.

The reasoning parser and any tool definitions are assumed to be configured on
the server already (per the deployment briefing); this client only *sends* the
reasoning control and *reads back* the separated ``reasoning_content`` that a
vLLM reasoning parser emits.

Two design choices mirror the rest of the backend:

* **Lazy import.** The ``openai`` SDK is only imported when a real client is
  built, so importing this module (or the Django app) stays cheap and
  side-effect free — the same pattern as ``neo4j_inspector_from_settings``.
* **Injectable transport.** :class:`LLMClient` takes a ``completions`` object
  with a ``create`` method. Production passes ``openai``'s chat-completions
  resource; tests pass a fake, so the whole client runs offline.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from apps.core import llm_budget, llm_usage


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM client is asked to run without enough configuration."""


class ReasoningLevel(StrEnum):
    """How hard the server should think before answering.

    ``NONE`` disables structured reasoning; the others map onto the server's
    reasoning budget (see :class:`ReasoningStyle` for how they are transmitted).
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def coerce(cls, value: ReasoningLevel | str | None) -> ReasoningLevel:
        if value is None:
            return cls.MEDIUM
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            allowed = ", ".join(level.value for level in cls)
            raise LLMConfigurationError(
                f"unknown reasoning level {value!r}; expected one of: {allowed}"
            ) from exc


class ReasoningStyle(StrEnum):
    """How a :class:`ReasoningLevel` is encoded for the server.

    * ``EFFORT`` — send vLLM's ``reasoning_effort`` (``low``/``medium``/``high``);
      ``NONE`` sends nothing, leaving the server default.
    * ``THINKING`` — toggle ``chat_template_kwargs.enable_thinking`` (the Qwen3
      style), on for any level above ``NONE``.
    """

    EFFORT = "effort"
    THINKING = "thinking"

    @classmethod
    def coerce(cls, value: ReasoningStyle | str | None) -> ReasoningStyle:
        if value is None:
            return cls.EFFORT
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            allowed = ", ".join(style.value for style in cls)
            raise LLMConfigurationError(
                f"unknown reasoning style {value!r}; expected one of: {allowed}"
            ) from exc


@dataclass(frozen=True)
class LLMConfig:
    """Everything needed to reach and steer the endpoint."""

    base_url: str
    api_key: str = "EMPTY"
    model: str = ""
    timeout: float = 60.0
    temperature: float = 0.2
    max_tokens: int = 1024
    reasoning: ReasoningLevel = ReasoningLevel.MEDIUM
    reasoning_style: ReasoningStyle = ReasoningStyle.EFFORT
    # Reaching the server and waiting for a slow answer are different failures.
    # ``timeout`` is generous because generation is slow; a *connect* attempt
    # that takes more than a couple of seconds means the endpoint is unreachable,
    # and callers with a deterministic fallback (onboarding synthesis, clusters,
    # statements) should get there in seconds rather than minutes.
    connect_timeout: float = 5.0
    # The SDK retries twice by default, so an unreachable endpoint costs
    # 3x the timeout per call. Retrying a dead endpoint only delays the
    # fallback; leave retries to the caller.
    max_retries: int = 0

    @classmethod
    def from_settings(cls, settings: Any) -> LLMConfig:
        """Build config from Django settings (the ``LLM_*`` group)."""

        return cls(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            timeout=float(settings.LLM_TIMEOUT),
            temperature=float(settings.LLM_TEMPERATURE),
            max_tokens=int(settings.LLM_MAX_TOKENS),
            reasoning=ReasoningLevel.coerce(settings.LLM_REASONING),
            reasoning_style=ReasoningStyle.coerce(settings.LLM_REASONING_STYLE),
            connect_timeout=float(getattr(settings, "LLM_CONNECT_TIMEOUT", 5.0)),
            max_retries=int(getattr(settings, "LLM_MAX_RETRIES", 0)),
        )


@dataclass(frozen=True)
class LLMMessage:
    """A single chat message."""

    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class LLMResponse:
    """A parsed chat completion.

    ``reasoning`` carries the server's separated reasoning trace when a vLLM
    reasoning parser is active; it is ``None`` when the server returns only an
    answer.
    """

    content: str
    reasoning: str | None = None
    model: str = ""
    finish_reason: str | None = None
    usage: Mapping[str, Any] | None = None
    raw: Any = field(default=None, repr=False)


class ChatCompletions(Protocol):
    """The slice of the OpenAI SDK the client uses (``client.chat.completions``)."""

    def create(self, **kwargs: Any) -> Any: ...


def _normalize_messages(
    messages: str | LLMMessage | Mapping[str, str] | Iterable[Any],
) -> list[dict[str, str]]:
    """Accept a string, one message, or a sequence of messages/dicts."""

    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    if isinstance(messages, LLMMessage):
        return [messages.as_dict()]
    if isinstance(messages, Mapping):
        return [{"role": str(messages["role"]), "content": str(messages["content"])}]

    normalized: list[dict[str, str]] = []
    for item in messages:
        if isinstance(item, LLMMessage):
            normalized.append(item.as_dict())
        elif isinstance(item, Mapping):
            normalized.append(
                {"role": str(item["role"]), "content": str(item["content"])}
            )
        else:
            raise TypeError(f"unsupported message type: {type(item)!r}")
    if not normalized:
        raise LLMConfigurationError("at least one message is required")
    return normalized


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    """Coerce a pydantic/SDK object or dict to a plain mapping, if present."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    for attr in ("model_dump", "to_dict", "dict"):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                return dict(method())
            except TypeError:
                continue
    return None


def reasoning_extra_body(
    level: ReasoningLevel, style: ReasoningStyle
) -> dict[str, Any]:
    """Translate a reasoning level into the OpenAI ``extra_body`` vLLM reads."""

    if style is ReasoningStyle.THINKING:
        enabled = level is not ReasoningLevel.NONE
        return {"chat_template_kwargs": {"enable_thinking": enabled}}
    # EFFORT style: only send a budget when one is requested.
    if level is ReasoningLevel.NONE:
        return {}
    return {"reasoning_effort": level.value}


def _merge_extra_body(
    base: dict[str, Any], override: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Shallow-merge caller overrides over the reasoning-derived body.

    ``chat_template_kwargs`` is merged one level deeper so a caller can add a
    flag without dropping ``enable_thinking``.
    """

    if not override:
        return base
    merged = dict(base)
    for key, value in override.items():
        if (
            key == "chat_template_kwargs"
            and isinstance(value, Mapping)
            and isinstance(merged.get(key), Mapping)
        ):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


class LLMClient:
    """Query an OpenAI-compatible endpoint with structured reasoning levels.

    ``component`` names the calling feature (``papers``, ``briefing``,
    ``intake.clusters``, …). Every completion is counted against it in the daily
    LLM ledger, which is what the nightly analytics report reads to say how many
    calls the run made, how many failed, and what they cost in tokens. The label
    is the only thing a new LLM-backed feature has to supply to appear there.
    """

    def __init__(
        self,
        config: LLMConfig,
        *,
        completions: ChatCompletions | None = None,
        component: str = "",
    ) -> None:
        self.config = config
        self._completions = completions
        self.component = component

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        completions: ChatCompletions | None = None,
        component: str = "",
    ) -> LLMClient:
        return cls(
            LLMConfig.from_settings(settings),
            completions=completions,
            component=component,
        )

    @property
    def completions(self) -> ChatCompletions:
        """The transport, built lazily from the ``openai`` SDK on first use."""

        if self._completions is None:
            self._completions = self._build_completions()
        return self._completions

    def _build_completions(self) -> ChatCompletions:
        import httpx  # lazy (an openai dependency): only needed for a real client
        from openai import OpenAI  # lazy: importing this module needs no SDK

        # Split the budget: a short connect deadline so an unreachable endpoint
        # falls back fast, the full timeout for read/write so a slow model still
        # gets to finish. A single float would apply the long timeout to connect.
        timeout = httpx.Timeout(
            self.config.timeout,
            connect=min(self.config.connect_timeout, self.config.timeout),
        )
        client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key or "EMPTY",
            timeout=timeout,
            max_retries=self.config.max_retries,
        )
        return client.chat.completions

    def complete(
        self,
        messages: str | LLMMessage | Mapping[str, str] | Sequence[Any],
        *,
        model: str | None = None,
        reasoning: ReasoningLevel | str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        extra_body: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion and return the parsed answer + reasoning."""

        resolved_model = model or self.config.model
        if not resolved_model:
            raise LLMConfigurationError(
                "no model configured; set LLM_MODEL or pass model=..."
            )

        level = (
            self.config.reasoning
            if reasoning is None
            else ReasoningLevel.coerce(reasoning)
        )
        body = _merge_extra_body(
            reasoning_extra_body(level, self.config.reasoning_style), extra_body
        )

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": _normalize_messages(messages),
            "temperature": (
                self.config.temperature if temperature is None else temperature
            ),
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
        }
        if tools:
            payload["tools"] = list(tools)
        if body:
            payload["extra_body"] = body
        payload.update(kwargs)

        # The nightly run's budget (``nightly.model_calls``) refuses the call
        # before it is made, so a refusal is neither billed nor counted; every
        # caller already degrades on a failed call. Outside the nightly run this
        # never refuses (see apps.core.llm_budget).
        llm_budget.check()

        # Count the call either way. A failure here is exactly the number the
        # analytics report needs, so the ledger write brackets the request and
        # re-raises untouched — accounting observes, it never intervenes.
        try:
            raw = self.completions.create(**payload)
            response = self._parse(raw, fallback_model=resolved_model)
        except Exception:
            llm_usage.record(self.component, ok=False)
            raise
        llm_usage.record(self.component, ok=True, usage=response.usage)
        return response

    @staticmethod
    def _parse(raw: Any, *, fallback_model: str) -> LLMResponse:
        choices = getattr(raw, "choices", None) or []
        if not choices:
            raise LLMConfigurationError("LLM response contained no choices")
        choice = choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        # vLLM reasoning parsers expose the trace as `reasoning_content`; some
        # OpenAI-compatible servers use `reasoning`. Accept either.
        reasoning = None
        if message is not None:
            reasoning = getattr(message, "reasoning_content", None) or getattr(
                message, "reasoning", None
            )
        return LLMResponse(
            content=content or "",
            reasoning=reasoning,
            model=getattr(raw, "model", "") or fallback_model,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=_as_mapping(getattr(raw, "usage", None)),
            raw=raw,
        )


def build_llm_client(
    settings: Any | None = None,
    *,
    completions: ChatCompletions | None = None,
    component: str = "",
) -> LLMClient:
    """Convenience factory. Defaults to Django settings when none are given.

    Pass ``component`` so the calls show up under a meaningful name in the daily
    LLM ledger; unlabelled clients are counted as ``unlabelled``.
    """

    if settings is None:
        from django.conf import settings as django_settings

        settings = django_settings
    return LLMClient.from_settings(
        settings, completions=completions, component=component
    )

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

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from apps.core import llm_budget, llm_usage


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM client is asked to run without enough configuration."""


class LLMServerError(RuntimeError):
    """A model server refused or failed a call (raised by the ``llmkit``
    bridge; the OpenAI-compatible client raises the SDK's own errors, which
    :func:`is_unavailable_error` and :func:`is_context_length_error` read too).
    """

    def __init__(self, message: str, *, server: str = "") -> None:
        super().__init__(message)
        self.server = server


class LLMUnavailableError(LLMServerError):
    """The server could not answer now: unreachable, timed out, overloaded,
    rate-limited or a 5xx. Another server might."""


class LLMContextLengthError(LLMServerError):
    """The prompt does not fit the model's context window."""


class LLMRequestError(LLMServerError):
    """The server rejected the request itself; another server would too."""


_CONTEXT_PHRASES = (
    "context length", "context_length", "maximum context", "context window",
    "prompt is too long", "too many tokens", "input is too long",
    "exceeds the context",
)


def is_context_length_error(exc: BaseException) -> bool:
    """Whether ``exc`` says the prompt overflowed the model's window."""
    if isinstance(exc, LLMContextLengthError):
        return True
    if isinstance(exc, LLMServerError):
        return False
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    return status in (400, 413, 422) and any(p in text for p in _CONTEXT_PHRASES)


def is_unavailable_error(exc: BaseException) -> bool:
    """Whether another server might succeed where this call failed."""
    if isinstance(exc, LLMUnavailableError):
        return True
    if isinstance(exc, (LLMServerError, LLMConfigurationError)):
        return False
    name = type(exc).__name__
    if name in ("APIConnectionError", "APITimeoutError", "ConnectError",
                "ConnectTimeout", "ReadTimeout", "TimeoutException",
                "RemoteProtocolError"):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


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
    #: Output cap per reply, thinking included. ``0`` sends no ``max_tokens``
    #: at all (the instance default, ``llm.max_tokens``).
    max_tokens: int = 0
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
            max_tokens=int(getattr(settings, "LLM_MAX_TOKENS", 0) or 0),
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
class ToolCall:
    """One function call the model asked for. ``arguments`` is the raw JSON
    text the server sent; parsing (and repairing) it is the caller's job."""

    id: str
    name: str
    arguments: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


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
    tool_calls: tuple[ToolCall, ...] = ()
    #: Reasoning state a server needs back verbatim on the next turn (Anthropic
    #: thinking signatures, Gemini thought signatures): ``{"kind", "blocks"}``.
    #: Never parsed; ``None`` for OpenAI-compatible servers.
    opaque: Mapping[str, Any] | None = field(default=None, repr=False)
    #: The server that answered (``[llm.providers.<name>]``; ``local`` is the
    #: ``.env`` endpoint). Empty for a client built outside the registry.
    server: str = ""


class ChatCompletions(Protocol):
    """The slice of the OpenAI SDK the client uses (``client.chat.completions``)."""

    def create(self, **kwargs: Any) -> Any: ...


#: Message keys passed through as they are, for tool-calling conversations:
#: an assistant turn's ``tool_calls`` and a tool result's ``tool_call_id``.
_PASSTHROUGH_KEYS = ("tool_calls", "tool_call_id", "name")


def _mapping_message(item: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": str(item["role"])}
    content = item.get("content")
    # An assistant turn that only calls functions may carry no text.
    out["content"] = None if content is None and item.get("tool_calls") else (
        "" if content is None else str(content)
    )
    for key in _PASSTHROUGH_KEYS:
        if item.get(key):
            out[key] = item[key]
    return out


def _normalize_messages(
    messages: str | LLMMessage | Mapping[str, Any] | Iterable[Any],
) -> list[dict[str, Any]]:
    """Accept a string, one message, or a sequence of messages/dicts."""

    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    if isinstance(messages, LLMMessage):
        return [messages.as_dict()]
    if isinstance(messages, Mapping):
        return [_mapping_message(messages)]

    normalized: list[dict[str, Any]] = []
    for item in messages:
        if isinstance(item, LLMMessage):
            normalized.append(item.as_dict())
        elif isinstance(item, Mapping):
            normalized.append(_mapping_message(item))
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
        server: str = "",
    ) -> None:
        self.config = config
        self._completions = completions
        self.component = component
        #: Which ``[llm.providers.<name>]`` this client reaches (ledger + reply).
        self.server = server

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        completions: ChatCompletions | None = None,
        component: str = "",
        server: str = "",
    ) -> LLMClient:
        return cls(
            LLMConfig.from_settings(settings),
            completions=completions,
            component=component,
            server=server,
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
        tool_choice: str | Mapping[str, Any] | None = None,
        extra_body: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion and return the parsed answer + reasoning."""

        payload = self._payload(
            messages,
            model=model,
            reasoning=reasoning,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            extra_body=extra_body,
            **kwargs,
        )

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
            response = self._parse(raw, fallback_model=payload["model"])
        except Exception:
            llm_usage.record(self.component, ok=False, server=self._ledger_server)
            raise
        llm_usage.record(self.component, ok=True, usage=response.usage,
                         server=self._ledger_server)
        return self._served(response)

    def complete_stream(
        self,
        messages: str | LLMMessage | Mapping[str, str] | Sequence[Any],
        *,
        on_delta: Callable[[str, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        model: str | None = None,
        reasoning: ReasoningLevel | str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        tool_choice: str | Mapping[str, Any] | None = None,
        extra_body: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Stream a chat completion, reporting deltas as they arrive.

        ``on_delta(kind, text)`` is called with ``kind`` ``"text"`` or
        ``"thinking"`` for each chunk. ``should_stop()`` is checked after every
        chunk; when it returns true the stream is closed and what arrived so far
        is returned with ``finish_reason="cancelled"``. Tool calls are
        accumulated across chunks and returned whole, as :meth:`complete` does.
        """

        payload = self._payload(
            messages,
            model=model,
            reasoning=reasoning,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            extra_body=extra_body,
            **kwargs,
        )
        payload["stream"] = True
        payload.setdefault("stream_options", {"include_usage": True})
        llm_budget.check()
        try:
            stream = self.completions.create(**payload)
            response = _accumulate_stream(
                stream,
                fallback_model=payload["model"],
                on_delta=on_delta,
                should_stop=should_stop,
            )
        except Exception:
            llm_usage.record(self.component, ok=False, server=self._ledger_server)
            raise
        llm_usage.record(self.component, ok=True, usage=response.usage,
                         server=self._ledger_server)
        return self._served(response)

    @property
    def _ledger_server(self) -> str:
        return self.server or llm_usage.DEFAULT_SERVER

    def _served(self, response: LLMResponse) -> LLMResponse:
        if not self.server:
            return response
        from dataclasses import replace

        return replace(response, server=self.server)

    def _payload(
        self,
        messages: Any,
        *,
        model: str | None,
        reasoning: ReasoningLevel | str | None,
        temperature: float | None,
        max_tokens: int | None,
        tools: Sequence[Mapping[str, Any]] | None,
        tool_choice: str | Mapping[str, Any] | None,
        extra_body: Mapping[str, Any] | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
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
        }
        # No cap unless the operator set one or the caller asked: on a
        # reasoning model the cap includes thinking, and a starved reply falls
        # back silently (D-6 of the Mylo agent plan).
        cap = self.config.max_tokens if max_tokens is None else max_tokens
        if cap and cap > 0:
            payload["max_tokens"] = int(cap)
        if tools:
            payload["tools"] = list(tools)
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice
        if body:
            payload["extra_body"] = body
        payload.update(kwargs)
        return payload

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
        calls = []
        for index, call in enumerate(
            (getattr(message, "tool_calls", None) or []) if message is not None else []
        ):
            fn = _get(call, "function")
            name = _get(fn, "name") or ""
            if not name:
                continue
            calls.append(
                ToolCall(
                    id=_get(call, "id") or f"call_{index}",
                    name=name,
                    arguments=_get(fn, "arguments") or "",
                )
            )
        return LLMResponse(
            content=content or "",
            reasoning=reasoning,
            model=getattr(raw, "model", "") or fallback_model,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=_as_mapping(getattr(raw, "usage", None)),
            raw=raw,
            tool_calls=tuple(calls),
        )


def _get(obj: Any, key: str) -> Any:
    """Read ``key`` from an SDK object or a plain dict."""
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _accumulate_stream(
    stream: Any,
    *,
    fallback_model: str,
    on_delta: Callable[[str, str], None] | None,
    should_stop: Callable[[], bool] | None,
) -> LLMResponse:
    """Fold a chat-completions stream into one :class:`LLMResponse`."""
    text: list[str] = []
    thinking: list[str] = []
    calls: dict[int, dict[str, Any]] = {}
    model = ""
    finish = None
    usage = None
    try:
        for chunk in stream:
            model = _get(chunk, "model") or model
            chunk_usage = _as_mapping(_get(chunk, "usage"))
            if chunk_usage:
                usage = chunk_usage
            for choice in _get(chunk, "choices") or []:
                delta = _get(choice, "delta")
                finish = _get(choice, "finish_reason") or finish
                if delta is None:
                    continue
                piece = _get(delta, "reasoning_content") or _get(delta, "reasoning")
                if piece:
                    thinking.append(piece)
                    if on_delta:
                        on_delta("thinking", piece)
                piece = _get(delta, "content")
                if piece:
                    text.append(piece)
                    if on_delta:
                        on_delta("text", piece)
                for part in _get(delta, "tool_calls") or []:
                    index = _get(part, "index")
                    index = len(calls) if index is None else int(index)
                    slot = calls.setdefault(index, {"id": "", "name": "", "args": []})
                    slot["id"] = _get(part, "id") or slot["id"]
                    fn = _get(part, "function")
                    if fn is not None:
                        slot["name"] = slot["name"] or (_get(fn, "name") or "")
                        if _get(fn, "arguments"):
                            slot["args"].append(_get(fn, "arguments"))
            if should_stop is not None and should_stop():
                finish = "cancelled"
                break
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - closing a dead stream is best effort
                pass
    tool_calls = tuple(
        ToolCall(id=slot["id"] or f"call_{index}", name=slot["name"],
                 arguments="".join(slot["args"]))
        for index, slot in sorted(calls.items())
        if slot["name"]
    )
    return LLMResponse(
        content="".join(text),
        reasoning="".join(thinking) or None,
        model=model or fallback_model,
        finish_reason=finish,
        usage=usage,
        raw=None,
        tool_calls=tool_calls,
    )


def build_llm_client(
    settings: Any | None = None,
    *,
    completions: ChatCompletions | None = None,
    component: str = "",
    server: str | None = None,
) -> Any:
    """The client for ``component``: routed to its server, with fallback.

    Pass ``component`` so the calls show up under a meaningful name in the daily
    LLM ledger; unlabelled clients are counted as ``unlabelled``. Which server
    answers comes from ``[llm.routes]`` (``apps.core.llm_servers.resolve``);
    with nothing routed, that is ``local``, the ``.env`` endpoint, built exactly
    as before servers existed. ``server`` names one server outright (the
    probe and health checks); it must be one the host allows.

    An explicit ``settings`` object or ``completions`` transport (tests, the
    pre-registry call sites) builds the OpenAI-compatible client from those
    settings directly, as this factory always did.

    The return value has ``complete`` / ``complete_stream``; for an
    OpenAI-compatible server it is an :class:`LLMClient`, for Anthropic, Gemini
    and native Ollama an ``apps.core.llm_bridge.KitClient``, and when
    ``llm.fallback`` lists servers, a :class:`FallbackClient` over them.
    """

    if settings is not None or completions is not None:
        if settings is None:
            from django.conf import settings as django_settings

            settings = django_settings
        return LLMClient.from_settings(
            settings, completions=completions, component=component
        )
    from apps.core import llm_servers

    route = (llm_servers.resolve(component) if server is None
             else llm_servers.route_to(server, component))
    primary = client_for_route(route, component)
    if server is not None:
        return primary
    table = llm_servers.table()
    chain = [
        name for name in table.fallback
        if name != route.server and table.callable(name)
    ]
    if not chain:
        return primary
    return FallbackClient(
        component,
        [primary, *(client_for_route(llm_servers.route_to(name, component),
                                     component) for name in chain)],
    )


def client_for_route(route: Any, component: str) -> Any:
    """One server's client: the shared OpenAI-compatible client or the bridge."""
    from django.conf import settings

    from apps.core import llm_servers
    from config.instance import LLM_OPENAI_KINDS

    entry = llm_servers.server(route.server) or {}
    if entry.get("synthesized"):
        client = LLMClient.from_settings(settings, component=component,
                                         server=route.server)
        if route.model and route.model != client.config.model:
            from dataclasses import replace

            client.config = replace(client.config, model=route.model)
        return client
    if entry.get("kind") in LLM_OPENAI_KINDS:
        base = LLMConfig.from_settings(settings)
        from dataclasses import replace

        provider = llm_servers.provider_config(entry)
        config = replace(
            base,
            base_url=provider.resolved_base_url() or "",
            api_key=llm_servers.api_key(entry) or "EMPTY",
            model=route.model,
            timeout=float(entry.get("timeout") or base.timeout),
            connect_timeout=float(entry.get("connect_timeout")
                                  or base.connect_timeout),
            reasoning=ReasoningLevel.coerce(entry.get("reasoning")
                                            or base.reasoning.value),
        )
        return LLMClient(config, component=component, server=route.server)
    from apps.core.llm_bridge import KitClient

    return KitClient(entry, model=route.model, component=component)


class FallbackClient:
    """Try the routed server, then each ``llm.fallback`` server in order.

    A server whose circuit is open (three failures in a row, for 30 seconds) is
    skipped without a call. Only a failure another server could avoid —
    unreachable, timed out, overloaded, rate-limited, 5xx — moves on; a
    rejected request is raised as it is. A streamed reply that has already
    shown text is never replayed elsewhere. Only servers the host listed are
    ever tried (S-14), and a cloud one only while ``llm.allow_cloud`` is true.
    The caller's ``model=`` applies to the routed server only; each fallback
    server uses its own model.
    """

    def __init__(self, component: str, clients: list[Any]) -> None:
        self.component = component
        self.clients = clients
        self.server = clients[0].server

    def complete(self, messages: Any, **kwargs: Any) -> LLMResponse:
        return self._run(lambda client, kw: client.complete(messages, **kw),
                         kwargs, None)

    def complete_stream(self, messages: Any, *, on_delta=None,
                        **kwargs: Any) -> LLMResponse:
        shown = [False]

        def delta(kind: str, text: str) -> None:
            shown[0] = True
            if on_delta is not None:
                on_delta(kind, text)

        return self._run(
            lambda client, kw: client.complete_stream(messages, on_delta=delta,
                                                      **kw),
            kwargs, shown)

    def _run(self, call, kwargs: dict[str, Any], shown) -> LLMResponse:
        import logging

        log = logging.getLogger(__name__)
        last: BaseException | None = None
        for index, client in enumerate(self.clients):
            breaker = breaker_for(client.server)
            if breaker.is_open:
                last = last or LLMUnavailableError(
                    f"server {client.server!r} is failing; skipped",
                    server=client.server)
                continue
            kw = dict(kwargs)
            if index:
                kw.pop("model", None)
            try:
                response = call(client, kw)
            except Exception as exc:
                if not is_unavailable_error(exc):
                    raise
                breaker.record_failure()
                last = exc
                if shown is not None and shown[0]:
                    raise
                log.warning("llm server %r unavailable for %r (%s); trying the "
                            "next fallback", client.server, self.component, exc)
                continue
            breaker.record_success()
            return response
        assert last is not None
        raise last


_breakers: dict[str, Any] = {}


def breaker_for(server: str) -> Any:
    """The process-wide circuit breaker for one server (3 failures, 30 s)."""
    from apps.core.llmkit import CircuitBreaker

    breaker = _breakers.get(server)
    if breaker is None:
        breaker = _breakers.setdefault(server, CircuitBreaker(threshold=3,
                                                              reset_after=30.0))
    return breaker

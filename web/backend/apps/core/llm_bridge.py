"""``KitClient``: the shared client surface over an ``llmkit`` provider.

OpenAI-shaped servers keep :class:`apps.core.llm.LLMClient`, which carries the
reasoning-style handling the components were tuned on. Anthropic, Gemini and
native Ollama go through this class instead. It has the same ``complete`` /
``complete_stream`` signature and returns the same
:class:`~apps.core.llm.LLMResponse`, so feature code never tests the server
kind: every difference between wire formats ends here.

What this boundary translates:

* **Messages** — OpenAI-shaped dicts in (``role``, ``content``, ``tool_calls``,
  ``tool_call_id``), ``llmkit.Message`` out. Consecutive tool results become one
  turn; each result knows its function's name (Gemini answers by name).
* **Opaque reasoning state** — Anthropic thinking blocks (with signatures) and
  Gemini thought-signature parts come back in ``LLMResponse.opaque`` as
  ``{"kind", "blocks"}`` (JSON-safe, otherwise untouched). An assistant
  message carrying ``opaque`` of this server's kind hands the blocks back
  verbatim; of another kind, they are dropped.
* **Tools** — OpenAI function schemas pass to ``llmkit.ToolDef`` unchanged;
  calls come back whole, arguments re-serialised to the JSON string
  ``LLMResponse.tool_calls`` carries.
* **Reasoning** — the instance's ``LLM_REASONING`` level (or the server's own
  ``reasoning``) becomes ``GenParams.reasoning_effort``; the adapter snaps it to
  what the model accepts.
* **Usage** — ``billable_input_tokens`` (cache reads counted once) and output
  tokens, in the ``prompt_tokens`` / ``completion_tokens`` keys the ledger and
  the agent read.
* **Errors** — ``llmkit`` errors become :class:`~apps.core.llm.LLMServerError`
  subclasses; a context overflow is :class:`~apps.core.llm.LLMContextLengthError`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from apps.core import llm_budget, llm_usage
from apps.core.llm import (
    LLMConfigurationError,
    LLMContextLengthError,
    LLMMessage,
    LLMRequestError,
    LLMResponse,
    LLMUnavailableError,
    ReasoningLevel,
    ToolCall,
)

logger = logging.getLogger(__name__)

#: The kinds this client serves; the rest are OpenAI-shaped (LLMClient).
KINDS = ("anthropic", "gemini", "ollama")


class KitClient:
    """One server reached through ``llmkit``, with the ``LLMClient`` surface."""

    def __init__(
        self,
        entry: Mapping[str, Any],
        *,
        model: str = "",
        component: str = "",
        provider: Any = None,
    ) -> None:
        self.entry = dict(entry)
        self.server = self.entry["name"]
        self.kind = self.entry["kind"]
        self.model = model or self.entry.get("model") or ""
        self.component = component
        self._provider = provider

    @property
    def provider(self):
        if self._provider is None:
            from apps.core import llm_servers
            from apps.core.llmkit.providers import build_provider

            self._provider = build_provider(llm_servers.provider_config(self.entry))
        return self._provider

    # -- the LLMClient surface ------------------------------------------------

    def complete(self, messages, *, model=None, reasoning=None, temperature=None,
                 max_tokens=None, tools=None, tool_choice=None, extra_body=None,
                 **kwargs) -> LLMResponse:
        return self._call(messages, stream=False, on_delta=None, should_stop=None,
                          model=model, reasoning=reasoning, temperature=temperature,
                          max_tokens=max_tokens, tools=tools, tool_choice=tool_choice)

    def complete_stream(self, messages, *, on_delta=None, should_stop=None,
                        model=None, reasoning=None, temperature=None,
                        max_tokens=None, tools=None, tool_choice=None,
                        extra_body=None, **kwargs) -> LLMResponse:
        return self._call(messages, stream=True, on_delta=on_delta,
                          should_stop=should_stop, model=model, reasoning=reasoning,
                          temperature=temperature, max_tokens=max_tokens,
                          tools=tools, tool_choice=tool_choice)

    # -- the one call ---------------------------------------------------------

    def _call(self, messages, *, stream: bool,
              on_delta: Callable[[str, str], None] | None,
              should_stop: Callable[[], bool] | None, model, reasoning,
              temperature, max_tokens, tools, tool_choice) -> LLMResponse:
        name = model or self.model
        if not name:
            raise LLMConfigurationError(
                f"no model configured for server {self.server!r}; set model in "
                f"[llm.providers.{self.server}]")
        msgs = to_kit_messages(messages, self.kind)
        tool_defs = to_tool_defs(tools)
        params = self._params(reasoning, temperature, max_tokens,
                              tool_choice if tool_defs else None)
        llm_budget.check()
        try:
            if stream:
                response = self._stream(msgs, name, tool_defs, params, on_delta,
                                        should_stop)
            else:
                with _translated(self.server):
                    out = self.provider.chat(msgs, model=name, tools=tool_defs,
                                             params=params)
                response = self._response(
                    text=out.text, thinking=out.thinking, calls=out.tool_calls,
                    finish=out.finish_reason, usage=out.usage,
                    model=out.model or name, raw=out.raw)
        except Exception:
            llm_usage.record(self.component, ok=False, server=self.server)
            raise
        llm_usage.record(self.component, ok=True, usage=response.usage,
                         server=self.server)
        return response

    def _stream(self, msgs, name, tool_defs, params, on_delta, should_stop):
        text: list[str] = []
        thinking: list[str] = []
        calls = []
        finish, usage, raw, served = None, None, None, name
        with _translated(self.server):
            chunks = self.provider.stream(msgs, model=name, tools=tool_defs,
                                          params=params)
            try:
                for chunk in chunks:
                    served = chunk.model or served
                    if chunk.type == "text" and chunk.text:
                        text.append(chunk.text)
                        if on_delta:
                            on_delta("text", chunk.text)
                    elif chunk.type == "thinking" and chunk.text:
                        thinking.append(chunk.text)
                        if on_delta:
                            on_delta("thinking", chunk.text)
                    elif chunk.type == "tool_call" and chunk.tool_call:
                        calls.append(chunk.tool_call)
                    elif chunk.type == "done":
                        finish, usage, raw = chunk.finish_reason, chunk.usage, chunk.raw
                    if should_stop is not None and should_stop():
                        finish = "cancelled"
                        break
            finally:
                close = getattr(chunks, "close", None)
                if callable(close):
                    close()
        return self._response(text="".join(text), thinking="".join(thinking) or None,
                              calls=calls, finish=finish, usage=usage,
                              model=served, raw=raw)

    def _params(self, reasoning, temperature, max_tokens, tool_choice):
        from django.conf import settings

        from apps.core.llmkit import GenParams

        level = ReasoningLevel.coerce(
            reasoning if reasoning is not None
            else (self.entry.get("reasoning") or settings.LLM_REASONING))
        effort = None if level is ReasoningLevel.NONE else level.value
        if temperature is None:
            temperature = float(settings.LLM_TEMPERATURE)
        cap = int(settings.LLM_MAX_TOKENS or 0) if max_tokens is None else max_tokens
        params = GenParams(
            # LLM_TEMPERATURE is on OpenAI's 0..2 scale; llmkit's is 0..1.
            temperature=max(0.0, min(1.0, float(temperature) / 2.0)),
            max_tokens=int(cap) if cap and cap > 0 else None,
            reasoning_effort=effort if effort else (
                "none" if self.kind != "anthropic" else None),
            include_thoughts=bool(effort),
            tool_choice=_tool_choice(tool_choice),
        )
        if self.kind == "anthropic" and effort:
            # Claude accepts no sampling temperature while it thinks.
            params.temperature = None
        return params

    def _call_id(self, call) -> str:
        """The server's call id, or a fresh one where the server gives none
        that is unique across a thread (Ollama numbers each reply's calls
        from 0; Gemini may send none, and llmkit then uses the name)."""
        cid = call.id or ""
        if not cid or cid == call.name or self.kind == "ollama":
            import uuid

            cid = f"call_{uuid.uuid4().hex[:24]}"
        return cid

    def _response(self, *, text, thinking, calls, finish, usage, model,
                  raw) -> LLMResponse:
        return LLMResponse(
            content=text or "",
            reasoning=thinking or None,
            model=model,
            finish_reason=finish,
            usage=usage_mapping(usage),
            raw=None,
            tool_calls=tuple(
                ToolCall(id=self._call_id(c), name=c.name,
                         arguments=json.dumps(c.arguments or {}))
                for c in calls if c.name),
            opaque=opaque_state(self.kind, raw),
            server=self.server,
        )


# --------------------------------------------------------------------------- #
# Translation helpers (pure; tested directly)
# --------------------------------------------------------------------------- #


def _as_dict(message: Any) -> dict[str, Any]:
    if isinstance(message, LLMMessage):
        return message.as_dict()
    if isinstance(message, Mapping):
        return dict(message)
    raise TypeError(f"unsupported message type: {type(message)!r}")


def to_kit_messages(messages: Any, kind: str) -> list[Any]:
    """OpenAI-shaped messages as ``llmkit.Message`` objects for ``kind``."""
    from apps.core.llmkit import Message
    from apps.core.llmkit import ToolCall as KitCall
    from apps.core.llmkit.types import ToolResult

    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    elif isinstance(messages, (LLMMessage, Mapping)):
        messages = [messages]
    rows = [_as_dict(m) for m in messages]
    if not rows:
        raise LLMConfigurationError("at least one message is required")
    names: dict[str, str] = {}
    out: list[Any] = []
    for row in rows:
        role = str(row.get("role") or "user")
        content = row.get("content")
        text = "" if content is None else str(content)
        if role == "assistant":
            calls = []
            for index, call in enumerate(row.get("tool_calls") or []):
                fn = call.get("function") or {}
                cid = call.get("id") or f"call_{index}"
                names[cid] = fn.get("name") or ""
                calls.append(KitCall(id=cid, name=fn.get("name") or "",
                                     arguments=_arguments(fn.get("arguments"))))
            opaque = row.get("opaque")
            blocks = None
            if isinstance(opaque, Mapping) and opaque.get("kind") == kind:
                blocks = list(opaque.get("blocks") or []) or None
            out.append(Message(role="assistant", content=text, tool_calls=calls,
                               thinking_raw=blocks))
        elif role == "tool":
            cid = str(row.get("tool_call_id") or "")
            result = ToolResult(tool_call_id=cid, content=text,
                                name=row.get("name") or names.get(cid) or None)
            if out and out[-1].role == "tool":
                out[-1].tool_results.append(result)
            else:
                out.append(Message(role="tool", tool_results=[result]))
        elif role == "system":
            out.append(Message.system(text))
        else:
            out.append(Message.user(text))
    return out


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def to_tool_defs(tools: Sequence[Mapping[str, Any]] | None) -> list[Any] | None:
    """OpenAI ``{"type": "function", "function": {...}}`` tools as ToolDefs."""
    if not tools:
        return None
    from apps.core.llmkit import ToolDef

    out = []
    for tool in tools:
        fn = tool.get("function") if "function" in tool else tool
        out.append(ToolDef(
            name=fn["name"],
            description=fn.get("description") or "",
            parameters=dict(fn.get("parameters")
                            or {"type": "object", "properties": {}}),
        ))
    return out


def _tool_choice(choice: Any) -> Any:
    if choice is None:
        return None
    if isinstance(choice, str):
        return choice
    if isinstance(choice, Mapping):
        fn = choice.get("function") or {}
        name = fn.get("name") or choice.get("name")
        if name:
            return {"name": name}
    return "auto"


def usage_mapping(usage: Any) -> dict[str, int] | None:
    """``llmkit.Usage`` in the OpenAI keys the ledger reads (cache once)."""
    if usage is None:
        return None
    prompt = int(usage.billable_input_tokens)
    completion = int(usage.output_tokens)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "reasoning_tokens": int(usage.reasoning_tokens),
        "cached_tokens": int(usage.cached_read_tokens),
    }


def _dump(block: Any) -> Any:
    if isinstance(block, Mapping):
        return dict(block)
    dump = getattr(block, "model_dump", None)
    if callable(dump):
        return dump(mode="json", exclude_none=True)
    return block


def opaque_state(kind: str, raw: Any) -> dict[str, Any] | None:
    """The reasoning state a server needs back verbatim, JSON-safe, or None.

    Anthropic: the ``thinking`` / ``redacted_thinking`` blocks of the reply,
    signatures included. Gemini: the parts carrying a thought signature (and
    the thought parts). Ollama keeps none.
    """
    blocks: list[Any] = []
    if kind == "anthropic":
        content = getattr(raw, "content", None)
        if isinstance(raw, Mapping):
            content = raw.get("content")
        for block in content or []:
            btype = (block.get("type") if isinstance(block, Mapping)
                     else getattr(block, "type", None))
            if btype in ("thinking", "redacted_thinking"):
                blocks.append(_dump(block))
    elif kind == "gemini":
        if isinstance(raw, Mapping) and "thinking_raw" in raw:
            parts = raw["thinking_raw"] or []
        else:
            parts = []
            for cand in (getattr(raw, "candidates", None) or [])[:1]:
                content = getattr(cand, "content", None)
                for part in getattr(content, "parts", None) or []:
                    if getattr(part, "thought", False) or getattr(
                            part, "thought_signature", None):
                        parts.append(part)
        blocks = [_dump(p) for p in parts]
    if not blocks:
        return None
    return {"kind": kind, "blocks": blocks}


class _translated:
    """Re-raise ``llmkit`` errors as the shared client's error classes."""

    def __init__(self, server: str) -> None:
        self.server = server

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            return False
        from apps.core.llmkit import errors as kit

        if isinstance(exc, (LLMConfigurationError, LLMRequestError,
                            LLMUnavailableError)):
            return False
        if isinstance(exc, kit.ContextLengthError):
            raise LLMContextLengthError(str(exc), server=self.server) from exc
        if isinstance(exc, kit.LLMError):
            if exc.retryable:
                raise LLMUnavailableError(str(exc), server=self.server) from exc
            if isinstance(exc, kit.ConfigError):
                raise LLMConfigurationError(str(exc)) from exc
            raise LLMRequestError(str(exc), server=self.server) from exc
        return False

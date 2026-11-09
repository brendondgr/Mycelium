"""One model call, and the repairs a local model needs (GAIFA §4.3).

The instance model is local vLLM by default, which sometimes:

* leaks a function call into the text (Hermes ``<tool_call>{…}</tool_call>``,
  a ``tool_code`` fence with ``name(arg=…)``, or a bare JSON object) — re-parsed
  here **for known function names only**;
* sends loose or truncated JSON arguments — repaired where it is unambiguous;
* puts its reasoning inline as ``<think>…</think>`` — split off;
* repeats itself until the cap — the repetition is cut;
* returns nothing at all — retried once.
"""

from __future__ import annotations

import ast
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from apps.core.llm import LLMResponse

from . import config


class ModelPort(Protocol):
    def __call__(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None,
        tool_choice: str | None,
        on_delta: Callable | None,
        should_stop: Callable | None,
    ) -> LLMResponse: ...


class NoModel(RuntimeError):
    """No model is configured on this instance."""


def model_name() -> str:
    from django.conf import settings

    return config.get("model") or getattr(settings, "LLM_MODEL", "") or ""


def model_info() -> dict | None:
    """``{name, label, location}`` of the model that answers chat, or ``None``
    when none is configured. ``location`` is ``local``, ``remote`` or
    ``cloud`` (S-3); until the server registry exists every model is the
    instance's own, so it is ``local`` and ``label`` is the model name."""
    name = model_name()
    if not name:
        return None
    return {"name": name, "label": name, "location": "local"}


def default_port() -> ModelPort:
    """The instance's model through the shared client, streamed."""
    from apps.core.llm import build_llm_client

    name = model_name()
    if not name:
        raise NoModel("no model configured")
    client = build_llm_client(component="agent")
    cap = int(config.get("max_output_tokens") or 0)

    def port(*, messages, tools, tool_choice, on_delta, should_stop):
        return client.complete_stream(
            messages,
            model=name,
            tools=tools or None,
            tool_choice=tool_choice if tools else None,
            max_tokens=cap,
            on_delta=on_delta,
            should_stop=should_stop,
        )

    return port


@dataclass
class Call:
    id: str
    name: str
    arguments: str
    args: dict | None
    error: str = ""


@dataclass
class Reply:
    text: str
    thinking: str
    calls: list[Call]
    finish: str | None
    usage: dict | None
    repairs: list[str] = field(default_factory=list)


_THINK = re.compile(r"<think>(.*?)(</think>|$)", re.S)
_HERMES = re.compile(r"<tool_call>\s*(\{.*?\})\s*(</tool_call>|$)", re.S)
_TOOL_CODE = re.compile(r"```(?:tool_code|python)?\s*\n?(.*?)```", re.S)


def repair_json(text: str) -> dict | None:
    """Parse function arguments, repairing the common local-model faults."""
    text = (text or "").strip()
    if not text:
        return {}
    for candidate in _json_candidates(text):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, str):  # double-encoded
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if isinstance(value, dict):
            return value
    try:  # Python-style dict: single quotes, True/None
        value = ast.literal_eval(text)
        if isinstance(value, dict):
            return value
    except (ValueError, SyntaxError):
        pass
    return None


def _json_candidates(text: str):
    yield text
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    yield stripped
    no_trailing = re.sub(r",\s*([}\]])", r"\1", stripped)
    yield no_trailing
    # truncated: close open strings and brackets
    opens = []
    in_str = esc = False
    for ch in no_trailing:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str and ch in "{[":
            opens.append("}" if ch == "{" else "]")
        elif not in_str and ch in "}]" and opens:
            opens.pop()
    closed = no_trailing + ('"' if in_str else "") + "".join(reversed(opens))
    yield re.sub(r",\s*([}\]])", r"\1", closed)


def _leaked_calls(text: str, known: set[str]) -> tuple[list[Call], str]:
    calls: list[Call] = []
    rest = text
    for match in list(_HERMES.finditer(text)):
        data = repair_json(match.group(1)) or {}
        name = data.get("name")
        if name in known:
            args = data.get("arguments", data.get("parameters", {}))
            if isinstance(args, str):
                args = repair_json(args) or {}
            calls.append(_call(name, args))
            rest = rest.replace(match.group(0), "")
    for match in list(_TOOL_CODE.finditer(rest)):
        found = _pythonic(match.group(1), known)
        if found:
            calls.extend(found)
            rest = rest.replace(match.group(0), "")
    if not calls:
        stripped = rest.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            data = repair_json(stripped) or {}
            if data.get("name") in known and isinstance(
                data.get("arguments", {}), dict
            ):
                calls.append(_call(data["name"], data.get("arguments", {})))
                rest = ""
    return calls, rest.strip()


def _pythonic(code: str, known: set[str]) -> list[Call]:
    """``name(a=1, b="x")`` lines, possibly wrapped in ``print(...)``."""
    out = []
    try:
        tree = ast.parse(code.strip())
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in known:
            continue
        try:
            args = {
                kw.arg: ast.literal_eval(kw.value) for kw in node.keywords if kw.arg
            }
        except ValueError:
            continue
        out.append(_call(node.func.id, args))
    return out


def _call(name: str, args: dict) -> Call:
    raw = json.dumps(args)
    return Call(id=f"call_{uuid.uuid4().hex[:12]}", name=name, arguments=raw, args=args)


def cut_runaway(text: str, *, repeats: int = 4) -> tuple[str, bool]:
    """Cut a model stuck in a loop: text ending in the same run (10–400
    characters) repeated ``repeats`` or more times keeps one copy of it; a
    line repeated more than ``repeats`` times keeps text up to its first."""
    n = len(text)
    for period in range(10, min(400, n // repeats) + 1):
        unit = text[n - period :]
        if not unit.strip() or text[n - period * repeats :] != unit * repeats:
            continue
        start = n - period * repeats
        while start - period >= 0 and text[start - period : start] == unit:
            start -= period
        return text[: start + period].rstrip(), True
    lines = text.splitlines()
    seen: dict[str, int] = {}
    for line in lines:
        if len(line.strip()) < 8:
            continue
        seen[line] = seen.get(line, 0) + 1
        if seen[line] > repeats:
            first = lines.index(line)
            return "\n".join(lines[: first + 1]).rstrip(), True
    return text, False


def call(
    port: ModelPort,
    *,
    messages: list[dict],
    tools: list[dict],
    tool_choice: str | None,
    known: set[str],
    on_delta=None,
    should_stop=None,
) -> Reply:
    response = port(
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        on_delta=on_delta,
        should_stop=should_stop,
    )
    repairs: list[str] = []
    if (
        not (response.content or "").strip()
        and not response.tool_calls
        and (response.finish_reason != "cancelled")
    ):
        repairs.append("empty_retry")
        response = port(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            on_delta=None,
            should_stop=should_stop,
        )
    return parse(
        response, known=known, repairs=repairs, allow_calls=tool_choice != "none"
    )


def parse(
    response: LLMResponse,
    *,
    known: set[str],
    repairs: list[str] | None = None,
    allow_calls: bool = True,
) -> Reply:
    repairs = list(repairs or [])
    text = response.content or ""
    thinking = response.reasoning or ""
    think = _THINK.findall(text)
    if think:
        thinking = (thinking + "\n" + "\n".join(t[0] for t in think)).strip()
        text = _THINK.sub("", text)
        repairs.append("think_split")
    calls: list[Call] = []
    for tc in response.tool_calls:
        args = repair_json(tc.arguments)
        error = "" if args is not None else "arguments are not valid JSON"
        if (
            args is not None
            and tc.arguments.strip()
            and _plain_json(tc.arguments) is None
        ):
            repairs.append("json_repaired")
        calls.append(
            Call(
                id=tc.id or _call(tc.name, {}).id,
                name=tc.name,
                arguments=json.dumps(args) if args is not None else tc.arguments,
                args=args,
                error=error,
            )
        )
    if not calls and allow_calls:
        leaked, rest = _leaked_calls(text, known)
        if leaked:
            calls, text = leaked, rest
            repairs.append("leaked_call")
    text, cut = cut_runaway(text)
    if cut:
        repairs.append("runaway_cut")
    if not allow_calls:
        calls = []
    return Reply(
        text=text.strip(),
        thinking=thinking.strip(),
        calls=calls,
        finish=response.finish_reason,
        usage=dict(response.usage or {}) or None,
        repairs=repairs,
    )


def _plain_json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None

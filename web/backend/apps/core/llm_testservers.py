"""Mock model servers for tests: OpenAI-compatible (vLLM), llama.cpp, Ollama,
Anthropic and Gemini, each on a loopback port.

Each mock speaks the wire format the real server does closely enough for the
official SDKs (``openai``, ``anthropic``, ``google-genai``) and ``llmkit`` to
talk to it: model listing with context windows, chat, streaming, tool calls and
the opaque reasoning state (Anthropic thinking signatures, Gemini thought
signatures). Replies are scripted::

    with MockServer("anthropic") as srv:
        srv.replies.append(reply(calls=[("search", {"q": "x"})]))
        srv.replies.append(reply(text="done"))
        ...
        srv.requests  # every JSON body the server received

Not a test module itself (pytest does not collect it); imported by
``apps/core/test_llm_*.py`` and ``tools/agent/tests``.
"""

from __future__ import annotations

import base64
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

KINDS = ("openai_compatible", "llamacpp", "ollama", "anthropic", "gemini")
CONTEXT = {"openai_compatible": 40960, "llamacpp": 16384, "ollama": 8192,
           "anthropic": 200000, "gemini": 1048576}
MODEL = {"openai_compatible": "Qwen/Qwen3-8B", "llamacpp": "qwen3-8b.gguf",
         "ollama": "qwen3:8b", "anthropic": "claude-test-5",
         "gemini": "gemini-3-test"}


def reply(text: str = "", *, thinking: str = "", calls=(),
          signature: str = "") -> dict[str, Any]:
    """One scripted model turn. ``calls`` is ``[(name, args), ...]``."""
    return {"text": text, "thinking": thinking, "calls": list(calls),
            "signature": signature}


def dead_url() -> str:
    """An address where nothing listens: connecting is refused at once."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"


class MockServer:
    """One mock server of ``kind``; use as a context manager."""

    def __init__(self, kind: str, *, model: str = "", context: int = 0) -> None:
        if kind not in KINDS:
            raise ValueError(kind)
        self.kind = kind
        self.model = model or MODEL[kind]
        self.context = context or CONTEXT[kind]
        self.replies: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.paths: list[str] = []
        self.list_calls = 0
        self.fail_chat = 0  # answer this many chat calls with HTTP 500
        self._server: ThreadingHTTPServer | None = None

    # -- lifecycle -----------------------------------------------------------

    def __enter__(self) -> MockServer:
        handler = _handler_for(self)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    @property
    def root(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def base_url(self) -> str:
        """What a host writes as ``base_url`` for this kind."""
        if self.kind in ("openai_compatible", "llamacpp"):
            return f"{self.root}/v1"
        return self.root

    def next_reply(self) -> dict[str, Any]:
        return self.replies.pop(0) if self.replies else reply("ok")

    def server_entry(self, name: str = "", **fields: Any) -> dict[str, Any]:
        """A resolved ``LLM_SERVERS`` entry pointing at this mock."""
        from config.instance import derive_location

        kind = self.kind
        # Anthropic and Gemini mocks stand in for the public APIs, so they are
        # stated as cloud (their loopback address would otherwise say local).
        hosted = kind in ("anthropic", "gemini")
        entry = {
            "name": name or kind, "kind": kind, "base_url": self.base_url,
            "api_key_env": "MOCK_LLM_KEY" if kind in ("anthropic", "gemini") else "",
            "model": self.model, "label": f"Mock {kind}", "enabled": True,
            "location": "cloud" if hosted else derive_location(kind, self.base_url),
            "location_stated": hosted, "timeout": 10.0, "connect_timeout": 2.0,
            "context_window": 0, "reasoning": "", "model_allow": [],
            "model_deny": [], "synthesized": False,
        }
        entry.update(fields)
        return entry


# --------------------------------------------------------------------------- #
# Wire formats
# --------------------------------------------------------------------------- #


def _sse(events: list[tuple[str | None, dict | str]]) -> bytes:
    out = []
    for event, data in events:
        text = data if isinstance(data, str) else json.dumps(data)
        out.append((f"event: {event}\n" if event else "") + f"data: {text}\n\n")
    return "".join(out).encode()


def _openai_models(srv: MockServer) -> dict:
    return {"object": "list", "data": [
        {"id": srv.model, "object": "model", "created": 1755000000,
         "owned_by": "vllm", "max_model_len": srv.context}]}


def _openai_message(srv: MockServer, r: dict) -> dict:
    msg: dict[str, Any] = {"role": "assistant", "content": r["text"] or None}
    if r["thinking"]:
        msg["reasoning_content"] = r["thinking"]
    if r["calls"]:
        msg["tool_calls"] = [
            {"id": f"call_{i}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (name, args) in enumerate(r["calls"])]
    return msg


def _openai_chat(srv: MockServer, body: dict, r: dict) -> tuple[str, bytes]:
    usage = {"prompt_tokens": 30, "completion_tokens": 7, "total_tokens": 37}
    finish = "tool_calls" if r["calls"] else "stop"
    if not body.get("stream"):
        return "application/json", json.dumps({
            "id": "chatcmpl-1", "object": "chat.completion", "created": 1,
            "model": srv.model, "usage": usage,
            "choices": [{"index": 0, "finish_reason": finish,
                         "message": _openai_message(srv, r)}]}).encode()
    base = {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 1,
            "model": srv.model}
    events: list[tuple[str | None, dict | str]] = []

    def chunk(delta: dict, finish_reason=None) -> None:
        events.append((None, {**base, "choices": [
            {"index": 0, "delta": delta, "finish_reason": finish_reason}]}))

    chunk({"role": "assistant"})
    if r["thinking"]:
        chunk({"reasoning_content": r["thinking"]})
    if r["text"]:
        half = len(r["text"]) // 2
        chunk({"content": r["text"][:half]})
        chunk({"content": r["text"][half:]})
    for i, (name, args) in enumerate(r["calls"]):
        text = json.dumps(args)
        chunk({"tool_calls": [{"index": i, "id": f"call_{i}", "type": "function",
                               "function": {"name": name, "arguments": text[:3]}}]})
        chunk({"tool_calls": [{"index": i, "function": {"arguments": text[3:]}}]})
    chunk({}, finish)
    events.append((None, {**base, "choices": [], "usage": usage}))
    events.append((None, "[DONE]"))
    return "text/event-stream", _sse(events)


def _anthropic_models(srv: MockServer) -> dict:
    model = {
        "type": "model", "id": srv.model, "display_name": "Claude Test",
        "created_at": "2026-01-01T00:00:00Z", "max_input_tokens": srv.context,
        "max_tokens": 8192,
        "capabilities": {
            "thinking": {"supported": True}, "image_input": {"supported": True},
            "structured_outputs": {"supported": True},
            "effort": {"supported": True, "low": {"supported": True},
                       "medium": {"supported": True}, "high": {"supported": True}},
        },
    }
    return {"data": [model], "has_more": False, "first_id": srv.model,
            "last_id": srv.model}


def _anthropic_blocks(r: dict) -> list[dict]:
    blocks: list[dict] = []
    if r["thinking"]:
        blocks.append({"type": "thinking", "thinking": r["thinking"],
                       "signature": r["signature"] or "sig-anthropic-1=="})
    if r["text"]:
        blocks.append({"type": "text", "text": r["text"]})
    for i, (name, args) in enumerate(r["calls"]):
        blocks.append({"type": "tool_use", "id": f"toolu_{i}", "name": name,
                       "input": args})
    return blocks


def _anthropic_chat(srv: MockServer, body: dict, r: dict) -> tuple[str, bytes]:
    blocks = _anthropic_blocks(r)
    stop = "tool_use" if r["calls"] else "end_turn"
    usage = {"input_tokens": 30, "output_tokens": 7,
             "cache_read_input_tokens": 5, "cache_creation_input_tokens": 0}
    if not body.get("stream"):
        return "application/json", json.dumps({
            "id": "msg_1", "type": "message", "role": "assistant",
            "model": srv.model, "content": blocks, "stop_reason": stop,
            "stop_sequence": None, "usage": usage}).encode()
    events: list[tuple[str | None, dict | str]] = [("message_start", {
        "type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant",
            "model": srv.model, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {**usage, "output_tokens": 1}}})]
    for index, block in enumerate(blocks):
        kind = block["type"]
        if kind == "thinking":
            start = {"type": "thinking", "thinking": "", "signature": ""}
            deltas = [{"type": "thinking_delta", "thinking": block["thinking"]},
                      {"type": "signature_delta", "signature": block["signature"]}]
        elif kind == "text":
            start = {"type": "text", "text": ""}
            deltas = [{"type": "text_delta", "text": block["text"]}]
        else:
            start = {"type": "tool_use", "id": block["id"], "name": block["name"],
                     "input": {}}
            deltas = [{"type": "input_json_delta",
                       "partial_json": json.dumps(block["input"])}]
        events.append(("content_block_start", {
            "type": "content_block_start", "index": index, "content_block": start}))
        for delta in deltas:
            events.append(("content_block_delta", {
                "type": "content_block_delta", "index": index, "delta": delta}))
        events.append(("content_block_stop",
                       {"type": "content_block_stop", "index": index}))
    events.append(("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop, "stop_sequence": None},
        "usage": {"output_tokens": 7}}))
    events.append(("message_stop", {"type": "message_stop"}))
    return "text/event-stream", _sse(events)


def _gemini_models(srv: MockServer) -> dict:
    return {"models": [{
        "name": f"models/{srv.model}", "displayName": "Gemini Test",
        "version": "1", "inputTokenLimit": srv.context, "outputTokenLimit": 65536,
        "supportedGenerationMethods": ["generateContent", "countTokens"],
        "thinking": True}]}


def _gemini_parts(r: dict) -> list[dict]:
    parts: list[dict] = []
    if r["thinking"]:
        parts.append({"text": r["thinking"], "thought": True})
    signature = base64.b64encode(
        (r["signature"] or "gemini-thought-signature").encode()).decode()
    for i, (name, args) in enumerate(r["calls"]):
        part: dict[str, Any] = {"functionCall": {"name": name, "args": args,
                                                 "id": f"fc_{i}"}}
        if i == 0:
            part["thoughtSignature"] = signature
        parts.append(part)
    if r["text"]:
        parts.append({"text": r["text"]})
    return parts


def _gemini_chat(srv: MockServer, stream: bool, r: dict) -> tuple[str, bytes]:
    usage = {"promptTokenCount": 30, "candidatesTokenCount": 7,
             "thoughtsTokenCount": 3, "totalTokenCount": 40}
    payload = {"candidates": [{"content": {"role": "model",
                                           "parts": _gemini_parts(r)},
                               "finishReason": "STOP", "index": 0}],
               "usageMetadata": usage, "modelVersion": srv.model}
    if not stream:
        return "application/json", json.dumps(payload).encode()
    parts = payload["candidates"][0]["content"]["parts"]
    events: list[tuple[str | None, dict | str]] = []
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        chunk = {"candidates": [{"content": {"role": "model", "parts": [part]},
                                 "index": 0,
                                 **({"finishReason": "STOP"} if last else {})}],
                 "modelVersion": srv.model}
        if last:
            chunk["usageMetadata"] = usage
        events.append((None, chunk))
    if not parts:
        events.append((None, payload))
    return "text/event-stream", _sse(events)


def _ollama_chat(srv: MockServer, body: dict, r: dict) -> tuple[str, bytes]:
    msg: dict[str, Any] = {"role": "assistant", "content": r["text"]}
    if r["thinking"]:
        msg["thinking"] = r["thinking"]
    if r["calls"]:
        msg["tool_calls"] = [{"function": {"name": n, "arguments": a}}
                             for n, a in r["calls"]]
    final = {"model": srv.model, "created_at": "2026-01-01T00:00:00Z",
             "message": msg, "done": True, "done_reason": "stop",
             "prompt_eval_count": 30, "eval_count": 7}
    if body.get("stream") is False:
        return "application/json", json.dumps(final).encode()
    lines = []
    if r["thinking"]:
        lines.append({"model": srv.model, "done": False,
                      "message": {"role": "assistant", "content": "",
                                  "thinking": r["thinking"]}})
    if r["text"]:
        lines.append({"model": srv.model, "done": False,
                      "message": {"role": "assistant", "content": r["text"]}})
    if r["calls"]:
        lines.append({"model": srv.model, "done": False,
                      "message": {"role": "assistant", "content": "",
                                  "tool_calls": msg["tool_calls"]}})
    lines.append({**final, "message": {"role": "assistant", "content": ""}})
    return "application/x-ndjson", "".join(json.dumps(x) + "\n"
                                           for x in lines).encode()


def _handler_for(srv: MockServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:  # quiet
            pass

        def _send(self, code: int, ctype: str, data: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, payload: Any, code: int = 200) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw or b"{}")
            except ValueError:
                return {}

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            srv.paths.append(f"GET {path}")
            kind = srv.kind
            if kind in ("openai_compatible", "llamacpp") and path == "/v1/models":
                srv.list_calls += 1
                return self._json(_openai_models(srv))
            if kind == "llamacpp" and path == "/props":
                return self._json({"default_generation_settings":
                                   {"n_ctx": srv.context}, "total_slots": 1,
                                   "model_path": "/m.gguf"})
            if kind == "anthropic" and path == "/v1/models":
                srv.list_calls += 1
                return self._json(_anthropic_models(srv))
            if kind == "gemini" and path.endswith("/models"):
                srv.list_calls += 1
                return self._json(_gemini_models(srv))
            if kind == "ollama" and path == "/api/tags":
                srv.list_calls += 1
                return self._json({"models": [{"name": srv.model,
                                               "model": srv.model,
                                               "details": {"family": "qwen3"}}]})
            if kind == "ollama" and path == "/api/ps":
                return self._json({"models": []})
            if kind == "ollama" and path == "/api/version":
                return self._json({"version": "0.12.0"})
            self._json({"error": f"no route {path}"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            query = urlsplit(self.path).query
            body = self._body()
            srv.paths.append(f"POST {path}")
            kind = srv.kind
            if kind == "ollama" and path == "/api/show":
                return self._json({"capabilities": ["completion", "tools",
                                                    "thinking"],
                                   "model_info": {"qwen3.context_length":
                                                  srv.context}})
            chat_paths = {
                "openai_compatible": "/v1/chat/completions",
                "llamacpp": "/v1/chat/completions",
                "anthropic": "/v1/messages",
                "ollama": "/api/chat",
            }
            is_chat = (path == chat_paths.get(kind)) or (
                kind == "gemini" and (":generateContent" in path
                                      or ":streamGenerateContent" in path))
            if not is_chat:
                return self._json({"error": f"no route {path}"}, 404)
            srv.requests.append(body)
            if srv.fail_chat > 0:
                srv.fail_chat -= 1
                return self._json({"error": {"message": "mock failure",
                                             "type": "server_error"}}, 500)
            r = srv.next_reply()
            if kind in ("openai_compatible", "llamacpp"):
                ctype, data = _openai_chat(srv, body, r)
            elif kind == "anthropic":
                ctype, data = _anthropic_chat(srv, body, r)
            elif kind == "gemini":
                ctype, data = _gemini_chat(
                    srv, ":streamGenerateContent" in path or "alt=sse" in query, r)
            else:
                ctype, data = _ollama_chat(srv, body, r)
            self._send(200, ctype, data)

    return Handler

#!/usr/bin/env python3
"""Point this at any endpoint and it tells you what you are actually talking to.

The single most useful thing to run before writing integration code. It
identifies the server, lists its models with real metadata, and — importantly —
tests the behaviours that fail *silently* rather than with an error:

  * does `stream_options: {include_usage: true}` actually produce a usage chunk?
  * will tool calls come back, or did someone forget vLLM's
    `--enable-auto-tool-choice`?
  * does structured output actually constrain the response?
  * does the reasoning field come back as `reasoning`, `reasoning_content`,
    or `thinking`?

Usage
-----
    python probe.py http://localhost:11434
    python probe.py http://localhost:8000/v1 --model Qwen/Qwen3-8B
    python probe.py https://api.deepseek.com --key $DEEPSEEK_API_KEY
    python probe.py http://localhost:8080 --deep     # run behaviour tests
    python probe.py --all                            # every configured provider
    python probe.py http://gpu-box:8000/v1 --json    # machine-readable

Only `httpx` is required for detection; `--deep` also needs `openai`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional


try:
    import httpx
except ImportError:
    sys.exit("This script needs httpx: pip install httpx")


G, R, Y, B, DIM, X = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"
)


def ok(s: str) -> str:
    return f"{G}{s}{X}"


def bad(s: str) -> str:
    return f"{R}{s}{X}"


def warn(s: str) -> str:
    return f"{Y}{s}{X}"


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def roots(url: str) -> tuple[str, str]:
    """Return (bare_root, v1_root) for a URL given with or without /v1."""
    u = url.rstrip("/")
    if u.endswith("/v1"):
        return u[:-3].rstrip("/"), u
    if u.endswith("/beta") or u.endswith("/openai"):
        return u.rsplit("/", 1)[0], u
    return u, f"{u}/v1"


def probe_endpoint(url: str, key: Optional[str], timeout: float = 8.0) -> dict[str, Any]:
    bare, v1 = roots(url)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    report: dict[str, Any] = {
        "url": url, "bare_root": bare, "v1_root": v1,
        "kind": "unknown", "endpoints": {}, "models": [], "notes": [],
    }

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as c:

        def probe(path: str, method: str = "GET", **kw) -> Optional[httpx.Response]:
            try:
                r = c.request(method, path, **kw)
                report["endpoints"][path] = r.status_code
                return r
            except httpx.RequestError as exc:
                report["endpoints"][path] = f"unreachable ({type(exc).__name__})"
                return None

        # --- Ollama: native API is the giveaway --------------------------
        r = probe(f"{bare}/api/version")
        if r is not None and r.status_code == 200:
            report["kind"] = "ollama"
            try:
                report["server_version"] = r.json().get("version")
            except Exception:
                pass
            tags = probe(f"{bare}/api/tags")
            if tags is not None and tags.status_code == 200:
                for m in tags.json().get("models", []):
                    name = m.get("name", "")
                    entry: dict[str, Any] = {
                        "id": name,
                        "size_gb": round((m.get("size") or 0) / 1e9, 2),
                        "quant": (m.get("details") or {}).get("quantization_level"),
                        "params": (m.get("details") or {}).get("parameter_size"),
                    }
                    show = probe(f"{bare}/api/show", "POST", json={"model": name})
                    if show is not None and show.status_code == 200:
                        data = show.json()
                        entry["capabilities"] = data.get("capabilities")
                        mi = data.get("model_info") or {}
                        arch = mi.get("general.architecture")
                        entry["context"] = mi.get(f"{arch}.context_length") if arch else None
                    report["models"].append(entry)
            ps = probe(f"{bare}/api/ps")
            if ps is not None and ps.status_code == 200:
                report["loaded"] = [m.get("name") for m in ps.json().get("models", [])]
            report["notes"].append(
                "Use the native /api surface, not /v1 — the OpenAI layer drops "
                "capabilities, context length, quantization, and cannot set num_ctx."
            )
            return report

        # --- llama.cpp: /props is unique ---------------------------------
        r = probe(f"{bare}/props")
        if r is not None and r.status_code == 200:
            try:
                props = r.json()
            except Exception:
                props = {}
            if "default_generation_settings" in props or "model_path" in props:
                report["kind"] = "llamacpp"
                gen = props.get("default_generation_settings") or {}
                report["n_ctx_running"] = gen.get("n_ctx")
                report["total_slots"] = props.get("total_slots")
                report["model_path"] = props.get("model_path")
                report["modalities"] = props.get("modalities")
                report["has_chat_template"] = bool(props.get("chat_template"))
                if report["total_slots"] and report["total_slots"] > 1:
                    report["notes"].append(
                        f"--parallel {report['total_slots']} divides the context: each "
                        f"slot has n_ctx={report['n_ctx_running']}, NOT the full "
                        f"--ctx-size you passed."
                    )

        # --- /v1/models: everything else ---------------------------------
        r = probe(f"{v1}/models")
        if r is None:
            report["error"] = f"Could not reach {v1}/models"
            return report
        if r.status_code == 401 or r.status_code == 403:
            report["error"] = (
                f"HTTP {r.status_code}: authentication required. Pass --key."
            )
            return report
        if r.status_code == 404:
            report["error"] = (
                f"HTTP 404 at {v1}/models. If you passed a bare host, the SDK "
                f"needs the /v1 suffix; if you passed /v1 already, this server "
                f"may not implement model listing."
            )
            return report
        if r.status_code != 200:
            report["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
            return report

        data = r.json()
        entries = data.get("data", data if isinstance(data, list) else [])
        for m in entries:
            entry = {"id": m.get("id"), "owned_by": m.get("owned_by")}
            if m.get("max_model_len") is not None:
                entry["context"] = m["max_model_len"]
            if m.get("parent"):
                entry["lora_parent"] = m["parent"]
            meta = m.get("meta") or {}
            if meta.get("n_ctx_train"):
                entry["n_ctx_train"] = meta["n_ctx_train"]
            report["models"].append(entry)

        if report["kind"] == "unknown":
            owned = {m.get("owned_by") for m in entries}
            if "vllm" in owned or any("max_model_len" in m for m in entries):
                report["kind"] = "vllm"
            elif "llamacpp" in owned:
                report["kind"] = "llamacpp"
            elif "api.deepseek.com" in url:
                report["kind"] = "deepseek"
            elif "api.openai.com" in url:
                report["kind"] = "openai"
            elif "generativelanguage.googleapis.com" in url:
                report["kind"] = "gemini (openai-compat layer)"
            else:
                report["kind"] = "openai_compatible"

        if report["kind"] == "vllm":
            report["notes"].append(
                "Tool calling is OFF unless the server was started with "
                "--enable-auto-tool-choice --tool-call-parser <parser>. Failure "
                "is silent: tool_calls is simply absent. Run with --deep to test."
            )
            for path in ("/version", "/health", "/metrics", "/v1/responses"):
                probe(f"{bare}{path}" if not path.startswith("/v1") else f"{bare}{path}")

    return report


# --------------------------------------------------------------------------
# Behaviour tests (--deep)
# --------------------------------------------------------------------------


def behaviour_tests(url: str, key: Optional[str], model: str) -> dict[str, Any]:
    """Test the things that fail silently rather than erroring."""
    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "--deep needs the openai package"}

    _, v1 = roots(url)
    client = OpenAI(base_url=v1, api_key=key or "not-needed", timeout=60.0,
                    max_retries=0)
    out: dict[str, Any] = {"model": model}
    msg = [{"role": "user", "content": "Reply with exactly: OK"}]

    # 1. Basic chat + which reasoning field (if any) comes back.
    t0 = time.monotonic()
    try:
        r = client.chat.completions.create(model=model, messages=msg, max_tokens=16)
        out["chat"] = True
        out["latency_s"] = round(time.monotonic() - t0, 2)
        m = r.choices[0].message
        for f in ("reasoning", "reasoning_content", "thinking"):
            if getattr(m, f, None):
                out["reasoning_field"] = f
                break
        out["reasoning_field"] = out.get("reasoning_field", None)
        out["usage_on_nonstream"] = bool(getattr(r, "usage", None))
    except Exception as exc:
        out["chat"] = False
        out["chat_error"] = f"{type(exc).__name__}: {exc}"
        return out

    # 2. Does include_usage actually work? Widely assumed, not universal.
    try:
        stream = client.chat.completions.create(
            model=model, messages=msg, max_tokens=16, stream=True,
            stream_options={"include_usage": True},
        )
        saw_usage = any(getattr(ch, "usage", None) for ch in stream)
        out["stream"] = True
        out["stream_include_usage"] = saw_usage
    except Exception as exc:
        out["stream"] = False
        out["stream_error"] = f"{type(exc).__name__}: {exc}"

    # 3. Tool calling — the silent-failure case.
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    }]
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "What's the weather in Boston?"}],
            tools=tools, max_tokens=128,
        )
        calls = r.choices[0].message.tool_calls
        out["tools"] = bool(calls)
        if not calls:
            out["tools_note"] = (
                "Request accepted but no tool_calls returned. On vLLM this "
                "almost always means --enable-auto-tool-choice / "
                "--tool-call-parser were not set at launch. On llama.cpp, "
                "check the model's chat template supports tool syntax."
            )
    except Exception as exc:
        out["tools"] = False
        out["tools_error"] = f"{type(exc).__name__}: {exc}"

    # 4. Structured output via response_format.
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Give me a city and its country."}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "city",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"},
                                       "country": {"type": "string"}},
                        "required": ["city", "country"],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=128,
        )
        json.loads(r.choices[0].message.content or "")
        out["structured_output"] = True
    except Exception as exc:
        out["structured_output"] = False
        out["structured_output_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    # 5. Embeddings on the same endpoint.
    try:
        client.embeddings.create(model=model, input=["probe"])
        out["embeddings_same_model"] = True
    except Exception:
        out["embeddings_same_model"] = False

    return out


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def render(report: dict[str, Any], deep: Optional[dict[str, Any]] = None) -> None:
    print(f"\n{B}{report['url']}{X}")
    if report.get("error"):
        print(f"  {bad(report['error'])}")
        return

    print(f"  detected      {B}{report['kind']}{X}"
          + (f"  v{report['server_version']}" if report.get("server_version") else ""))
    if report.get("n_ctx_running"):
        print(f"  running ctx   {report['n_ctx_running']}"
              + (f"  ({report['total_slots']} slots)" if report.get("total_slots") else ""))
    if report.get("model_path"):
        print(f"  model path    {report['model_path']}")

    base = report["bare_root"]
    reachable = sorted(
        k.replace(base, "") or "/"
        for k, v in report["endpoints"].items()
        if v == 200
    )
    print(f"  endpoints     {', '.join(reachable) or '(none returned 200)'}")
    refused = sorted(
        k.replace(base, "") for k, v in report["endpoints"].items() if v not in (200,)
    )
    if refused:
        print(f"  {DIM}not served    {', '.join(refused)}{X}")

    models = report["models"]
    print(f"\n  {B}models ({len(models)}){X}")
    if not models:
        empty = (
            "none — for llama.cpp/vLLM an empty list is a real problem; "
            "for Ollama it just means nothing has been pulled yet"
        )
        print(f"    {warn(empty)}")
    for m in models[:40]:
        bits = []
        if m.get("context"):
            bits.append(f"{m['context']:,} ctx")
        elif m.get("n_ctx_train"):
            bits.append(f"{m['n_ctx_train']:,} trained ctx")
        if m.get("params"):
            bits.append(m["params"])
        if m.get("quant"):
            bits.append(m["quant"])
        if m.get("size_gb"):
            bits.append(f"{m['size_gb']}GB")
        if m.get("capabilities"):
            bits.append("caps=" + ",".join(m["capabilities"]))
        if m.get("lora_parent"):
            bits.append(f"LoRA of {m['lora_parent']}")
        loaded = " " + ok("[loaded]") if m["id"] in (report.get("loaded") or []) else ""
        print(f"    {m['id']}{loaded}")
        if bits:
            print(f"      {DIM}{'  '.join(bits)}{X}")
    if len(models) > 40:
        print(f"    {DIM}... and {len(models) - 40} more{X}")

    if deep:
        print(f"\n  {B}behaviour ({deep.get('model')}){X}")
        if deep.get("error"):
            print(f"    {bad(deep['error'])}")
        else:
            def row(label: str, key: str, note_key: Optional[str] = None) -> None:
                v = deep.get(key)
                mark = ok("yes") if v else bad("no") if v is False else warn("?")
                print(f"    {label:<24}{mark}")
                for nk in (note_key, f"{key}_error", f"{key}_note"):
                    if nk and deep.get(nk):
                        print(f"      {DIM}{deep[nk]}{X}")

            row("chat", "chat")
            if deep.get("latency_s"):
                print(f"    {'latency':<24}{deep['latency_s']}s")
            row("streaming", "stream")
            row("stream usage chunk", "stream_include_usage")
            row("tool calling", "tools")
            row("structured output", "structured_output")
            row("embeddings (same model)", "embeddings_same_model")
            rf = deep.get("reasoning_field")
            print(f"    {'reasoning field':<24}"
                  + (ok(rf) if rf else f"{DIM}none returned{X}"))

    for note in report.get("notes", []):
        print(f"\n  {warn('note')} {note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="base URL, with or without /v1")
    ap.add_argument("--key", help="API key / bearer token")
    ap.add_argument("--model", help="model id for --deep (default: first discovered)")
    ap.add_argument("--deep", action="store_true",
                    help="run behaviour tests (costs a few tokens)")
    ap.add_argument("--all", action="store_true",
                    help="probe every endpoint in providers.yaml")
    ap.add_argument("--config", help="path to providers.yaml")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--timeout", type=float, default=8.0)
    args = ap.parse_args()

    targets: list[tuple[str, Optional[str]]] = []
    if args.all:
        from apps.core.llmkit.config import load_configs

        for cfg in load_configs(args.config).values():
            if cfg.base_url:
                targets.append((cfg.base_url, cfg.api_key))
    elif args.url:
        targets.append((args.url, args.key))
    else:
        ap.error("give a URL or --all")

    results = []
    for url, key in targets:
        report = probe_endpoint(url, key, args.timeout)
        deep = None
        if args.deep and report["models"]:
            model = args.model or report["models"][0]["id"]
            deep = behaviour_tests(url, key, model)
        if args.json:
            results.append({"report": report, "behaviour": deep})
        else:
            render(report, deep)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

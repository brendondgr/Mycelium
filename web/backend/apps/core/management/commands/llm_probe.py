"""Probe one configured model server: what it is and what it really does.

    manage.py llm_probe local
    manage.py llm_probe claude --deep

Only servers declared in ``mycelium.toml`` (or ``local`` from ``.env``) can be
probed; no URL is accepted on the command line. The probe identifies the server
and lists its models with their context windows. ``--deep`` also exercises it
the way Mycelium uses it — a reply, a streamed reply and a function call through
the same client the components use (component ``preflight``) — and, for an
OpenAI-shaped server, runs the llm-integration skill's behaviour tests
(``apps/core/llmkit/probe.py``: usage in streams, tool calls, structured
output, which reasoning field comes back). ``--deep`` spends a few tokens.

A cloud server is probed only while ``llm.allow_cloud`` is true. The key is read
from the variable the server names and is never printed.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.core import llm_servers

#: Kinds whose wire format the skill's probe.py understands.
_HTTP_PROBE_KINDS = ("openai_compatible", "vllm", "llamacpp", "ollama", "openai",
                     "deepseek")


class Command(BaseCommand):
    help = "Identify one configured model server and test what it supports."

    def add_arguments(self, parser) -> None:
        parser.add_argument("server", help="a server name from mycelium.toml")
        parser.add_argument("--deep", action="store_true",
                            help="run behaviour tests (costs a few tokens)")
        parser.add_argument("--model", help="model to test (default: the "
                            "server's configured model)")
        parser.add_argument("--json", action="store_true",
                            help="machine-readable output")

    def handle(self, *args, **options) -> None:
        name = options["server"]
        table = llm_servers.table()
        entry = table.servers.get(name)
        if entry is None:
            raise CommandError(f"No server named {name!r}. Known: "
                               f"{', '.join(sorted(table.servers))}.")
        if not table.callable(name):
            raise CommandError(f"Server {name!r} may not be called: "
                               f"{llm_servers._why_not(table, name)}.")
        model = options.get("model") or entry["model"]
        report: dict = {
            "server": name, "kind": entry["kind"], "label": entry["label"],
            "location": entry["location"], "base_url": entry["base_url"] or None,
            "model": model, "api_key_env": entry["api_key_env"] or None,
        }
        ok, error = llm_servers.health(name, force=True)
        report["answers"] = ok
        report["error"] = error
        report["models"] = next(
            (row["models"] for row in llm_servers.options()
             if row["server"] == name), [])
        report["context_window"] = llm_servers.context_window(name, model)

        http_report = None
        if entry["kind"] in _HTTP_PROBE_KINDS and entry["base_url"]:
            from apps.core.llmkit import probe

            http_report = probe.probe_endpoint(
                entry["base_url"], llm_servers.api_key(entry) or None,
                timeout=float(entry["connect_timeout"]) + 3.0)
        deep = None
        if options.get("deep"):
            deep = {"mycelium": _client_checks(name, model)}
            if http_report is not None and entry["kind"] != "ollama" and model:
                from apps.core.llmkit import probe

                deep["wire"] = probe.behaviour_tests(
                    entry["base_url"], llm_servers.api_key(entry) or None, model)

        failed = not ok or bool(deep and not all(
            v is True for k, v in deep["mycelium"].items() if k != "error"))
        if options.get("json"):
            self.stdout.write(json.dumps(
                {**report, "http": http_report, "deep": deep, "ok": not failed},
                indent=2, default=str))
        else:
            self._render(report, http_report, deep)
        if failed:
            raise CommandError(f"Server {name!r} did not pass the probe.")

    def _render(self, report, http_report, deep) -> None:
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"{report['server']} — {report['label']}"))
        w(f"  kind {report['kind']}, runs {report['location']}, "
          f"model {report['model'] or '-'}")
        if report["base_url"]:
            w(f"  base_url {report['base_url']}")
        if report["api_key_env"]:
            w(f"  key from ${report['api_key_env']} (not shown)")
        if report["answers"]:
            w(self.style.SUCCESS("  answers"))
        else:
            w(self.style.ERROR(f"  does not answer: {report['error']}"))
        w(f"  context window {report['context_window']}")
        for model in report["models"][:12]:
            caps = ", ".join(model["capabilities"])
            w(f"    {model['id']}  context {model['context_window'] or '?'}  {caps}")
        if http_report is not None:
            w(f"  detected {http_report.get('kind')}"
              + (f" v{http_report['server_version']}"
                 if http_report.get("server_version") else ""))
            for note in http_report.get("notes") or []:
                w(self.style.WARNING(f"  note: {note}"))
        if deep:
            w(self.style.MIGRATE_HEADING("  Through Mycelium's client"))
            for check, value in deep["mycelium"].items():
                if check == "error":
                    if value:
                        w(self.style.ERROR(f"    {value}"))
                    continue
                style = self.style.SUCCESS if value is True else self.style.ERROR
                w(style(f"    {check:<12} {'yes' if value is True else value}"))
            if deep.get("wire"):
                w(self.style.MIGRATE_HEADING("  Wire behaviour (probe.py)"))
                for key, value in deep["wire"].items():
                    w(f"    {key:<24} {value}")


def _client_checks(server: str, model: str) -> dict:
    """A reply, a streamed reply and one function call through the shared
    client, as component ``preflight``."""
    from apps.core.llm import build_llm_client

    out: dict = {"reply": False, "stream": False, "tool_call": False, "error": None}
    try:
        client = build_llm_client(component="preflight", server=server)
        response = client.complete(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            model=model or None, max_tokens=256)
        out["reply"] = bool((response.content or "").strip()) or (
            f"empty reply (finish {response.finish_reason})")
        pieces: list[str] = []
        streamed = client.complete_stream(
            [{"role": "user", "content": "Count from 1 to 5."}],
            model=model or None, max_tokens=256,
            on_delta=lambda kind, text: pieces.append(text) if kind == "text"
            else None)
        out["stream"] = bool(pieces and streamed.content) or "no streamed text"
        tool = {"type": "function", "function": {
            "name": "get_weather", "description": "Weather for a city.",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}},
                           "required": ["city"]}}}
        called = client.complete(
            [{"role": "user", "content": "What is the weather in Boston? "
              "Use the tool."}],
            model=model or None, tools=[tool], tool_choice="auto", max_tokens=512)
        out["tool_call"] = any(c.name == "get_weather" for c in called.tool_calls) \
            or "no function call came back"
    except Exception as exc:  # noqa: BLE001 - the probe reports, never crashes
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out

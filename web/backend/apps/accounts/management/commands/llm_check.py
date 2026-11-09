"""Diagnose the configured LLM endpoint from inside the backend.

Onboarding's "Grow my profile" silently falls back to a deterministic draft when
the language model cannot be reached or returns nothing usable. This command makes
that path observable: it prints the effective ``LLM_*`` settings, sends one tiny
completion to confirm the endpoint answers, and runs the real profile extractor on
a sample so you can see whether every field comes back.

    uv run --project web/backend python web/backend/manage.py llm_check

It then lists every model server the instance knows (``[llm.providers.*]`` in
``mycelium.toml``, plus ``local``): its kind, where it runs, whether it answers,
the models it reports with their context windows, and which server each routed
component uses.

``--strict`` exits non-zero when a server some component is routed to (the
default server, or one named in ``[llm.routes]``) is misconfigured or does not
answer. A declared server nothing routes to is reported but never fails the
check, so an unused cloud server cannot skip a night.

Common gotcha: when the backend runs in a container, ``LLM_BASE_URL`` pointing at
``localhost`` refers to the *container*, not your host. Use ``host.docker.internal``
(add it via compose ``extra_hosts``) or the host's LAN IP instead.
"""

from __future__ import annotations

import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SAMPLE_TEXT = (
    "Dr. Ada Lovelace, Analytical Engine Institute. Research interests: "
    "computational mathematics, theory of computation, and early computing "
    "machines. Recent work: 'Notes on the Analytical Engine' and 'On Recursion'. "
    "Methods: formal proofs and algorithm design. Skills: mechanical computation, "
    "mathematical notation."
)


class Command(BaseCommand):
    help = "Check that the configured LLM endpoint is reachable and usable."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--strict",
            action="store_true",
            help=(
                "Exit non-zero when the endpoint is missing or unreachable, so "
                "automation (e.g. the daily run) can detect an LLM outage."
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        strict = bool(options.get("strict"))
        self._print_settings()
        failures = self._servers()
        if failures and strict:
            raise CommandError("; ".join(failures))
        if not settings.LLM_MODEL:
            message = (
                "LLM_MODEL is empty — synthesis will always use the "
                "deterministic fallback. Set LLM_MODEL to the served model."
            )
            self.stderr.write(self.style.ERROR(message))
            if strict:
                raise CommandError(message)
            return
        if not self._ping():
            if strict:
                raise CommandError(
                    "LLM endpoint is unreachable or returned nothing usable."
                )
            return
        self._extract()

    # -- steps ---------------------------------------------------------------

    def _print_settings(self) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("Effective LLM settings"))
        for name in (
            "LLM_BASE_URL",
            "LLM_MODEL",
            "LLM_TIMEOUT",
            "LLM_TEMPERATURE",
            "LLM_MAX_TOKENS",
            "LLM_REASONING",
            "LLM_REASONING_STYLE",
        ):
            self.stdout.write(f"  {name} = {getattr(settings, name, '<unset>')!r}")
        # Never print the key itself — just whether one is set.
        has_key = bool(getattr(settings, "LLM_API_KEY", "") not in ("", "EMPTY"))
        self.stdout.write(f"  LLM_API_KEY set = {has_key}")

    def _servers(self) -> list[str]:
        """List every server and route; return problems with routed servers."""
        from apps.core import llm_servers

        table = llm_servers.table()
        routed = {r["server"] for r in llm_servers.routes().values()}
        routed |= {r.partition(":")[0] for r in table.routes.values()}
        routed.add(table.default)
        failures: list[str] = []
        self.stdout.write(self.style.MIGRATE_HEADING("\nModel servers"))
        for row in llm_servers.options(force=True):
            name = row["server"]
            mark = "*" if row["default"] else " "
            state = ("answers" if row["ok"] else f"down: {row['error']}")
            line = (f" {mark}{name:<12} {row['kind']:<18} {row['location']:<7} "
                    f"model={row['model'] or '-'}  {state}")
            style = self.style.SUCCESS if row["ok"] else (
                self.style.ERROR if name in routed else self.style.WARNING)
            self.stdout.write(style(line))
            for model in row["models"][:8]:
                ctx = model["context_window"] or "?"
                self.stdout.write(f"      {model['id']}  context {ctx}")
            if len(row["models"]) > 8:
                self.stdout.write(f"      … {len(row['models']) - 8} more")
            if name in routed and not row["ok"]:
                failures.append(f"server {name!r} (routed) {row['error']}")
        for problem in table.problems(_environ()):
            routed_problem = any(f"[llm.providers.{n}]" in problem
                                 or f"names {n!r}" in problem for n in routed)
            if routed_problem or problem.startswith(("llm.default", "llm.routes")):
                failures.append(problem)
                self.stderr.write(self.style.ERROR(f"  ✗ {problem}"))
            else:
                self.stdout.write(self.style.WARNING(f"  ! {problem}"))
        self.stdout.write(self.style.MIGRATE_HEADING("\nRoutes"))
        for component, route in llm_servers.routes().items():
            label = "everything else" if component == "*" else component
            line = (f"  {label:<28} → {route['server']} ({route['model'] or '-'}, "
                    f"{route['location']})")
            if route["problem"]:
                line += f"  [asked for {route['requested']}: {route['problem']}]"
                failures.append(f"route {label}: {route['problem']}")
            self.stdout.write(line)
        return failures

    def _ping(self) -> bool:
        from apps.core.llm import LLMMessage, build_llm_client

        self.stdout.write(self.style.MIGRATE_HEADING("\nPinging the endpoint"))
        try:
            client = build_llm_client(component="preflight")
            response = client.complete(
                [
                    LLMMessage("system", "You are a health check. Reply with: ok"),
                    LLMMessage("user", "Reply with the two letters: ok"),
                ]
            )
        except Exception as exc:  # noqa: BLE001 — surface the real reason
            self.stderr.write(
                self.style.ERROR(f"  Endpoint call failed: {type(exc).__name__}: {exc}")
            )
            self.stderr.write(
                "  If this is a connection error and the backend runs in a "
                "container, 'localhost' points at the container, not your host."
            )
            return False
        content = (response.content or "").strip()
        self.stdout.write(f"  finish_reason = {response.finish_reason!r}")
        self.stdout.write(f"  content       = {content[:120]!r}")
        if response.reasoning:
            self.stdout.write(f"  reasoning     = {response.reasoning[:80]!r} …")
        if not content:
            self.stderr.write(
                self.style.WARNING(
                    "  The model returned no content. If finish_reason is "
                    "'length', raise LLM_MAX_TOKENS (reasoning is eating the budget)."
                )
            )
            return False
        self.stdout.write(self.style.SUCCESS("  Endpoint reachable."))
        return True

    def _extract(self) -> None:
        from apps.accounts.intake.extract import extract_profile_fields

        self.stdout.write(self.style.MIGRATE_HEADING("\nSample profile extraction"))
        # No fallback: we want to see exactly what the model produced.
        fields = extract_profile_fields(SAMPLE_TEXT)
        self.stdout.write(json.dumps(fields, indent=2))
        missing = [key for key, value in fields.items() if not value]
        if missing:
            self.stderr.write(
                self.style.WARNING(
                    "  Empty fields: "
                    + ", ".join(missing)
                    + ". The model answered but did not fill these — check the "
                    "model and prompt, or the backend logs for parse warnings."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("  All five fields populated."))


def _environ() -> dict[str, str]:
    return dict(os.environ)

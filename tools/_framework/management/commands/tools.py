"""``manage.py tools`` — the import script and tool housekeeping.

manage.py tools check [--json] [--fresh]   run (or show) the load report
manage.py tools plan [--json]              the nightly stage plan for loaded tools
manage.py tools migrations                 every loaded tool's migrations applied?
manage.py tools uninstall NAME --yes       migrate a tool to zero (tables dropped)
"""

from __future__ import annotations

import json
import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from tools._framework import loader, nightly


class Command(BaseCommand):
    help = "Check, plan, verify and uninstall modular tools."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        check = sub.add_parser("check", help="the load report")
        check.add_argument("--json", action="store_true")
        check.add_argument(
            "--fresh",
            action="store_true",
            help="ignore the cached report and re-probe every tool",
        )
        check.add_argument(
            "--lenient", action="store_true", help="exit 0 even if a tool failed"
        )
        plan = sub.add_parser("plan", help="the nightly stages loaded tools contribute")
        plan.add_argument("--json", action="store_true")
        sub.add_parser("migrations", help="are every loaded tool's migrations applied?")
        uninstall = sub.add_parser("uninstall", help="migrate one tool to zero")
        uninstall.add_argument("name")
        uninstall.add_argument("--yes", action="store_true")

    def handle(self, *args, **opts):
        return getattr(self, f"_{opts['action']}")(**opts)

    # ------------------------------------------------------------------ #

    def _report(self, fresh: bool) -> loader.LoadReport:
        report = settings.TOOLS_REPORT
        if fresh:
            report = loader.preflight(
                tool_configs=settings.INSTANCE.tools,
                environ=dict(os.environ),
                config_warnings=list(settings.INSTANCE.warnings),
            )
            report.fingerprint = settings.TOOLS_REPORT.fingerprint
            loader.write_cached(report)
        return report

    def _check(
        self, *, json: bool = False, fresh: bool = False, lenient: bool = False, **_
    ):
        report = self._report(fresh)
        if json:
            self.stdout.write(report.to_json(compact=True))
        else:
            self.stdout.write(report.table())
            for warning in report.warnings:
                self.stdout.write(self.style.WARNING(f"warning: {warning}"))
        failed = [n for n in report.order if report.tools[n].state == loader.FAILED]
        if failed and not lenient:
            raise CommandError(f"tools failed to load: {', '.join(failed)}")

    def _plan(self, *, json: bool = False, **_):
        run, skipped = nightly.plan_for(settings.TOOLS_REPORT.loaded())
        if json:
            self.stdout.write(
                _json(
                    {
                        "run": [_planned(p) for p in run],
                        "skipped": [
                            _planned(p)
                            | {"state": settings.TOOLS_REPORT.state(p.owner)}
                            for p in skipped
                        ],
                    }
                )
            )
            return
        for p in run:
            args = " ".join(p.stage.args)
            self.stdout.write(
                f"{p.stage.phase:<9} {p.owner:<15} {p.stage.command} {args}"
            )
        for p in skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"SKIPPED   {p.owner:<15} {p.stage.command} "
                    f"({settings.TOOLS_REPORT.state(p.owner)})"
                )
            )

    def _migrations(self, **_):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        labels = {
            settings.TOOLS_REPORT.tools[n].label for n in settings.TOOLS_REPORT.loaded()
        }
        targets = [k for k in executor.loader.graph.leaf_nodes() if k[0] in labels]
        unapplied = [m for m, _back in executor.migration_plan(targets)]
        if unapplied:
            raise CommandError(
                "unapplied tool migrations: "
                + ", ".join(f"{m.app_label}.{m.name}" for m in unapplied)
            )
        self.stdout.write(
            f"all migrations applied for: {', '.join(sorted(labels)) or 'no tools'}"
        )

    def _uninstall(self, *, name: str, yes: bool = False, **_):
        report = settings.TOOLS_REPORT
        item = report.tools.get(name)
        if item is None:
            raise CommandError(f"no tool named {name!r} is installed")
        if item.core:
            raise CommandError(
                f"{name} is a core tool; the platform cannot run without it"
            )
        dependents = [n for n in report.order if name in report.tools[n].depends_on]
        if dependents:
            raise CommandError(
                f"{', '.join(dependents)} depend on {name}; uninstall them first"
            )
        if not yes:
            raise CommandError(
                f"This drops every table of {name} (app label {item.label}). "
                "Re-run with --yes to confirm."
            )
        call_command("migrate", item.label, "zero", interactive=False)
        self.stdout.write(f"{name}: migrated to zero. Delete tools/{name}/ to finish.")


def _planned(p):
    return {
        "command": p.stage.command,
        "phase": p.stage.phase,
        "owner": p.owner,
        "args": list(p.stage.args),
        "intro": p.stage.intro,
    }


def _json(data) -> str:
    return json.dumps(data, indent=1)

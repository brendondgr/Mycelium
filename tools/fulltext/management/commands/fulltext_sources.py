"""Which full-text sources this instance can use, and why any cannot.

    manage.py fulltext_sources            configuration only, no network
    manage.py fulltext_sources --check    also ask each keyed provider, live

``--check`` tells a rejected key apart from a valid key this server is not
entitled to use (Elsevier and Wiley authorise by the requesting IP), which need
different fixes. It makes about a dozen requests and prints no secrets.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from tools.fulltext import config
from tools.fulltext.engine.probe import probe_all


class Command(BaseCommand):
    help = "List the full-text sources and whether each is usable here."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Probe each keyed provider live (a few requests).",
        )

    def handle(self, *args, check=False, **options):
        engine = config.engine()
        order = engine.order
        email = config.contact_email()
        self.stdout.write(f"contact email: {email or '(none — Unpaywall is off)'}")
        if check:
            rows = [
                (p.source, p.state, p.detail) for p in probe_all(engine.fetcher, order)
            ]
        else:
            rows = [
                (s["source"], "on" if s["available"] else "off", s["reason"] or "")
                for s in engine.sources()
                if s["source"] in order
            ]
        width = max(len(r[0]) for r in rows)
        state_width = max(len(r[1]) for r in rows)
        for source, state, detail in rows:
            line = f"  {source:<{width}}  {state:<{state_width}}  {detail}".rstrip()
            style = self.style.SUCCESS if state == "on" else self.style.WARNING
            self.stdout.write(style(line))
        left_out = [s["source"] for s in engine.sources() if s["source"] not in order]
        if left_out:
            self.stdout.write(f"not in [tools.fulltext] sources: {', '.join(left_out)}")

"""Start (or report on) the nightly run's model-call budget.

``manage.py nightly_budget --start`` prints, as JSON, the two environment
variables the nightly orchestrator hands every stage so they share one
``nightly.model_calls`` budget (see ``apps.core.llm_budget``). Without
``--start`` it reports the budget and, inside a run, what has been spent.
"""

import json

from django.core.management.base import BaseCommand

from apps.core import llm_budget


class Command(BaseCommand):
    help = "Print the nightly model-call budget's starting point (--start) or status."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start",
            action="store_true",
            help="print the environment a nightly run hands its stages, as JSON",
        )

    def handle(self, *args, **options):
        if options["start"]:
            self.stdout.write(json.dumps(llm_budget.start()))
            return
        cap = llm_budget.limit()
        spent = llm_budget.used()
        self.stdout.write(
            json.dumps(
                {
                    "limit": "unlimited" if cap is None else cap,
                    "used": spent,  # null outside a nightly run
                }
            )
        )

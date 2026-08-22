"""Report which device the cross-encoder rerank stage will actually use.

    uv run --project web/backend python manage.py rerank_device
    uv run --project web/backend python manage.py rerank_device --load

The mirror of ``embedding_device`` for the reranker. Without ``--load`` it
reports what the settings resolve to; with ``--load`` it builds the session and
prints the providers ONNX Runtime really chose — the only way to confirm a GPU on
a server rather than infer one from configuration.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.content import reranking


class Command(BaseCommand):
    help = "Show the resolved device for the cross-encoder rerank stage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--load",
            action="store_true",
            help="Build the model so the live session's providers are reported.",
        )
        parser.add_argument(
            "--json", action="store_true", help="Emit JSON instead of a table."
        )

    def handle(self, *args, **options):
        info = reranking.describe_device(load=options["load"])
        if options["json"]:
            self.stdout.write(json.dumps(info, indent=2, sort_keys=True))
            return

        for key, value in info.items():
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value) or "—"
            self.stdout.write(f"{key:>20}: {value}")

        if not info["enabled"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nThe rerank stage is OFF (RERANK_ENABLED=false). It ships off "
                    "because its evidence is a preference, not a measurement — see "
                    "apps/content/reranking.py."
                )
            )
        elif info["resolved"] == "cpu" and not info["cuda_available"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nNo CUDAExecutionProvider — reranking on the CPU. On a GPU "
                    "host install the GPU runtime: uv sync --extra embeddings-gpu"
                )
            )
        elif info["resolved"] == "cuda":
            self.stdout.write(self.style.SUCCESS("\nReranking on the GPU."))

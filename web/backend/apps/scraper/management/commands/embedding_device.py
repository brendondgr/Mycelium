"""Report (and optionally benchmark) the device the embedder runs on.

    uv run --project web/backend python web/backend/manage.py embedding_device
    uv run --project web/backend python web/backend/manage.py \
        embedding_device --benchmark 256

Without ``--benchmark`` this only resolves the configuration and lists ONNX
Runtime's providers — it does not load the model. With ``--benchmark`` it embeds
N synthetic texts (after a warm-up pass, so the model download/load is excluded)
and reports throughput plus the providers the live session actually chose. That
last line is the only real proof the GPU is being used:

    session providers: CUDAExecutionProvider, CPUExecutionProvider

If it says only ``CPUExecutionProvider`` on a CUDA host, the CPU-only runtime is
installed — re-sync with ``--extra embeddings-gpu``.
"""

from __future__ import annotations

import json
import time

from django.core.management.base import BaseCommand, CommandError

from apps.scraper.embedding import (
    CUDA,
    FastEmbedEmbedder,
    _session_providers,
    describe_device,
)


class Command(BaseCommand):
    help = "Show which device (CUDA GPU or CPU) local embedding will run on."

    def add_arguments(self, parser):
        parser.add_argument(
            "--benchmark",
            type=int,
            nargs="?",
            const=256,
            default=0,
            metavar="N",
            help="Embed N synthetic texts and report throughput (default 256).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the report as JSON instead of text.",
        )

    def handle(self, *args, **options):
        count = options["benchmark"]
        info = describe_device()

        if count and not info["installed"]:
            raise CommandError(
                "fastembed is not installed. Install the CPU runtime with "
                "`uv sync --extra embeddings`, or the GPU runtime with "
                "`uv sync --extra embeddings-gpu`."
            )

        if count:
            embedder = FastEmbedEmbedder()
            embedder(["warm up the model so the load is not timed"])
            info["session_providers"] = _session_providers(embedder._ensure_model())
            texts = [
                f"Sample research abstract number {i} about graph neural networks "
                f"applied to materials discovery and catalysis."
                for i in range(count)
            ]
            started = time.perf_counter()
            vectors = embedder(texts)
            elapsed = time.perf_counter() - started
            info["benchmark"] = {
                "texts": count,
                "seconds": round(elapsed, 3),
                "texts_per_second": round(count / elapsed, 1) if elapsed else None,
                "dimensions": len(vectors[0]) if vectors else 0,
            }

        if options["json"]:
            self.stdout.write(json.dumps(info, indent=2))
            return

        style = self.style.SUCCESS if info["device"] == CUDA else self.style.WARNING
        self.stdout.write(f"model:               {info['model']}")
        self.stdout.write(f"requested device:    {info['requested']}")
        self.stdout.write(style(f"resolved device:     {info['device']}"))
        if info["device_id"] is not None:
            self.stdout.write(f"device id:           {info['device_id']}")
        self.stdout.write(f"batch size:          {info['batch_size']}")
        self.stdout.write(f"fastembed installed: {info['installed']}")
        self.stdout.write(f"onnxruntime:         {info['onnxruntime_version'] or '—'}")
        self.stdout.write(
            f"available providers: {', '.join(info['available_providers']) or '—'}"
        )
        if info["session_providers"]:
            self.stdout.write(
                f"session providers:   {', '.join(info['session_providers'])}"
            )
        bench = info.get("benchmark")
        if bench:
            self.stdout.write(
                f"benchmark:           {bench['texts']} texts in {bench['seconds']}s "
                f"({bench['texts_per_second']} texts/s, {bench['dimensions']}-dim)"
            )
        if info["device"] != CUDA:
            self.stdout.write(
                self.style.NOTICE(
                    "Embedding on the CPU. For GPU acceleration on a CUDA host: "
                    "uv sync --project web/backend --extra embeddings-gpu "
                    "(and leave EMBEDDING_DEVICE=auto)."
                )
            )

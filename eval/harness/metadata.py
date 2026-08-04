"""`ir_metadata` emission, alongside every run file.

LongEval asks participants to track indexing and retrieval resource consumption
in the `ir-metadata` format (https://www.ir-metadata.org/), and the CLEF 2026
submission skeleton expects an `ir-metadata.yml` next to each `run.txt.gz`.
Emitting it on every run means a future TIRA submission needs no extra work — and
it records the provenance a reader needs to trust the number.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any


def _resources() -> dict[str, Any]:
    import os

    return {
        "platform": {
            "operating system": platform.platform(),
            "python": platform.python_version(),
        },
        "cpu": {
            "model": platform.processor() or "unknown",
            "cores": os.cpu_count(),
        },
        # Stated explicitly: this host has no CUDA device, so every number was
        # produced on CPU. A GPU run would be faster but identical in ranking.
        "gpu": {"model": "none", "count": 0},
    }


def write_ir_metadata(record, path: Path) -> Path:
    """Write the ir_metadata sidecar for one run."""
    import yaml

    payload = {
        "schema version": 0.1,
        "tag": f"mycelium-{record.arm}",
        "method": {
            "name": record.arm,
            "description": (
                "Mycelium production ranking stack (apps.content) evaluated "
                "through eval/. The arm calls production functions directly; it "
                "contains no ranking logic of its own."
            ),
        },
        "actor": {"team": "Mycelium"},
        "research goal": {
            "description": (
                "Measure whether the deployed retrieval and fusion stack is sound "
                "against an external collection with published baselines."
            )
        },
        "platform": _resources(),
        "implementation": {
            "executable": {
                "cmd": "uv run --project eval eval/run.py",
                "version": {"commit": record.git_sha, "dirty": record.dirty},
            }
        },
        "data": {
            "training data": {"name": record.snapshot},
            "test data": {"name": record.snapshot},
        },
        "evaluation": {
            "qrels": record.qrels,
            "corpus scope": record.corpus_scope,
            "corpus documents": record.corpus_docs,
            "queries": record.n_queries,
            "measures": record.metrics,
        },
        "resources": {
            "runtime": {"wallclock seconds": record.wall_clock_s},
            "embedding model": record.embedding_model or "none (lexical arm)",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path

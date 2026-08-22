"""One-time SPLADE encode of the production corpora (`EXP-2026-08-014`).

    uv run --project eval python .../code/encode_splade.py

The three-channel arm needs a learned-sparse index over the same `ContentItem`
rows the other arms retrieve from. This reuses `eval/harness/neural.py`'s
`splade_encode` unchanged — content-addressed cache, shard checkpointing, one
ONNX session — rather than writing a second encoder, because two encoders is two
chances to encode something subtly different and then compare them as if they
were the same.

Encoded per content type, so a change to one corpus does not invalidate the
others. Roughly 39,000 documents at the ~24 docs/s measured in
`EXP-2026-08-008`, so about half an hour, once.

Run this **alone**: `EXP-2026-08-008` ISSUES §5 measured that two concurrent ONNX
sessions on this host are catastrophically slower than serial.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EXP_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DATABASE_URL"] = os.environ.get(
    "MYCELIUM_DATABASE_URL", "postgres://mycelium:mycelium@127.0.0.1:11450/mycelium"
)
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH", str(REPO_ROOT / "data" / "eval-cache" / "fastembed")
)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

#: The snapshot label baked into the cache key. Bumping it forces a re-encode,
#: which is the correct response to the store's contents changing.
SNAPSHOT = "mycelium-store-2026-08-22"


@dataclass(frozen=True)
class Doc:
    """The two fields `splade_encode` needs: a stable id and the text to index."""

    id: str
    text: str


def corpus(content_type: str) -> list[Doc]:
    from apps.content.lexical import _item_text
    from apps.content.models import ContentItem

    return [
        Doc(id=str(item.id), text=_item_text(item))
        for item in ContentItem.objects.filter(
            type=content_type, embedding__isnull=False
        ).order_by("id")
    ]


def main() -> int:
    import django

    django.setup()
    from harness.neural import splade_encode

    for content_type in ("paper", "grant", "conference", "fellowship"):
        docs = corpus(content_type)
        started = time.time()
        print(f"=== {content_type}: {len(docs)} docs ===", flush=True)
        matrix = splade_encode(
            docs,
            snapshot=SNAPSHOT,
            scope=content_type,
            log=lambda m: print(f"  {m}", flush=True),
        )
        print(
            f"=== {content_type}: {matrix.shape}, {matrix.nnz:,} non-zeros, "
            f"{time.time() - started:.0f}s ===",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

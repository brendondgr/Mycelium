"""`ir_datasets` collections adapted to the shapes the ranking stack expects.

Two adapters, both deliberately thin:

- :class:`EvalDoc` satisfies :class:`tools.retrieval.protocols.Retrievable`, so a
  LongEval document can be handed straight to `build_bm25_index`, `fuse_interest`,
  and `_build_pool` — the production functions, unmodified.
- :func:`queries` turns a topic into the single-interest `SearchInterest` the pool
  builder treats as one "interest". A LongEval query is a keyword string, so
  `label`, `query_text`, and `embed_text` are all that string; the multi-interest
  and cluster machinery is simply not exercised by this collection (see the claims
  boundary in `docs/evaluation.md`).

Nothing here touches Django's database. `apps.content` is importable without a
connection as long as settings are configured, which `eval/run.py` does.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EVAL_ROOT = Path(__file__).resolve().parent.parent
COLLECTIONS_FILE = EVAL_ROOT / "collections.toml"


@dataclass(slots=True)
class EvalDoc:
    """One collection document, shaped as a `Retrievable`.

    `metadata` carries `title` and `abstract` because that is the fallback
    `tools.retrieval.lexical._item_text` uses when no prebuilt `search_text` is
    present — which is exactly how a scraped paper looks in production.
    """

    id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None

    @property
    def text(self) -> str:
        meta = self.metadata
        title = meta.get("title") or ""
        abstract = meta.get("abstract") or ""
        return f"{title} {abstract}".strip()


@dataclass(frozen=True, slots=True)
class Collection:
    """One row of `collections.toml`, resolved."""

    id: str
    ir_datasets_id: str
    snapshot: str
    timestamp: str
    scoreable: bool
    qrels_variants: tuple[str, ...]
    default_qrels: str | None = None
    note: str = ""
    blocked_reason: str = ""

    def dataset_id(self, qrels: str | None = None) -> str:
        """The `ir_datasets` id, with the qrels variant substituted if needed."""
        if "{qrels}" not in self.ir_datasets_id:
            return self.ir_datasets_id
        variant = qrels or self.default_qrels
        if not variant:
            raise ValueError(f"{self.id} needs a qrels variant but none was given")
        return self.ir_datasets_id.format(qrels=variant)


def load_collections(path: Path | None = None) -> dict[str, Collection]:
    """Every declared collection, keyed by its short id."""
    data = tomllib.loads((path or COLLECTIONS_FILE).read_text())
    out: dict[str, Collection] = {}
    for row in data.get("collection", []):
        out[row["id"]] = Collection(
            id=row["id"],
            ir_datasets_id=row["ir_datasets_id"],
            snapshot=row["snapshot"],
            timestamp=row.get("timestamp", ""),
            scoreable=bool(row.get("scoreable", False)),
            qrels_variants=tuple(row.get("qrels_variants", ())),
            default_qrels=row.get("default_qrels"),
            note=row.get("note", ""),
            blocked_reason=row.get("blocked_reason", ""),
        )
    return out


def _register(dataset_id: str) -> None:
    """Register only the LongEval family `dataset_id` belongs to.

    Registration is eager and expensive: `ir_datasets_longeval` constructs every
    subset at import time, and constructing one downloads and extracts its whole
    collection (~2.8 GB for the 2026 family, ~2 GB for 2025). Registering both
    would make a 2026 run pay for the 2025 corpora it never touches, so the
    families are registered independently, on demand.
    """
    if dataset_id.startswith("longeval-sci-2026"):
        from ir_datasets_longeval.datasets.longeval_sci_2026 import register

    elif dataset_id.startswith("longeval-sci"):
        from ir_datasets_longeval.datasets.longeval_sci import register

    else:
        raise ValueError(f"no LongEval family registers {dataset_id!r}")
    register()


def load_dataset(collection: Collection, qrels: str | None = None):
    """The raw `ir_datasets` dataset for a collection."""
    import ir_datasets

    dataset_id = collection.dataset_id(qrels)
    _register(dataset_id)
    return ir_datasets.load(dataset_id)


def docs(dataset, *, limit: int | None = None) -> Iterator[EvalDoc]:
    """Stream the collection's documents as `Retrievable` objects."""
    for i, doc in enumerate(dataset.docs_iter()):
        if limit is not None and i >= limit:
            return
        yield EvalDoc(
            id=doc.doc_id,
            metadata={
                "title": getattr(doc, "title", "") or "",
                "abstract": getattr(doc, "abstract", "") or "",
            },
        )


def queries(dataset) -> list[tuple[str, str]]:
    """`(query_id, query_text)` for every topic, in collection order."""
    return [(q.query_id, q.default_text()) for q in dataset.queries_iter()]


def search_interest(query_text: str):
    """One LongEval topic as the single `SearchInterest` the pool builder takes.

    Imported lazily so this module stays importable before Django is configured.
    """
    from tools.recommendation.interests_query import SearchInterest

    return SearchInterest(
        label=query_text, query_text=query_text, embed_text=query_text
    )


def judged_doc_ids(dataset) -> set[str]:
    """Every document id appearing in the qrels — the pooled subset's core."""
    return {q.doc_id for q in dataset.qrels_iter()}

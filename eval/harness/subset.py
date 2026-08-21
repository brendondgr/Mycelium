"""The frozen evaluation subset, and the matrix slice that makes it free.

Two problems this module solves, both of which otherwise cost hours a day.

**1. The subset must not move.** `run.py`'s `pooled` scope is rebuilt on every
invocation from a corpus-wide BM25 pass unioned with the judged set. It is
deterministic, but it is minutes of work and it is silently sensitive to anything
that changes BM25 — so two arms run a week apart could, in principle, be scored
over different documents. For a day of back-to-back ladder comparisons that is
unacceptable: a difference between arm 3 and arm 11 must be about the *ranking*.
So the document id list is computed once, written to `eval/subsets/`, committed,
and every later run loads it instead of recomputing it.

**2. The vectors already exist.** The embedding cache is content-addressed by a
digest of the document ids *in order* (see :func:`.index.cache_key`), so a subset
is a cache miss and re-embeds — about 37 minutes for 84,489 documents with
bge-small on this host. But the cached full-corpus matrix is row-aligned to the
full document order, and the subset is built as an *order-preserving filter* of
that same list. So the subset's vectors are literally a row selection out of a
matrix already on disk. :func:`slice_matrix` takes that selection and writes it
under the key the subset would have computed, turning a 37-minute encode into a
few seconds of numpy — once, ever.

The same discipline generalizes to every model added to the ladder: encode the
frozen subset exactly once, cache it content-addressed, never encode again.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

EVAL_ROOT = Path(__file__).resolve().parent.parent
SUBSET_DIR = EVAL_ROOT / "subsets"


def subset_path(collection_id: str, *, depth: int) -> Path:
    """Where the frozen id list for one collection/pool-depth lives."""
    return SUBSET_DIR / f"{collection_id}__pooled_d{depth}.txt"


def load_frozen(path: Path) -> list[str] | None:
    """The frozen document ids in corpus order, or ``None`` if not built yet."""
    if not path.exists():
        return None
    ids = [line.strip() for line in path.read_text().splitlines()]
    return [doc_id for doc_id in ids if doc_id]


def write_frozen(path: Path, doc_ids: Sequence[str]) -> None:
    """Persist the frozen id list, one per line, in corpus order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(doc_ids) + "\n")


def select(all_docs: Sequence[Any], keep: set[str]) -> tuple[list[Any], list[int]]:
    """``(subset_docs, positions)`` — an order-preserving filter of ``all_docs``.

    ``positions`` are indices into ``all_docs``, which is exactly what
    :func:`slice_matrix` needs to lift the matching rows out of a row-aligned
    embedding matrix. Returning both together is what guarantees the documents and
    the vectors cannot drift out of alignment.
    """
    docs: list[Any] = []
    positions: list[int] = []
    for i, doc in enumerate(all_docs):
        if str(doc.id) in keep:
            docs.append(doc)
            positions.append(i)
    return docs, positions


def slice_matrix(
    full_matrix: np.ndarray,
    positions: Sequence[int],
    *,
    out_path: Path,
    log=print,
) -> np.ndarray:
    """Write the rows of ``full_matrix`` at ``positions`` to ``out_path``.

    The source is normally memory-mapped, so the fancy-index below is the only
    point at which the selected rows are materialized. Idempotent: an existing
    file of the right shape is loaded rather than rebuilt.
    """
    if out_path.exists():
        existing = np.load(out_path, mmap_mode="r")
        if existing.shape[0] == len(positions):
            log(f"matrix slice already present: {out_path.name} {existing.shape}")
            return existing
        log(
            f"matrix slice {out_path.name} has stale shape "
            f"{existing.shape}; rebuilding"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"slicing {len(positions)} rows out of {full_matrix.shape[0]} …")
    sliced = np.ascontiguousarray(full_matrix[np.asarray(positions, dtype=np.int64)])
    np.save(out_path, sliced)
    log(f"matrix slice written: {out_path.name} {sliced.shape}")
    return sliced

"""In-memory exact vector index, plus the on-disk embedding cache.

**Why an exact index is not a compromise.** Production runs *no* ANN index: every
`retrieve_for_vector` call is a pgvector sequential scan ordered by cosine
distance (there is no `hnsw`/`ivfflat` index anywhere in the schema). So
:class:`NumpyIndex` does not approximate production — it computes the identical
ranking, and any difference between the two would be a bug, not a tolerance.

**The cache** is what makes goal 5 ("cheap to re-run") true. Embedding the corpus
dominates wall clock; the vectors are keyed by `(model, snapshot, corpus scope,
doc count, id digest)` so a second run of any arm over the same corpus loads a
memory-mapped `.npy` in seconds. The key includes a digest of the document ids in
order, so a corpus that silently changed underneath cannot reuse stale vectors.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

EVAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_ROOT.parent

#: Where embedding matrices live. **Deliberately outside `eval/`**, next to the
#: downloaded corpora. `eval/cache/` is gitignored, so a `git worktree remove`
#: deletes it — and with it hours of embedding compute, silently. Keeping the
#: matrices under `data/eval-cache/` (also gitignored, but never inside a
#: worktree) means they survive a worktree being torn down, which is the normal
#: end of an agent session. Override with `MYCELIUM_EVAL_CACHE` if you want them
#: elsewhere; point it at a path that is not inside a worktree.
DEFAULT_CACHE_DIR = Path(
    os.environ.get(
        "MYCELIUM_EVAL_CACHE", REPO_ROOT / "data" / "eval-cache" / "embeddings"
    )
)


class NumpyIndex:
    """Exact cosine nearest-neighbour search over a fixed document set.

    Vectors are assumed unit-length (the production embedder normalizes), so the
    cosine similarity is a plain dot product and the ranking is `argsort` of it.
    """

    def __init__(self, docs: Sequence[Any], matrix: np.ndarray) -> None:
        if len(docs) != matrix.shape[0]:
            raise ValueError(
                f"{len(docs)} docs but {matrix.shape[0]} vectors — cache is stale"
            )
        self.docs = list(docs)
        self.matrix = matrix
        self._positions = {str(doc.id): i for i, doc in enumerate(self.docs)}

    def search(
        self,
        vector: Sequence[float] | None,
        *,
        limit: int,
        exclude_ids: Sequence[Any] | None = None,
    ) -> list[tuple[Any, float]]:
        """Up to `limit` documents nearest `vector`, best first, as `(doc, sim)`.

        Mirrors `retrieve_for_vector`'s contract exactly: an empty or `None`
        vector yields `[]`, and similarities are clamped to `[0, 1]`.
        """
        if vector is None or len(vector) == 0 or limit <= 0:
            return []
        query = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        if norm == 0.0:
            return []
        sims = self.matrix @ (query / norm)

        blocked = set()
        if exclude_ids:
            blocked = {
                self._positions[key]
                for key in (str(i) for i in exclude_ids)
                if key in self._positions
            }
        want = min(limit + len(blocked), sims.shape[0])
        # argpartition finds the top-`want` without sorting the whole corpus;
        # only that slice is then ordered.
        top = np.argpartition(-sims, want - 1)[:want]
        top = top[np.argsort(-sims[top], kind="stable")]

        out: list[tuple[Any, float]] = []
        for position in top:
            if position in blocked:
                continue
            similarity = float(sims[position])
            out.append((self.docs[position], min(max(similarity, 0.0), 1.0)))
            if len(out) == limit:
                break
        return out


def cache_key(
    *, model: str, snapshot: str, scope: str, doc_ids: Sequence[str]
) -> str:
    """A content-addressed key for one corpus embedding."""
    digest = hashlib.sha256()
    for doc_id in doc_ids:
        digest.update(doc_id.encode())
        digest.update(b"\x00")
    payload = json.dumps(
        {
            "model": model,
            "snapshot": snapshot,
            "scope": scope,
            "n": len(doc_ids),
            "ids": digest.hexdigest(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def embed_corpus(
    docs: Sequence[Any],
    *,
    model: str,
    snapshot: str,
    scope: str,
    cache_dir: Path | None = None,
    parallel: int | None = None,
    batch_size: int = 64,
    log=print,
) -> np.ndarray:
    """Embed `docs` with the production model, caching the matrix on disk.

    The vectors come from the same `BAAI/bge-small-en-v1.5` fastembed model the
    scan pipeline uses, normalized the same way — `parallel` only shards the work
    across processes and does not change a single value (see
    `tests/test_embedding_parity.py`).
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    ids = [str(doc.id) for doc in docs]
    key = cache_key(model=model, snapshot=snapshot, scope=scope, doc_ids=ids)
    path = cache_dir / f"{key}.npy"

    if path.exists():
        log(f"embedding cache hit: {path.name} ({len(ids)} docs)")
        return np.load(path, mmap_mode="r")

    log(f"embedding {len(ids)} docs with {model} (parallel={parallel}) …")
    from fastembed import TextEmbedding

    embedder = TextEmbedding(model)
    texts = [doc.text for doc in docs]
    raw = np.asarray(
        list(embedder.embed(texts, batch_size=batch_size, parallel=parallel)),
        dtype=np.float32,
    )
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = (raw / norms).astype(np.float32)
    np.save(path, matrix)
    log(f"embedding cache written: {path.name}")
    return matrix

"""SPLADE and ColBERT encoders for the retrieval ladder, with resumable caches.

Both models run as ONNX on CPU through the same `fastembed` the production
embedder uses — this host has no CUDA device, so that is not a preference, it is
the only option. Measured on 32 cores: SPLADE++ 24.3 docs/s, ColBERT-small 31.2
docs/s, which puts a full 84,489-document encode at roughly 58 and 45 minutes
respectively.

Those are one-time costs *provided nothing ever recomputes them*, so this module
takes the same discipline `index.py` established and hardens it in two ways:

* **Content-addressed, like the dense matrix.** The key covers the model, the
  snapshot, the scope, and a digest of the document ids in order, so a corpus that
  changed underneath cannot silently reuse stale vectors.
* **Shard-checkpointed.** An hour-long encode that dies at minute 55 and starts
  over is how a day gets eaten. Each chunk of `CHUNK` documents is written as its
  own shard the moment it finishes; a re-run skips every shard already on disk and
  resumes at the first missing one. Shards merge into the final artifact only once
  every one is present.

Neither model is in production. They are candidates on the ladder, measured
before anything is proposed for deployment.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .index import DEFAULT_CACHE_DIR, cache_key

#: Documents per checkpoint shard. At ~25 docs/s this is about three minutes of
#: work — small enough that a crash is cheap, large enough that shard overhead is
#: noise.
CHUNK = 4096

#: Worker processes fastembed shards an encode across. One ONNX session leaves
#: most of a 32-core host idle on batches this size, and two sessions competing
#: for the same cores is far worse than one — measured the hard way: a 4,096-doc
#: shard took 20 minutes with two encoders running, against a projected three.
#: The ladder now encodes one model at a time, sharded across processes.
PARALLEL = 8

SPLADE_MODEL = "prithivida/Splade_PP_en_v1"
COLBERT_MODEL = "answerdotai/answerai-colbert-small-v1"


def _shard_dir(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.shards"


def _plan(n_docs: int) -> list[tuple[int, int]]:
    return [(start, min(start + CHUNK, n_docs)) for start in range(0, n_docs, CHUNK)]


def _encode_shards(
    docs: Sequence[Any],
    *,
    key: str,
    cache_dir: Path,
    encode_chunk,
    save_shard,
    log,
) -> Path:
    """Run `encode_chunk` over every missing shard; return the shard directory."""
    shards = _shard_dir(cache_dir, key)
    shards.mkdir(parents=True, exist_ok=True)
    plan = _plan(len(docs))
    todo = [
        (i, span)
        for i, span in enumerate(plan)
        if not (shards / f"{i:05d}.npz").exists()
    ]
    if not todo:
        log(f"all {len(plan)} shards already encoded")
        return shards

    log(f"{len(plan) - len(todo)}/{len(plan)} shards cached; encoding {len(todo)} more")
    for n, (i, (start, end)) in enumerate(todo, start=1):
        texts = [docs[j].text for j in range(start, end)]
        payload = encode_chunk(texts)
        save_shard(shards / f"{i:05d}.npz", payload)
        log(f"  shard {i:05d} ({n}/{len(todo)}) — docs {start}-{end}")
    return shards


# -- SPLADE -------------------------------------------------------------------


def splade_encode(
    docs: Sequence[Any],
    *,
    snapshot: str,
    scope: str,
    model: str = SPLADE_MODEL,
    cache_dir: Path | None = None,
    log=print,
):
    """Encode `docs` to a `scipy.sparse.csr_matrix` over the model vocabulary.

    Rows are documents in the given order, columns are vocabulary terms, values
    are the learned term weights. A SPLADE row is an *expanded* bag of words: it
    carries terms the document never contained and downweights ones it did, which
    is what separates it from BM25 and what makes it worth measuring here.
    """
    from scipy import sparse

    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    ids = [str(doc.id) for doc in docs]
    key = cache_key(model=model, snapshot=snapshot, scope=scope, doc_ids=ids)
    final = cache_dir / f"{key}.splade.npz"
    if final.exists():
        log(f"SPLADE cache hit: {final.name} ({len(ids)} docs)")
        return sparse.load_npz(final)

    embedder = _splade_model(model)

    def encode_chunk(texts: list[str]):
        rows, cols, vals = [], [], []
        stream = embedder.embed(texts, batch_size=16, parallel=PARALLEL)
        for r, emb in enumerate(stream):
            idx = np.asarray(emb.indices, dtype=np.int32)
            rows.append(np.full(idx.shape, r, dtype=np.int32))
            cols.append(idx)
            vals.append(np.asarray(emb.values, dtype=np.float32))
        return {
            "rows": np.concatenate(rows) if rows else np.empty(0, np.int32),
            "cols": np.concatenate(cols) if cols else np.empty(0, np.int32),
            "vals": np.concatenate(vals) if vals else np.empty(0, np.float32),
            "n": np.asarray([len(texts)], dtype=np.int64),
        }

    shards = _encode_shards(
        docs,
        key=key,
        cache_dir=cache_dir,
        encode_chunk=encode_chunk,
        save_shard=lambda path, payload: np.savez(path, **payload),
        log=log,
    )

    log("merging SPLADE shards …")
    all_rows, all_cols, all_vals, offset, width = [], [], [], 0, 0
    for path in sorted(shards.glob("*.npz")):
        blob = np.load(path)
        all_rows.append(blob["rows"].astype(np.int64) + offset)
        all_cols.append(blob["cols"])
        all_vals.append(blob["vals"])
        offset += int(blob["n"][0])
        if blob["cols"].size:
            width = max(width, int(blob["cols"].max()) + 1)
    matrix = sparse.csr_matrix(
        (
            np.concatenate(all_vals),
            (np.concatenate(all_rows), np.concatenate(all_cols).astype(np.int64)),
        ),
        shape=(offset, max(width, 30522)),
        dtype=np.float32,
    )
    sparse.save_npz(final, matrix)
    log(f"SPLADE cache written: {final.name} {matrix.shape}, nnz={matrix.nnz}")
    return matrix


def _splade_model(model: str = SPLADE_MODEL):
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(model)


def splade_query_vector(embedder, text: str, width: int):
    """One query as a 1-row CSR matrix, aligned to the document matrix width."""
    from scipy import sparse

    emb = next(iter(embedder.query_embed([text])))
    cols = np.asarray(emb.indices, dtype=np.int64)
    vals = np.asarray(emb.values, dtype=np.float32)
    keep = cols < width
    cols, vals = cols[keep], vals[keep]
    return sparse.csr_matrix(
        (vals, (np.zeros_like(cols), cols)), shape=(1, width), dtype=np.float32
    )


# -- ColBERT ------------------------------------------------------------------


@dataclass
class ColbertStore:
    """Per-token document vectors, flattened with an offset table.

    ColBERT keeps one vector per token rather than one per document, so the store
    is ragged. Flat storage plus `offsets` keeps it memory-mappable: `doc i` is
    `flat[offsets[i]:offsets[i + 1]]`. Held as float16 — the MaxSim ranking is
    unchanged at that precision and it halves a multi-gigabyte artifact.
    """

    flat: np.ndarray  # (total_tokens, dim) float16
    offsets: np.ndarray  # (n_docs + 1,) int64

    def doc(self, i: int) -> np.ndarray:
        return self.flat[self.offsets[i] : self.offsets[i + 1]]

    def __len__(self) -> int:
        return len(self.offsets) - 1


def colbert_encode(
    docs: Sequence[Any],
    *,
    snapshot: str,
    scope: str,
    model: str = COLBERT_MODEL,
    cache_dir: Path | None = None,
    log=print,
) -> ColbertStore:
    """Encode `docs` to per-token vectors, cached and resumable."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    ids = [str(doc.id) for doc in docs]
    key = cache_key(model=model, snapshot=snapshot, scope=scope, doc_ids=ids)
    flat_path = cache_dir / f"{key}.colbert.flat.npy"
    off_path = cache_dir / f"{key}.colbert.offsets.npy"
    if flat_path.exists() and off_path.exists():
        log(f"ColBERT cache hit: {flat_path.name} ({len(ids)} docs)")
        return ColbertStore(
            flat=np.load(flat_path, mmap_mode="r"),
            offsets=np.load(off_path),
        )

    embedder = _colbert_model(model)

    def encode_chunk(texts: list[str]):
        mats = [
            np.asarray(m, dtype=np.float16)
            for m in embedder.embed(texts, batch_size=16, parallel=PARALLEL)
        ]
        lengths = np.asarray([m.shape[0] for m in mats], dtype=np.int64)
        empty = np.empty((0, 96), np.float16)
        return {
            "flat": np.concatenate(mats, axis=0) if mats else empty,
            "lengths": lengths,
        }

    shards = _encode_shards(
        docs,
        key=key,
        cache_dir=cache_dir,
        encode_chunk=encode_chunk,
        save_shard=lambda path, payload: np.savez(path, **payload),
        log=log,
    )

    log("merging ColBERT shards …")
    blocks, lengths = [], []
    for path in sorted(shards.glob("*.npz")):
        blob = np.load(path)
        blocks.append(blob["flat"])
        lengths.append(blob["lengths"])
    flat = np.concatenate(blocks, axis=0)
    all_lengths = np.concatenate(lengths)
    offsets = np.zeros(len(all_lengths) + 1, dtype=np.int64)
    np.cumsum(all_lengths, out=offsets[1:])
    np.save(flat_path, flat)
    np.save(off_path, offsets)
    log(f"ColBERT cache written: {flat.shape} over {len(all_lengths)} docs")
    return ColbertStore(flat=np.load(flat_path, mmap_mode="r"), offsets=offsets)


def _colbert_model(model: str = COLBERT_MODEL):
    from fastembed import LateInteractionTextEmbedding

    return LateInteractionTextEmbedding(model)


def colbert_query_vectors(embedder, text: str) -> np.ndarray:
    """Per-token query vectors, float32 for the MaxSim dot products."""
    return np.asarray(next(iter(embedder.query_embed([text]))), dtype=np.float32)


def maxsim(query: np.ndarray, doc: np.ndarray) -> float:
    """The ColBERT late-interaction score.

    For every query token, the single best-matching document token; summed.
    Formally ``sum_i max_j (q_i . d_j)`` — which is why it can align "knowledge
    graph" against "structured representations" with no shared vocabulary, and why
    the alignment it produces is displayable back to a user.
    """
    if doc.shape[0] == 0 or query.shape[0] == 0:
        return 0.0
    return float(np.max(query @ doc.astype(np.float32).T, axis=1).sum())


def write_manifest(path: Path, payload: dict) -> None:
    """A small sidecar describing what an artifact holds, for the record."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

"""The tool's file store and the rows that point into it.

Every retrieved paper becomes two files under ``data/fulltext/files/``, named
by the SHA-256 of the original (so the same PDF fetched twice is stored once):

    files/<aa>/<sha256>.<pdf|xml|html|txt>   the original, as the source served it
    files/<aa>/<sha256>.md                   the markdown document (metadata,
                                             abstract, full text)

The engine's own cache (``data/fulltext/cache/``) is internal and may be
cleared at any time; nothing outside the engine reads it.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from django.db import IntegrityError, transaction
from django.db.models import Q

from tools.retrieval.read import ContentItem

from . import config
from .engine.cache import atomic_write
from .engine.pipeline import ORIGINAL_EXT
from .models import FulltextDocument


def absolute(relative: str) -> Path:
    """A stored path, made absolute; refuses anything that escapes the store."""
    root = config.data_root().resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise ValueError(f"{relative!r} is outside the full-text store")
    return path


def find_document(ids: dict) -> FulltextDocument | None:
    """An already-stored document for any of these identifiers."""
    q = Q()
    for field, key in (
        ("doi", "doi"),
        ("pmid", "pmid"),
        ("pmcid", "pmcid"),
        ("arxiv_id", "arxiv"),
    ):
        if ids.get(key):
            q |= Q(**{field: ids[key]})
    if not q:
        return None
    return FulltextDocument.objects.filter(q).order_by("-fetched_at").first()


def find_content_item(ids: dict) -> ContentItem | None:
    """The corpus paper with any of these identifiers, if the corpus has it."""
    q = Q()
    for key in ("doi", "pmid", "pmcid", "arxiv"):
        if ids.get(key):
            q |= Q(**{f"metadata__{key}": ids[key]})
    if not q:
        return None
    return ContentItem.objects.filter(q, type=ContentItem.Type.PAPER).first()


def save(result: dict) -> FulltextDocument:
    """Store a ``full_text`` engine result and return its document row.

    Idempotent on the DOI: a paper already stored is returned as it is.
    """
    ids = result.get("ids") or {}
    existing = find_document(ids)
    if existing is not None:
        return existing

    markdown = result["document"].encode("utf-8")
    original = result.get("original")
    data = Path(original["path"]).read_bytes() if original else b""
    sha = hashlib.sha256(data or markdown).hexdigest()
    folder = Path("files") / sha[:2]
    original_rel = ""
    if original:
        ext = ORIGINAL_EXT.get(original["kind"], "bin")
        original_rel = str(folder / f"{sha}.{ext}")
        target = absolute(original_rel)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".part")
            shutil.copyfile(original["path"], tmp)
            tmp.replace(target)
    markdown_rel = str(folder / f"{sha}.md")
    atomic_write(absolute(markdown_rel), markdown)

    meta = result.get("metadata") or {}
    row = FulltextDocument(
        content_item=find_content_item(ids),
        doi=ids.get("doi") or "",
        pmid=ids.get("pmid") or "",
        pmcid=ids.get("pmcid") or "",
        arxiv_id=ids.get("arxiv") or "",
        title=meta.get("title") or "",
        metadata={k: v for k, v in meta.items() if k != "title"},
        source=result["source"],
        source_url=(result.get("source_url") or "")[:1000],
        licensed=bool(result.get("licensed")),
        original_path=original_rel,
        original_kind=(original or {}).get("kind", ""),
        markdown_path=markdown_rel,
        chars=int(result.get("chars") or 0),
        sha256=sha,
    )
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError:  # another worker stored the same DOI meanwhile
        return find_document(ids) or row
    return row


def read_markdown(doc: FulltextDocument) -> str:
    return absolute(doc.markdown_path).read_text(encoding="utf-8")


def original_file(doc: FulltextDocument) -> Path | None:
    return absolute(doc.original_path) if doc.original_path else None
